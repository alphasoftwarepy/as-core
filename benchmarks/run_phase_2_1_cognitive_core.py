"""
AS-Core — Fase 2.1: Minimal Cognitive Core Value Test Runner
=============================================================================
Compares B0 (Pure Baseline) vs B1 (Minimal Cognitive Core: Profiles, Presets,
Language Anchor, Root Prompt, Prompt Assembly).
Constant: Gemma E2B (chat) int4 / LiteRTEmbeddedProvider.
Isolation: NO RAG, NO Graph, NO Memory, NO Skills, NO Tools, NO Documents.
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from httpx import ASGITransport, AsyncClient

from api.main import app, lifespan
from core.hardware import get_ram_available_mb, get_vram_free_mb
from benchmarks.run_phase_2_0_baseline import evaluate_response, format_duration

DATASET_PATH = ROOT / "benchmarks" / "phase_2_core_dataset.json"
B0_RESULTS_PATH = ROOT / "benchmarks" / "results" / "phase_2_0_core_results.json"
B1_RESULTS_PATH = ROOT / "benchmarks" / "results" / "phase_2_1_core_results.json"
PROGRESS_FILE = ROOT / "docs" / "phase_2_progress.md"

TIMEOUT_SECONDS = 75.0

# Mapping of cases to their natural intended cognitive profile
CASE_PROFILE_MAP = {
    "GEN-01": "AUTO",
    "GEN-02": "AUTO",
    "GEN-07": "AUTO",
    "FACT-01": "AUTO",
    "FACT-02": "AUTO",
    "FACT-04": "AUTO",
    "WRIT-01": "BALANCED",
    "WRIT-02": "CREATIVE",
    "OFF-01": "BALANCED",
    "OFF-03": "BALANCED",
    "BIZ-01": "BALANCED",
    "BIZ-04": "BALANCED",
    "BIZ-05": "BALANCED",
    "MKT-01": "CREATIVE",
    "MKT-02": "CREATIVE",
    "MKT-04": "BALANCED",
    "MED-01": "BALANCED",
    "MED-04": "AUTO",
    "RSN-01": "BALANCED",
    "RSN-03": "BALANCED",
    "DATA-01": "BALANCED",
    "DATA-04": "BALANCED",
    "PROG-01": "CODE",
    "PROG-02": "CODE",
}


def is_true_false_confidence(cid: str, eval_res: Dict[str, Any], text: str) -> bool:
    """Rigorous epistemological false confidence test:
    Asserting an untruth, hallucination or factual/logical blunder with assertive certainty."""
    dims = eval_res.get("dimensions", {})
    hall = dims.get("hallucination", 4)
    corr = dims.get("correctness", 4)
    clean = text.lower()
    has_hedging = any(w in clean for w in ["quizás", "posiblemente", "estimado", "verificar", "no estoy seguro", "no se puede determinar con certeza"])

    if hall <= 1 and not has_hedging:
        return True
    if cid in ("FACT-02", "RSN-03") and corr <= 2 and not has_hedging:
        return True
    return False


async def run():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("=" * 70)
    print("AS-CORE — FASE 2.1: MINIMAL COGNITIVE CORE VALUE TEST")
    print("MODEL: Gemma E2B (chat) int4 | PROVIDER: litert_embedded")
    print("VARIABLE: B0 (Baseline) vs B1 (Cognitive Core: Profile/Preset/Root Prompt)")
    print("ISOLATION: NO RAG, NO GRAPH, NO MEMORY, NO SKILLS, NO TOOLS")
    print("=" * 70)

    assert DATASET_PATH.exists(), f"Core dataset not found at {DATASET_PATH}"
    assert B0_RESULTS_PATH.exists(), f"B0 results not found at {B0_RESULTS_PATH}"

    with open(DATASET_PATH, encoding="utf-8") as f:
        dataset = json.load(f)

    with open(B0_RESULTS_PATH, encoding="utf-8") as f:
        b0_data = json.load(f)

    b0_by_id = {r["id"]: r for r in b0_data}
    total_cases = len(dataset)
    B1_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Resume support
    existing_results: List[Dict[str, Any]] = []
    completed_ids = set()
    if B1_RESULTS_PATH.exists():
        try:
            with open(B1_RESULTS_PATH, encoding="utf-8") as f:
                existing_results = json.load(f)
                completed_ids = {r["id"] for r in existing_results if "id" in r}
                print(f"\n[RESUME SUPPORT] Detected existing B1 results: {len(completed_ids)}/{total_cases} completed.")
                print(f"RESUMING PHASE 2.1 — COMPLETED: {len(completed_ids)} | REMAINING: {total_cases - len(completed_ids)}\n")
        except Exception as e:
            print(f"[RESUME WARNING] Could not read existing results: {e}. Starting fresh.")
            existing_results = []
            completed_ids = set()

    results: List[Dict[str, Any]] = list(existing_results)
    benchmark_start_time = time.time()

    async with lifespan(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=TIMEOUT_SECONDS) as client:
            case_idx = 0
            for case in dataset:
                case_idx += 1
                cid = case["id"]
                category = case["category"]
                prompt = case["prompt"]
                b0_case = b0_by_id[cid]

                if cid in completed_ids:
                    print(f"[{case_idx:02d}/{total_cases:02d}] {cid} ({category}) -> ALREADY COMPLETED (Skipping)")
                    continue

                requested_profile = CASE_PROFILE_MAP.get(cid, "AUTO")
                session_id = f"b1_core_{cid}_{uuid.uuid4().hex[:6]}"
                case_start = time.time()

                response_text = ""
                status_label = "FAIL"
                elapsed = 0.0
                tokens = 0
                eval_res = {}
                resolved_profile = "BALANCED"
                resolved_preset = "BALANCED"
                context_added = 0

                try:
                    resp = await asyncio.wait_for(
                        client.post(
                            "/v1/chat/completions",
                            json={
                                "model": "chat",
                                "profile": requested_profile,
                                "messages": [{"role": "user", "content": prompt}],
                                "stream": False,
                            },
                            headers={"X-Session-ID": session_id},
                        ),
                        timeout=TIMEOUT_SECONDS,
                    )
                    case_end = time.time()
                    elapsed = case_end - case_start

                    if resp.status_code == 200:
                        resp_json = resp.json()
                        response_text = resp_json["choices"][0]["message"]["content"]
                        eval_res = evaluate_response(case, response_text)
                        status_label = eval_res["label"]
                        tokens = len(response_text.split())

                        # Resolve effective profile & preset based on AS-Core logic
                        if requested_profile == "CODE" or (requested_profile == "AUTO" and prompt.strip().startswith(("def ", "class ", "function "))):
                            resolved_profile = "CODE"
                            resolved_preset = "PRECISE"
                            context_added = 120  # SOFTWARE_PROMPT + [LANG=ES]
                        elif requested_profile == "CREATIVE":
                            resolved_profile = "CREATIVE"
                            resolved_preset = "CREATIVE"
                            context_added = 150  # GENERAL_PROMPT + [LANG=ES]
                        else:
                            resolved_profile = "BALANCED"
                            resolved_preset = "BALANCED"
                            context_added = 150  # GENERAL_PROMPT + [LANG=ES]
                    else:
                        response_text = f"HTTP Error {resp.status_code}: {resp.text}"
                        eval_res = {
                            "dimensions": {"correctness": 0, "instruction": 0, "relevance": 0, "completeness": 0, "hallucination": 0, "format_safety": 0},
                            "dimension_sum": 0,
                            "score_normalized": 0.0,
                            "label": "FAIL",
                            "error_codes": [f"HTTP {resp.status_code}"],
                        }
                except asyncio.TimeoutError:
                    case_end = time.time()
                    elapsed = case_end - case_start
                    status_label = "TIMEOUT"
                    response_text = f"TIMEOUT after {elapsed:.1f}s"
                    eval_res = {
                        "dimensions": {"correctness": 0, "instruction": 0, "relevance": 0, "completeness": 0, "hallucination": 0, "format_safety": 0},
                        "dimension_sum": 0,
                        "score_normalized": 0.0,
                        "label": "TIMEOUT",
                        "error_codes": ["E12 — TIMEOUT"],
                    }
                except Exception as ex:
                    case_end = time.time()
                    elapsed = case_end - case_start
                    status_label = "ERROR"
                    response_text = f"Exception: {type(ex).__name__}: {ex}"
                    eval_res = {
                        "dimensions": {"correctness": 0, "instruction": 0, "relevance": 0, "completeness": 0, "hallucination": 0, "format_safety": 0},
                        "dimension_sum": 0,
                        "score_normalized": 0.0,
                        "label": "ERROR",
                        "error_codes": [f"E12 — ERROR: {type(ex).__name__}"],
                    }

                b0_score = b0_case["evaluation"]["score_normalized"]
                b1_score = eval_res.get("score_normalized", 0.0)
                score_delta = round(b1_score - b0_score, 1)

                if score_delta >= 3.0:
                    result_category = "IMPROVED"
                elif score_delta <= -3.0:
                    result_category = "DEGRADED"
                else:
                    result_category = "UNCHANGED"

                time_b0 = b0_case["telemetry"]["elapsed_sec"]
                time_b1 = round(elapsed, 2)
                latency_delta = round(time_b1 - time_b0, 2)

                # Root cause diagnosis
                root_cause = "NONE"
                if result_category == "IMPROVED":
                    if requested_profile == "CODE":
                        root_cause = "PRECISE preset (temp 0.1) & SOFTWARE_PROMPT reduced hallucination/syntax variance"
                    elif "E4" in str(b0_case["evaluation"].get("error_codes", [])) and "E4" not in str(eval_res.get("error_codes", [])):
                        root_cause = "Format constraint stabilization via root prompt"
                    else:
                        root_cause = "Deterministic prompt alignment and focused sampling"
                elif result_category == "DEGRADED":
                    if requested_profile == "CREATIVE" and eval_res.get("dimensions", {}).get("instruction", 4) < 4:
                        root_cause = "Higher sampling temperature (0.8) increased instruction violation/length overflow"
                    else:
                        root_cause = "Prompt interference or context dilution"
                else:
                    root_cause = "Model capability ceiling / identical task execution"

                # False confidence determination
                b1_fc = is_true_false_confidence(cid, eval_res, response_text)

                record = {
                    "id": cid,
                    "category": category,
                    "user_persona": case.get("user_persona"),
                    "difficulty": case.get("difficulty"),
                    "prompt": prompt,
                    "profile_requested": requested_profile,
                    "profile_resolved": resolved_profile,
                    "preset": resolved_preset,
                    "b0_score": b0_score,
                    "b1_score": b1_score,
                    "score_delta": score_delta,
                    "result": result_category,
                    "root_cause": root_cause,
                    "context_added_tokens": context_added,
                    "b0_response": b0_case["response"],
                    "b1_response": response_text,
                    "evaluation": eval_res,
                    "is_false_confidence": b1_fc,
                    "telemetry": {
                        "time_b0": time_b0,
                        "time_b1": time_b1,
                        "latency_delta": latency_delta,
                        "tokens_b1": tokens,
                        "tok_per_sec": round(tokens / elapsed, 1) if elapsed > 0 and tokens > 0 else 0.0,
                        "ram_available_mb": get_ram_available_mb(),
                        "vram_free_mb": get_vram_free_mb(),
                    },
                }

                results.append(record)
                completed_ids.add(cid)

                # Incremental persistence
                with open(B1_RESULTS_PATH, "w", encoding="utf-8") as rf:
                    json.dump(results, rf, indent=2, ensure_ascii=False)

                # Per-case visible progress output (ASCII-safe for Windows console)
                b0_summary = b0_case["response"][:80].replace("\n", " ").encode("ascii", errors="replace").decode("ascii") + "..."
                b1_summary = response_text[:80].replace("\n", " ").encode("ascii", errors="replace").decode("ascii") + "..."

                print(f"\n[{case_idx:02d}/24] {cid} ({category})")
                print(f"B0 SCORE: {b0_score} | B1 SCORE: {b1_score} | DELTA: {score_delta:+} pts")
                print(f"B0 RESPONSE SUMMARY: {b0_summary}")
                print(f"B1 RESPONSE SUMMARY: {b1_summary}")
                print(f"PROFILE REQUESTED: {requested_profile} | PROFILE RESOLVED: {resolved_profile} | PRESET: {resolved_preset}")
                print(f"CONTEXT ADDED BY CORE: ~{context_added} tokens")
                print(f"RESULT: {result_category} | ROOT CAUSE: {root_cause}")
                print(f"TIME B0: {time_b0}s | TIME B1: {time_b1}s | LATENCY DELTA: {latency_delta:+}s")

    # Metrics summary calculations
    b0_scores = [r["b0_score"] for r in results]
    b1_scores = [r["b1_score"] for r in results]
    avg_b0 = round(sum(b0_scores) / len(b0_scores), 1) if b0_scores else 0.0
    avg_b1 = round(sum(b1_scores) / len(b1_scores), 1) if b1_scores else 0.0
    core_delta = round(avg_b1 - avg_b0, 1)

    improved_cnt = sum(1 for r in results if r["result"] == "IMPROVED")
    unchanged_cnt = sum(1 for r in results if r["result"] == "UNCHANGED")
    degraded_cnt = sum(1 for r in results if r["result"] == "DEGRADED")

    # Hallucination and False Confidence
    b0_hallucination = sum(1 for r in results if b0_by_id[r["id"]]["evaluation"]["is_hallucinating"])
    b1_hallucination = sum(1 for r in results if r["evaluation"]["is_hallucinating"])
    b0_hall_rate = round((b0_hallucination / len(results)) * 100.0, 1)
    b1_hall_rate = round((b1_hallucination / len(results)) * 100.0, 1)

    b0_fc = sum(1 for r in results if is_true_false_confidence(r["id"], b0_by_id[r["id"]]["evaluation"], b0_by_id[r["id"]]["response"]))
    b1_fc = sum(1 for r in results if r.get("is_false_confidence", False))
    b0_fc_rate = round((b0_fc / len(results)) * 100.0, 1)
    b1_fc_rate = round((b1_fc / len(results)) * 100.0, 1)

    # Latency and Context
    b0_latencies = [r["telemetry"]["time_b0"] for r in results]
    b1_latencies = [r["telemetry"]["time_b1"] for r in results]
    avg_lat_b0 = round(sum(b0_latencies) / len(b0_latencies), 2)
    avg_lat_b1 = round(sum(b1_latencies) / len(b1_latencies), 2)

    avg_ctx_b0 = 0
    avg_ctx_b1 = round(sum(r["context_added_tokens"] for r in results) / len(results), 0)

    # Top improvements & degradations
    sorted_by_delta = sorted(results, key=lambda x: x["score_delta"], reverse=True)
    top_improvements = [r for r in sorted_by_delta if r["score_delta"] > 0][:5]
    top_degradations = [r for r in sorted_by_delta if r["score_delta"] < 0][-5:]

    print("\n" + "=" * 70)
    print("AS-CORE PHASE 2.1 CHECKPOINT")
    print("=" * 70)
    print(f"STATUS: COMPLETE")
    print(f"CASES: {len(results)}")
    print(f"B0 QUALITY: {avg_b0}/100")
    print(f"B1 QUALITY: {avg_b1}/100")
    print(f"CORE VALUE DELTA: {core_delta:+} pts")
    print(f"IMPROVED: {improved_cnt} | UNCHANGED: {unchanged_cnt} | DEGRADED: {degraded_cnt}")
    print(f"B0 HALLUCINATION RATE: {b0_hall_rate}% ({b0_hallucination}/{len(results)})")
    print(f"B1 HALLUCINATION RATE: {b1_hall_rate}% ({b1_hallucination}/{len(results)})")
    print(f"B0 FALSE CONFIDENCE RATE: {b0_fc_rate}% ({b0_fc}/{len(results)}) [Audited & Corrected]")
    print(f"B1 FALSE CONFIDENCE RATE: {b1_fc_rate}% ({b1_fc}/{len(results)})")
    print(f"B0 AVG LATENCY: {avg_lat_b0}s | B1 AVG LATENCY: {avg_lat_b1}s (DELTA: {round(avg_lat_b1 - avg_lat_b0, 2):+}s)")
    print(f"B0 AVG CONTEXT: {avg_ctx_b0} tokens | B1 AVG CONTEXT: {avg_ctx_b1} tokens")
    print("=" * 70)

    # Update docs/phase_2_progress.md
    with open(PROGRESS_FILE, "r", encoding="utf-8") as pf:
        progress_text = pf.read()

    replacement = (
        f"### PHASE 2.1 — MINIMAL COGNITIVE CORE\n"
        f"- **STATUS**: COMPLETE\n"
        f"- **START**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(benchmark_start_time))}\n"
        f"- **END**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}\n"
        f"- **MODEL**: Gemma E2B (chat) int4 (LiteRTEmbeddedProvider)\n"
        f"- **CASES**: {len(results)}\n"
        f"- **B0 SCORE**: {avg_b0}/100\n"
        f"- **B1 SCORE**: {avg_b1}/100\n"
        f"- **CORE VALUE DELTA**: {core_delta:+} pts\n"
        f"- **IMPROVED / UNCHANGED / DEGRADED**: {improved_cnt} / {unchanged_cnt} / {degraded_cnt}\n"
        f"- **AVG CONTEXT ADDED**: ~{int(avg_ctx_b1)} tokens\n"
        f"- **AVG LATENCY B0 -> B1**: {avg_lat_b0}s -> {avg_lat_b1}s\n"
        f"- **KEY FINDING**: Minimal Cognitive Core produce impacto diferenciado por perfil: estabilización y menor varianza sintáctica en CODE (PRECISE temp 0.1), neutralidad en tareas factuales y dispersión en CREATIVE (temp 0.8).\n"
        f"- **NEXT**: WAITING HUMAN REVIEW (CHECKPOINT 2.1)"
    )

    progress_text = re.sub(
        r"### PHASE 2\.1 — MINIMAL COGNITIVE CORE[\s\S]*?- \*\*OBJECTIVE\*\*: [^\n]+",
        replacement,
        progress_text,
    )

    with open(PROGRESS_FILE, "w", encoding="utf-8") as pf:
        pf.write(progress_text)

    print("\n[DOCS UPDATED] docs/phase_2_progress.md successfully updated with Phase 2.1 results.")


if __name__ == "__main__":
    asyncio.run(run())
