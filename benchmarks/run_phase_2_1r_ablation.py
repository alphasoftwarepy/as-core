"""
AS-Core — Fase 2.1R: Minimal Cognitive Core — 5-Step Reduction Audit
=============================================================================
Executes controlled ablation variants on a representative Reduction Set
(11 cases) to determine whether the value of B1 can be preserved or improved
with less context, lower complexity, and reduced latency.

Isolation:
- Gemma E2B (chat) int4 via litert_embedded on GPU WebGPU.
- Constant hardware & runtime lifecycle.
- NO RAG, NO Graph, NO Memory, NO Skills, NO Tools, NO Web, NO Documents.
- Hard freeze on production code.
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

from api.main import app, lifespan
from core.hardware import get_ram_available_mb, get_vram_free_mb
from providers.base import InferenceRequest

DATASET_PATH = ROOT / "benchmarks" / "phase_2_core_dataset.json"
B0_RESULTS_PATH = ROOT / "benchmarks" / "results" / "phase_2_0_core_results.json"
B1_RESULTS_PATH = ROOT / "benchmarks" / "results" / "phase_2_1_core_results.json"
ABLATION_RESULTS_PATH = ROOT / "benchmarks" / "results" / "phase_2_1r_reduction_results.json"

TIMEOUT_SECONDS = 75.0

# 11-Case Representative Reduction Set
REDUCTION_SET_IDS = [
    "FACT-01",  # Facts / Physics (Placas tectónicas fosas Marianas)
    "FACT-02",  # Geography Boundary Trap (Asunción Distrito Capital)
    "GEN-07",   # Hallucination Trap (San Veridia país ficticio)
    "BIZ-05",   # Business Negotiation / Scope Creep (Precheck Target)
    "MKT-01",   # Creative / Marketing Slogans (Strict constraint: <=7 words)
    "RSN-03",   # Logic / Inverse Proportion (4 pintores vs 8 pintores)
    "DATA-01",  # Structured Extraction / Data Formatting (JSON extraction)
    "PROG-01",  # Pure Code Generation (HTML5 page or function)
    "WRIT-01",  # Business Writing / Apology Email
    "OFF-03",   # Office Table Generation (Markdown table from unformatted text)
    "BIZ-04",   # Business Conceptual Analysis (FODA Matrix)
]

CASE_PROFILE_MAP = {
    "FACT-01": "AUTO",
    "FACT-02": "AUTO",
    "GEN-07": "AUTO",
    "BIZ-05": "BALANCED",
    "MKT-01": "CREATIVE",
    "RSN-03": "BALANCED",
    "DATA-01": "BALANCED",
    "PROG-01": "CODE",
    "WRIT-01": "BALANCED",
    "OFF-03": "BALANCED",
    "BIZ-04": "BALANCED",
}

PRESETS = {
    "PRECISE": {"temperature": 0.1, "top_k": 10, "top_p": 0.9, "max_tokens": 4096},
    "BALANCED": {"temperature": 0.5, "top_k": 40, "top_p": 0.95, "max_tokens": 4096},
    "CREATIVE": {"temperature": 0.8, "top_k": 50, "top_p": 1.0, "max_tokens": 5120},
}

PROFILE_TO_PRESET = {
    "CODE": "PRECISE",
    "BALANCED": "BALANCED",
    "CREATIVE": "CREATIVE",
    "AUTO": "BALANCED",
}

GENERAL_PROMPT = (
    "Eres un asistente de inteligencia artificial directo, táctico y orientado a resultados.\n"
    "Analiza la consulta de manera objetiva y clara.\n"
    "Si el usuario adjunta documentos, utilízalos como tu fuente primaria de información para responder, resumir o explicar su contenido.\n"
    "Si no hay documentos adjuntos, responde la consulta de manera normal.\n"
    "No fuerces perspectivas de negocio, ventas, marketing o programación a menos que sea necesario."
)

SOFTWARE_PROMPT = (
    "Eres un desarrollador de software experto y arquitecto técnico.\n"
    "Analiza el problema y diseña una solución robusta y eficiente.\n"
    "Genera código limpio, tipado y bien estructurado, siguiendo las mejores prácticas del lenguaje solicitado.\n"
    "Incluye explicaciones técnicas breves y concisas cuando sea pertinente.\n"
    "No fuerces perspectivas de negocio o ventas a menos que se soliciten explícitamente."
)

MINIMAL_CORE_PROMPT = (
    "Responde en español de forma directa, precisa y objetiva. "
    "Cumple estrictamente las restricciones de formato e instrucciones indicadas."
)


def evaluate_response_audited(case: Dict[str, Any], response_text: str) -> Dict[str, Any]:
    """
    Audited evaluator enforcing format constraints and penalizing code generation
    when natural language correspondence is requested (e.g., BIZ-05).
    """
    from benchmarks.run_phase_2_0_baseline import evaluate_response
    res = evaluate_response(case, response_text)
    cid = case["id"]
    clean = response_text.strip()

    # BIZ-05 Audit Correction: penalize if Python script/code block is generated
    # instead of the requested brief formal email.
    if cid == "BIZ-05":
        if "```" in clean or "def " in clean or "import " in clean:
            dims = res.get("dimensions", {})
            dims["instruction"] = min(dims.get("instruction", 4), 2)
            dims["format_safety"] = min(dims.get("format_safety", 4), 2)
            res["error_codes"].append("E4 — FORMAT FAILURE (Code block generated instead of formal email text)")
            total = sum(dims.values())
            res["dimensions"] = dims
            res["dimension_sum"] = total
            res["score_normalized"] = round((total / 24) * 100, 1)
            res["label"] = "FAIL" if res["score_normalized"] < 50 else ("PARTIAL" if res["score_normalized"] < 80 else "PASS")

    return res


def is_true_false_confidence(cid: str, eval_res: Dict[str, Any], text: str) -> bool:
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


def build_variant_config(variant_id: str, case: Dict[str, Any]) -> Dict[str, Any]:
    cid = case["id"]
    profile = CASE_PROFILE_MAP.get(cid, "AUTO")
    preset_name = PROFILE_TO_PRESET.get(profile, "BALANCED")
    preset = PRESETS[preset_name]

    if variant_id == "V2_NO_LANG_ANCHOR":
        base_prompt = SOFTWARE_PROMPT if profile == "CODE" else GENERAL_PROMPT
        # Context block simulation if keyword matched
        context_block = ""
        if cid == "BIZ-05":
            context_block = "\n\n## CONTEXTO\nHabilidad activa: programming"
        system_prompt = f"{base_prompt}{context_block}"
        tokens_added = len(system_prompt.split())

    elif variant_id == "V3_NO_CONTEXT_BLOCK":
        base_prompt = SOFTWARE_PROMPT if profile == "CODE" else GENERAL_PROMPT
        system_prompt = f"[LANG=ES]\n{base_prompt}"
        tokens_added = len(system_prompt.split())

    elif variant_id == "V4_PRESET_ONLY":
        system_prompt = ""
        tokens_added = 0

    elif variant_id == "V5_MINIMAL_CORE":
        system_prompt = MINIMAL_CORE_PROMPT
        tokens_added = len(system_prompt.split())

    else:
        raise ValueError(f"Unknown variant: {variant_id}")

    return {
        "system_prompt": system_prompt,
        "preset_name": preset_name,
        "preset": preset,
        "tokens_added": tokens_added,
        "profile": profile,
    }


async def run_ablation():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("=" * 75)
    print("AS-CORE — FASE 2.1R: REDUCTION AUDIT / ABLATION BENCHMARK")
    print("REDUCTION SET: 11 Representative Cases")
    print("MODEL: Gemma E2B (chat) int4 | PROVIDER: litert_embedded (GPU WebGPU)")
    print("ISOLATION: HARD FREEZE on Production Code. NO RAG/Memory/Skills/Tools.")
    print("=" * 75)

    with open(DATASET_PATH, encoding="utf-8") as f:
        full_dataset = json.load(f)
    case_map = {c["id"]: c for c in full_dataset}
    reduction_cases = [case_map[cid] for cid in REDUCTION_SET_IDS]

    with open(B0_RESULTS_PATH, encoding="utf-8") as f:
        b0_full = json.load(f)
    b0_by_id = {r["id"]: r for r in b0_full}

    with open(B1_RESULTS_PATH, encoding="utf-8") as f:
        b1_full = json.load(f)
    b1_by_id = {r["id"]: r for r in b1_full}

    # Load or initialize ablation results
    ablation_data: Dict[str, Any] = {
        "reduction_set_ids": REDUCTION_SET_IDS,
        "variants": {
            "V0_BASELINE": {},
            "V1_CURRENT_B1": {},
            "V2_NO_LANG_ANCHOR": {},
            "V3_NO_CONTEXT_BLOCK": {},
            "V4_PRESET_ONLY": {},
            "V5_MINIMAL_CORE": {},
        },
        "summary": {},
    }

    if ABLATION_RESULTS_PATH.exists():
        try:
            with open(ABLATION_RESULTS_PATH, encoding="utf-8") as f:
                ablation_data = json.load(f)
                print(f"[RESUME SUPPORT] Loaded existing ablation data from {ABLATION_RESULTS_PATH}")
        except Exception as e:
            print(f"[RESUME WARNING] Could not parse existing results: {e}")

    # Populate V0 Baseline from frozen results
    print("\n--- POPULATING V0 (FROZEN BASELINE) ---")
    for cid in REDUCTION_SET_IDS:
        b0_c = b0_by_id[cid]
        c = case_map[cid]
        eval_audited = evaluate_response_audited(c, b0_c["response"])
        is_fc = is_true_false_confidence(cid, eval_audited, b0_c["response"])
        ablation_data["variants"]["V0_BASELINE"][cid] = {
            "response": b0_c["response"],
            "score": eval_audited["score_normalized"],
            "evaluation": eval_audited,
            "latency_sec": b0_c["telemetry"]["elapsed_sec"],
            "output_tokens": len(b0_c["response"].split()),
            "context_tokens": 0,
            "is_false_confidence": is_fc,
            "hallucination": eval_audited["dimensions"]["hallucination"],
            "instruction": eval_audited["dimensions"]["instruction"],
        }
    v0_scores = [ablation_data["variants"]["V0_BASELINE"][cid]["score"] for cid in REDUCTION_SET_IDS]
    v0_avg = sum(v0_scores) / len(v0_scores)
    print(f"V0 Baseline Average on Reduction Set: {v0_avg:.1f}/100")

    # Populate V1 Current B1 from frozen results with audited BIZ-05 evaluation
    print("\n--- POPULATING V1 (FROZEN CURRENT B1 WITH AUDITED BIZ-05) ---")
    for cid in REDUCTION_SET_IDS:
        b1_c = b1_by_id[cid]
        c = case_map[cid]
        eval_audited = evaluate_response_audited(c, b1_c["b1_response"])
        is_fc = is_true_false_confidence(cid, eval_audited, b1_c["b1_response"])
        ablation_data["variants"]["V1_CURRENT_B1"][cid] = {
            "response": b1_c["b1_response"],
            "score": eval_audited["score_normalized"],
            "evaluation": eval_audited,
            "latency_sec": b1_c["telemetry"]["time_b1"],
            "output_tokens": b1_c["telemetry"]["tokens_b1"],
            "context_tokens": b1_c["context_added_tokens"],
            "is_false_confidence": is_fc,
            "hallucination": eval_audited["dimensions"]["hallucination"],
            "instruction": eval_audited["dimensions"]["instruction"],
        }
    v1_scores = [ablation_data["variants"]["V1_CURRENT_B1"][cid]["score"] for cid in REDUCTION_SET_IDS]
    v1_avg = sum(v1_scores) / len(v1_scores)
    print(f"V1 Current B1 Audited Average on Reduction Set: {v1_avg:.1f}/100")

    # Run remaining variants: V2, V3, V4, V5
    variants_to_run = [
        ("V2_NO_LANG_ANCHOR", "B1 without [LANG=ES] anchor"),
        ("V3_NO_CONTEXT_BLOCK", "B1 without ## CONTEXTO / intent keyword injection"),
        ("V4_PRESET_ONLY", "Profile Presets only (temp/top_p/top_k), ZERO system prompt"),
        ("V5_MINIMAL_CORE", "Minimal Core: Compact 35-token prompt + Profile Presets"),
    ]

    async with lifespan(app):
        engine = app.state.engine
        print(f"\n[ENGINE CONFIRMED] Model: {engine.active_model} | Physical: {engine.active_physical_model}")

        for var_id, var_desc in variants_to_run:
            print("\n" + "=" * 75)
            print(f"RUNNING VARIANT: {var_id} — {var_desc}")
            print("=" * 75)

            var_results = ablation_data["variants"].get(var_id, {})

            for case in reduction_cases:
                cid = case["id"]
                if cid in var_results and "score" in var_results[cid]:
                    print(f"  [{cid}] Already completed (Score: {var_results[cid]['score']:.1f}) -> Skipping")
                    continue

                prompt = case["prompt"]
                cfg = build_variant_config(var_id, case)
                sys_prompt = cfg["system_prompt"]
                preset = cfg["preset"]

                formatted_prompt = f"User: {prompt}\n\nAssistant:"
                req = InferenceRequest(
                    prompt=formatted_prompt,
                    model_id="chat",
                    temperature=preset["temperature"],
                    max_tokens=preset["max_tokens"],
                    top_p=preset["top_p"],
                    top_k=preset["top_k"],
                    system_prompt=sys_prompt,
                    request_id=f"ablation_{var_id}_{cid}_{uuid.uuid4().hex[:6]}",
                )

                t0 = time.time()
                res = await engine.generate(req)
                t1 = time.time()
                elapsed = round(t1 - t0, 2)
                resp_text = res.text.strip()
                tokens = len(resp_text.split())

                eval_res = evaluate_response_audited(case, resp_text)
                is_fc = is_true_false_confidence(cid, eval_res, resp_text)
                score = eval_res["score_normalized"]

                var_results[cid] = {
                    "response": resp_text,
                    "score": score,
                    "evaluation": eval_res,
                    "latency_sec": elapsed,
                    "output_tokens": tokens,
                    "context_tokens": cfg["tokens_added"],
                    "is_false_confidence": is_fc,
                    "hallucination": eval_res["dimensions"]["hallucination"],
                    "instruction": eval_res["dimensions"]["instruction"],
                }

                ablation_data["variants"][var_id] = var_results
                # Incremental persist
                with open(ABLATION_RESULTS_PATH, "w", encoding="utf-8") as f:
                    json.dump(ablation_data, f, indent=2, ensure_ascii=False)

                print(f"  [{cid}] Score: {score:4.1f} | Latency: {elapsed:5.2f}s | OutTok: {tokens:3d} | CtxTok: {cfg['tokens_added']:2d} | Label: {eval_res['label']}")

    # Compute Summary Matrix across all 6 variants
    print("\n" + "=" * 75)
    print("ABLATION BENCHMARK COMPLETE — COMPUTING REDUCTION SUMMARY MATRIX")
    print("=" * 75)

    summary: Dict[str, Any] = {}
    for vid, vdata in ablation_data["variants"].items():
        if len(vdata) < len(REDUCTION_SET_IDS):
            continue
        scores = [vdata[cid]["score"] for cid in REDUCTION_SET_IDS]
        latencies = [vdata[cid]["latency_sec"] for cid in REDUCTION_SET_IDS]
        ctx_tokens = [vdata[cid]["context_tokens"] for cid in REDUCTION_SET_IDS]
        out_tokens = [vdata[cid]["output_tokens"] for cid in REDUCTION_SET_IDS]
        fcs = sum(1 for cid in REDUCTION_SET_IDS if vdata[cid]["is_false_confidence"])
        halls = sum(1 for cid in REDUCTION_SET_IDS if vdata[cid]["hallucination"] <= 1)
        inst_violations = sum(1 for cid in REDUCTION_SET_IDS if vdata[cid]["instruction"] <= 2)

        avg_score = round(sum(scores) / len(scores), 2)
        avg_lat = round(sum(latencies) / len(latencies), 2)
        avg_ctx = round(sum(ctx_tokens) / len(ctx_tokens), 1)
        avg_out = round(sum(out_tokens) / len(out_tokens), 1)

        summary[vid] = {
            "quality_score": avg_score,
            "avg_latency_sec": avg_lat,
            "avg_context_tokens": avg_ctx,
            "avg_output_tokens": avg_out,
            "false_confidence_count": fcs,
            "hallucination_count": halls,
            "instruction_violations": inst_violations,
            "delta_vs_v0_score": round(avg_score - summary.get("V0_BASELINE", {}).get("quality_score", avg_score), 2),
            "delta_vs_v0_lat": round(avg_lat - summary.get("V0_BASELINE", {}).get("avg_latency_sec", avg_lat), 2),
            "delta_vs_v1_score": round(avg_score - summary.get("V1_CURRENT_B1", {}).get("quality_score", avg_score), 2),
            "delta_vs_v1_lat": round(avg_lat - summary.get("V1_CURRENT_B1", {}).get("avg_latency_sec", avg_lat), 2),
        }

    ablation_data["summary"] = summary
    with open(ABLATION_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(ablation_data, f, indent=2, ensure_ascii=False)

    print("\nSUMMARY TABLE (Reduction Set N=11):")
    print(f"{'VARIANT':<22} | {'QUALITY':<7} | {'LATENCY':<7} | {'CTX TOK':<7} | {'OUT TOK':<7} | {'FC':<3} | {'D_V0':<6} | {'D_V1':<6}")
    print("-" * 80)
    for vid, sm in summary.items():
        print(f"{vid:<22} | {sm['quality_score']:<7.1f} | {sm['avg_latency_sec']:<5.2f}s  | {sm['avg_context_tokens']:<7.0f} | {sm['avg_output_tokens']:<7.0f} | {sm['false_confidence_count']:<3d} | {sm['delta_vs_v0_score']:<+6.1f} | {sm['delta_vs_v1_score']:<+6.1f}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_ablation())
