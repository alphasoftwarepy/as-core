"""
AS-Core — Fase 2.2F: Relevance Score Threshold Ablation Runner
=============================================================================
Evaluates the single variable: RELEVANCE SCORE THRESHOLD.
Threshold values:
  R1   = 0.00 (Baseline)
  R2a  = 0.40
  R2b  = 0.50
  R2c  = 0.60
  R2d  = 0.65
  R2e  = 0.70
  R2f  = 0.75

Etapa 1: Complete retrieval curve over all 20 frozen benchmark cases.
Etapa 2: Physical inference with Gemma 3n E2B on the top finalist thresholds.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.database import init_db, get_session
from api.rag_service import build_rag_service, RAGService
from api.context_builder import get_context_builder, RetrievedChunk
from benchmarks.run_phase_2_2e_baseline import (
    BENCHMARK_CASES,
    BENCHMARK_DB_PATH,
    BENCHMARK_FAISS_PATH,
    evaluate_case_response,
)
from providers.base import InferenceRequest
from api.models import ChatCompletionRequest, ChatMessage
from runtime.coordinator.manager import PureCoordinator
from runtime.coordinator.models import RuntimeContract, SessionSnapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("benchmarks.phase_2_2f")

THRESHOLDS = [0.00, 0.40, 0.50, 0.60, 0.65, 0.70, 0.75]
RESULTS_OUTPUT_PATH = ROOT / "benchmarks" / "results" / "phase_2_2f_threshold_results.json"


def run_etapa_1_curve(rag_service: RAGService, db) -> Dict[str, Any]:
    print("=" * 80)
    print("ETAPA 1 — CURVA DE RETRIEVAL (0.00 -> 0.75)")
    print("=" * 80)

    # 1. Gather all raw retrieved chunks for each case
    case_raw_retrieval: Dict[str, List[RetrievedChunk]] = {}
    for case in BENCHMARK_CASES:
        cid = case["id"]
        session_id = f"sess_{cid}"
        prompt = case["prompt"]
        chunks = rag_service.retrieve(prompt, db, top_k=5, session_id=session_id)
        case_raw_retrieval[cid] = chunks

    curve_summary: Dict[float, Dict[str, Any]] = {}
    per_case_curves: Dict[str, Dict[float, Dict[str, Any]]] = {c["id"]: {} for c in BENCHMARK_CASES}

    doc_cases = [c for c in BENCHMARK_CASES if c["expected_rag"]]
    non_doc_cases = [c for c in BENCHMARK_CASES if not c["expected_rag"]]

    for th in THRESHOLDS:
        total_surviving = 0
        total_relevant = 0
        total_irrelevant = 0
        false_rag_on = 0
        false_rag_off = 0
        total_context_chars = 0
        builder = get_context_builder()

        for case in BENCHMARK_CASES:
            cid = case["id"]
            gt_kw = [k.lower() for k in case.get("gt_keywords", [])]
            raw_chunks = case_raw_retrieval[cid]

            # Filter by threshold
            surviving_chunks = [c for c in raw_chunks if c.score >= th]
            surviving_count = len(surviving_chunks)
            total_surviving += surviving_count

            rel_count = 0
            for sc in surviving_chunks:
                txt = sc.text.lower()
                if any(k in txt for k in gt_kw):
                    rel_count += 1
            irrel_count = surviving_count - rel_count

            total_relevant += rel_count
            total_irrelevant += irrel_count

            # Compose context if any survived
            if surviving_chunks:
                ctx = builder.build(surviving_chunks, mode="normal", query=case["prompt"])
            else:
                ctx = ""
            ctx_len = len(ctx)
            total_context_chars += ctx_len

            is_rag_on = ctx_len > 0
            if not case["expected_rag"] and is_rag_on:
                false_rag_on += 1
            if case["expected_rag"] and not is_rag_on:
                false_rag_off += 1

            per_case_curves[cid][th] = {
                "surviving_count": surviving_count,
                "relevant_count": rel_count,
                "irrelevant_count": irrel_count,
                "context_chars": ctx_len,
                "rag_on": is_rag_on,
                "max_score": round(max((c.score for c in raw_chunks), default=0.0), 4),
            }

        noise_ratio = (total_irrelevant / total_surviving * 100) if total_surviving > 0 else 0.0
        avg_chunks = total_surviving / len(BENCHMARK_CASES)
        avg_ctx_tok = (total_context_chars / len(BENCHMARK_CASES)) // 4

        curve_summary[th] = {
            "threshold": th,
            "total_surviving_chunks": total_surviving,
            "total_relevant_chunks": total_relevant,
            "total_irrelevant_chunks": total_irrelevant,
            "noise_ratio_pct": round(noise_ratio, 1),
            "false_rag_on": false_rag_on,
            "false_rag_off": false_rag_off,
            "avg_chunks_per_case": round(avg_chunks, 2),
            "avg_context_tokens": int(avg_ctx_tok),
        }

    # Print markdown table for Etapa 1
    print("\n| Threshold | Surviving Chunks | Relevant Chunks | Noise Ratio | False RAG ON | False RAG OFF | Avg Ctx Tokens |")
    print("| :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for th in THRESHOLDS:
        s = curve_summary[th]
        print(f"| **{th:.2f}** | {s['total_surviving_chunks']} | {s['total_relevant_chunks']} | {s['noise_ratio_pct']}% | {s['false_rag_on']}/3 | {s['false_rag_off']}/17 | {s['avg_context_tokens']} tok |")

    return {
        "summary": curve_summary,
        "per_case": per_case_curves,
        "case_raw_retrieval": case_raw_retrieval,
    }


async def run_etapa_2_physical(
    finalist_thresholds: List[float],
    rag_service: RAGService,
    db,
    etapa1_data: Dict[str, Any],
) -> Dict[float, Any]:
    print("\n" + "=" * 80)
    print(f"ETAPA 2 — INFERENCIA FÍSICA GEMMA 3n E2B (Finalistas: {finalist_thresholds})")
    print("=" * 80)

    from api.main import app, lifespan
    runner = lifespan(app)
    await runner.__aenter__()
    engine = app.state.engine

    coordinator = PureCoordinator()
    builder = get_context_builder()

    finalist_results: Dict[float, Any] = {}

    for th in finalist_thresholds:
        print(f"\n>>> RUNNING PHYSICAL BENCHMARK FOR THRESHOLD = {th:.2f}")
        case_results = []

        for case in BENCHMARK_CASES:
            cid = case["id"]
            prompt = case["prompt"]
            session_id = f"sess_{cid}"

            history = []
            if "turn1_prompt" in case:
                t1_prompt = case["turn1_prompt"]
                history.append(ChatMessage(role="user", content=t1_prompt))
                history.append(ChatMessage(role="assistant", content="Entendido."))

            messages = history + [ChatMessage(role="user", content=prompt)]

            contract = RuntimeContract(
                request_id=f"th_{int(th*100)}_{cid}",
                session_id=session_id,
                user_message=prompt,
                model_id="chat",
                profile="AUTO",
                timestamp=time.time(),
                snapshot=SessionSnapshot(session_id=session_id, turn_number=len(history) + 1),
            )

            # Assemble base prompt (without RAG first)
            manifest = coordinator.assemble(
                db=db,
                contract=contract,
                skill_service=None,
                rag_service=None,
                memory_service=None,
                enable_rag=False,
                graph_provider=None,
            )

            # Get raw chunks and apply threshold
            t_ret_start = time.perf_counter()
            raw_chunks = rag_service.retrieve(prompt, db, top_k=5, session_id=session_id)
            filtered_chunks = [c for c in raw_chunks if c.score >= th]
            ret_latency_ms = (time.perf_counter() - t_ret_start) * 1000

            # Build context if chunks survived
            if filtered_chunks:
                rag_context = builder.build(filtered_chunks, mode="normal", query=prompt)
                system_prompt = f"{manifest.system_prompt_snapshot}\n\n{rag_context}"
            else:
                rag_context = ""
                system_prompt = manifest.system_prompt_snapshot

            req = ChatCompletionRequest(
                model="chat",
                messages=messages,
                temperature=0.5,
                max_tokens=512,
                stream=False,
            )

            inf_req = InferenceRequest(
                prompt=req.build_prompt(),
                model_id="chat",
                temperature=0.5,
                max_tokens=512,
                top_p=0.95,
                top_k=40,
                stream=False,
                system_prompt=system_prompt,
                request_id=contract.request_id,
            )

            t0 = time.perf_counter()
            res = await engine.generate(inf_req)
            total_time = time.perf_counter() - t0
            answer = res.text or ""
            tokens_gen = res.tokens_generated

            eval_res = evaluate_case_response(case, answer, rag_context)

            # Relevant vs irrelevant in surviving chunks
            gt_kw = [k.lower() for k in case.get("gt_keywords", [])]
            rel_chunks = sum(1 for c in filtered_chunks if any(k in c.text.lower() for k in gt_kw))
            irrel_chunks = len(filtered_chunks) - rel_chunks

            res_entry = {
                "case_id": cid,
                "name": case["name"],
                "threshold": th,
                "rag_injected": len(rag_context) > 0,
                "answer": answer,
                "status": eval_res["status"],
                "score": eval_res["score"],
                "eval_detail": eval_res,
                "latency_s": round(total_time, 3),
                "retrieval_latency_ms": round(ret_latency_ms, 2),
                "output_tokens": tokens_gen,
                "context_chars": len(system_prompt),
                "context_tokens": len(system_prompt) // 4,
                "rag_context_chars": len(rag_context),
                "surviving_chunks_count": len(filtered_chunks),
                "relevant_chunks": rel_chunks,
                "irrelevant_chunks": irrel_chunks,
                "top_scores": [round(c.score, 4) for c in filtered_chunks[:3]],
            }
            case_results.append(res_entry)
            print(f"  [{cid}] TH={th:.2f} -> {eval_res['status']} ({eval_res['score']:.1f}%) | Time: {total_time:.2f}s | Chunks: {len(filtered_chunks)} (rel={rel_chunks}) | CtxChars: {len(rag_context)}")

        # Compute summary for this threshold
        doc_indices = [i for i, c in enumerate(BENCHMARK_CASES) if c["expected_rag"]]
        non_doc_indices = [i for i, c in enumerate(BENCHMARK_CASES) if not c["expected_rag"]]

        q_global = sum(r["score"] for r in case_results) / len(case_results)
        q_doc = sum(case_results[i]["score"] for i in doc_indices) / len(doc_indices)
        q_nondoc = sum(case_results[i]["score"] for i in non_doc_indices) / len(non_doc_indices)

        tot_surv = sum(r["surviving_chunks_count"] for r in case_results)
        tot_irrel = sum(r["irrelevant_chunks"] for r in case_results)
        noise_ratio = (tot_irrel / tot_surv * 100) if tot_surv > 0 else 0.0

        false_on = sum(1 for i in non_doc_indices if case_results[i]["rag_injected"])
        false_off = sum(1 for i in doc_indices if not case_results[i]["rag_injected"])

        avg_lat = sum(r["latency_s"] for r in case_results) / len(case_results)
        avg_tok = sum(r["context_tokens"] for r in case_results) / len(case_results)

        iso_res = next(r for r in case_results if r["case_id"] == "CASE_R")

        finalist_results[th] = {
            "quality_global": round(q_global, 2),
            "quality_documental": round(q_doc, 2),
            "quality_nondoc": round(q_nondoc, 2),
            "noise_ratio_pct": round(noise_ratio, 1),
            "false_rag_on": false_on,
            "false_rag_off": false_off,
            "avg_latency_s": round(avg_lat, 2),
            "avg_context_tokens": int(avg_tok),
            "isolation_preserved": iso_res["status"] == "PASS",
            "cases": case_results,
        }

    await runner.__aexit__(None, None, None)
    return finalist_results


async def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    init_db(BENCHMARK_DB_PATH)
    db = get_session()

    rag_service = build_rag_service(
        faiss_index_path=BENCHMARK_FAISS_PATH,
        embedding_dim=384,
        embedder_model="BAAI/bge-small-en-v1.5",
        chunk_size=300,
        chunk_overlap=50,
        retrieval_mode="hybrid",
        hybrid_alpha=0.7,
    )

    # 1. Run Etapa 1
    etapa1_data = run_etapa_1_curve(rag_service, db)

    # 2. Select Finalist Thresholds based on data
    # We want thresholds that balance False ON reduction with minimizing False OFF
    # Let's inspect thresholds like 0.60, 0.65, 0.70
    finalists = [0.50, 0.65, 0.70]

    # 3. Run Etapa 2 physical inference
    etapa2_data = await run_etapa_2_physical(finalists, rag_service, db, etapa1_data)

    # 4. Save consolidated payload
    consolidated_results = {
        "etapa_1_curve": etapa1_data["summary"],
        "etapa_1_per_case": etapa1_data["per_case"],
        "etapa_2_finalists": {str(k): v for k, v in etapa2_data.items()},
    }

    RESULTS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_OUTPUT_PATH, "w", encoding="utf-8") as fp:
        json.dump(consolidated_results, fp, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print("PHASE 2.2F THRESHOLD ABLATION COMPLETED SUCCESSFULLY!")
    print(f"Results saved to: {RESULTS_OUTPUT_PATH}")
    print("=" * 80)

    db.close()


if __name__ == "__main__":
    asyncio.run(main())
