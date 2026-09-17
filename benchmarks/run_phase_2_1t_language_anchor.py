"""
AS-Core — Fase 2.1T: Language Anchor Micro-Ablation Runner
=============================================================================
Direct controlled comparison on the 11-case Reduction Set:
Condition A: [LANG=ES] + Root Prompt
Condition B: Root Prompt (Without [LANG=ES])

Constant:
- Resident Gemma E2B (chat) int4 on GPU WebGPU
- Exactly the same profiles and presets
- Exactly the same cases and prompts
- Exactly the same root prompt (GENERAL_PROMPT / SOFTWARE_PROMPT)
- Isolated: NO RAG, NO Graph, NO Memory, NO Skills, NO Tools
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.main import app, lifespan
from core.hardware import get_ram_available_mb, get_vram_free_mb
from providers.base import InferenceRequest
from benchmarks.run_phase_2_1r_ablation import (
    evaluate_response_audited,
    is_true_false_confidence,
    REDUCTION_SET_IDS,
    CASE_PROFILE_MAP,
    PRESETS,
    PROFILE_TO_PRESET,
    GENERAL_PROMPT,
    SOFTWARE_PROMPT,
)

DATASET_PATH = ROOT / "benchmarks" / "phase_2_core_dataset.json"
RESULTS_PATH = ROOT / "benchmarks" / "results" / "phase_2_1t_language_anchor_results.json"


def detect_language_drift(text: str) -> bool:
    """Checks if the response drifted to English or contains non-Spanish dominant text."""
    clean = text.lower()
    english_markers = [
        " the ", " and ", " is ", " this ", " that ", " please ", " sure, ",
        " here is ", " here are ", " regarding ", " dear ", " sincerely "
    ]
    english_hits = sum(1 for m in english_markers if m in clean)
    # If 3 or more typical English syntax markers appear in a text that should be Spanish
    return english_hits >= 3


async def run_micro_ablation():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("=" * 75)
    print("AS-CORE — FASE 2.1T: LANGUAGE ANCHOR MICRO-ABLATION")
    print("CONDITION A: [LANG=ES] + Root Prompt")
    print("CONDITION B: Root Prompt Only (No Language Anchor)")
    print("REDUCTION SET: 11 Frozen Cases")
    print("MODEL: Gemma E2B (chat) int4 | PROVIDER: litert_embedded (GPU WebGPU)")
    print("=" * 75)

    with open(DATASET_PATH, encoding="utf-8") as f:
        full_dataset = json.load(f)
    case_map = {c["id"]: c for c in full_dataset}
    reduction_cases = [case_map[cid] for cid in REDUCTION_SET_IDS]

    results: Dict[str, Any] = {
        "CONDITION_A_WITH_LANG": {},
        "CONDITION_B_WITHOUT_LANG": {},
    }

    async with lifespan(app):
        engine = app.state.engine
        print(f"[ENGINE CONFIRMED] Model: {engine.active_model} | Physical: {engine.active_physical_model}")

        conditions = [
            ("CONDITION_A_WITH_LANG", True, "[LANG=ES] + Root Prompt"),
            ("CONDITION_B_WITHOUT_LANG", False, "Root Prompt Only"),
        ]

        for cond_id, include_anchor, cond_desc in conditions:
            print("\n" + "=" * 75)
            print(f"RUNNING {cond_id}: {cond_desc}")
            print("=" * 75)

            cond_data = {}
            for case in reduction_cases:
                cid = case["id"]
                prompt = case["prompt"]
                profile = CASE_PROFILE_MAP.get(cid, "AUTO")
                preset_name = PROFILE_TO_PRESET.get(profile, "BALANCED")
                preset = PRESETS[preset_name]

                base_prompt = SOFTWARE_PROMPT if profile == "CODE" else GENERAL_PROMPT
                if include_anchor:
                    system_prompt = f"[LANG=ES]\n{base_prompt}"
                    anchor_tokens = 4
                else:
                    system_prompt = base_prompt
                    anchor_tokens = 0

                ctx_tokens = len(system_prompt.split())
                formatted_prompt = f"User: {prompt}\n\nAssistant:"

                req = InferenceRequest(
                    prompt=formatted_prompt,
                    model_id="chat",
                    temperature=preset["temperature"],
                    max_tokens=preset["max_tokens"],
                    top_p=preset["top_p"],
                    top_k=preset["top_k"],
                    system_prompt=system_prompt,
                    request_id=f"lang_{cond_id}_{cid}_{uuid.uuid4().hex[:6]}",
                )

                t0 = time.time()
                first_token_time = None
                text_chunks = []
                async for chunk in engine.generate_stream(req):
                    if chunk.text:
                        if first_token_time is None:
                            first_token_time = time.time()
                        text_chunks.append(chunk.text)
                t1 = time.time()

                ttft_sec = round((first_token_time - t0), 3) if first_token_time else 0.0
                elapsed = round(t1 - t0, 2)
                resp_text = "".join(text_chunks).strip()
                out_tokens = len(resp_text.split())

                eval_res = evaluate_response_audited(case, resp_text)
                is_fc = is_true_false_confidence(cid, eval_res, resp_text)
                has_drift = detect_language_drift(resp_text)
                echoed_tag = "[LANG=ES]" in resp_text

                cond_data[cid] = {
                    "score": eval_res["score_normalized"],
                    "latency_sec": elapsed,
                    "ttft_sec": ttft_sec,
                    "context_tokens": ctx_tokens,
                    "output_tokens": out_tokens,
                    "is_false_confidence": is_fc,
                    "language_drift": has_drift,
                    "echoed_tag": echoed_tag,
                    "hallucination": eval_res["dimensions"]["hallucination"],
                    "instruction": eval_res["dimensions"]["instruction"],
                    "response": resp_text,
                }

                print(f"  [{cid:8}] Score: {eval_res['score_normalized']:4.1f} | Lat: {elapsed:5.2f}s | TTFT: {ttft_sec*1000:5.0f}ms | OutTok: {out_tokens:3d} | EchoedTag: {echoed_tag} | Drift: {has_drift}")

            results[cond_id] = cond_data

    # Consolidation
    summary = {}
    for cond_id in ["CONDITION_A_WITH_LANG", "CONDITION_B_WITHOUT_LANG"]:
        cdata = results[cond_id]
        scores = [cdata[cid]["score"] for cid in REDUCTION_SET_IDS]
        lats = [cdata[cid]["latency_sec"] for cid in REDUCTION_SET_IDS]
        ttfts = [cdata[cid]["ttft_sec"] for cid in REDUCTION_SET_IDS]
        ctxs = [cdata[cid]["context_tokens"] for cid in REDUCTION_SET_IDS]
        outs = [cdata[cid]["output_tokens"] for cid in REDUCTION_SET_IDS]
        insts = [cdata[cid]["instruction"] for cid in REDUCTION_SET_IDS]
        fcs = sum(1 for cid in REDUCTION_SET_IDS if cdata[cid]["is_false_confidence"])
        drifts = sum(1 for cid in REDUCTION_SET_IDS if cdata[cid]["language_drift"])
        echos = sum(1 for cid in REDUCTION_SET_IDS if cdata[cid]["echoed_tag"])

        summary[cond_id] = {
            "avg_score": round(sum(scores) / len(scores), 2),
            "avg_latency": round(sum(lats) / len(lats), 2),
            "avg_ttft_sec": round(sum(ttfts) / len(ttfts), 3),
            "avg_context_tokens": round(sum(ctxs) / len(ctxs), 1),
            "avg_output_tokens": round(sum(outs) / len(outs), 1),
            "avg_instruction": round(sum(insts) / len(insts), 2),
            "false_confidence_count": fcs,
            "language_drift_count": drifts,
            "echoed_tag_count": echos,
        }

    final_payload = {
        "summary": summary,
        "details": results,
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 75)
    print("FASE 2.1T COMPARATIVE RESULTS (Reduction Set N=11):")
    print("=" * 75)
    print(f"{'METRIC':<25} | {'A: WITH [LANG=ES]':<20} | {'B: WITHOUT [LANG=ES]':<20} | {'DELTA (B - A)':<15}")
    print("-" * 85)
    sm_a = summary["CONDITION_A_WITH_LANG"]
    sm_b = summary["CONDITION_B_WITHOUT_LANG"]
    print(f"{'Quality Score':<25} | {sm_a['avg_score']:<20.2f} | {sm_b['avg_score']:<20.2f} | {sm_b['avg_score'] - sm_a['avg_score']:<+15.2f}")
    print(f"{'Avg Latency (s)':<25} | {sm_a['avg_latency']:<20.2f} | {sm_b['avg_latency']:<20.2f} | {sm_b['avg_latency'] - sm_a['avg_latency']:<+15.2f}")
    print(f"{'Avg TTFT (ms)':<25} | {sm_a['avg_ttft_sec']*1000:<20.1f} | {sm_b['avg_ttft_sec']*1000:<20.1f} | {(sm_b['avg_ttft_sec'] - sm_a['avg_ttft_sec'])*1000:<+15.1f}")
    print(f"{'Context Tokens':<25} | {sm_a['avg_context_tokens']:<20.1f} | {sm_b['avg_context_tokens']:<20.1f} | {sm_b['avg_context_tokens'] - sm_a['avg_context_tokens']:<+15.1f}")
    print(f"{'Output Tokens':<25} | {sm_a['avg_output_tokens']:<20.1f} | {sm_b['avg_output_tokens']:<20.1f} | {sm_b['avg_output_tokens'] - sm_a['avg_output_tokens']:<+15.1f}")
    print(f"{'Instruction Score (0-4)':<25} | {sm_a['avg_instruction']:<20.2f} | {sm_b['avg_instruction']:<20.2f} | {sm_b['avg_instruction'] - sm_a['avg_instruction']:<+15.2f}")
    print(f"{'Language Drift (Count)':<25} | {sm_a['language_drift_count']:<20d} | {sm_b['language_drift_count']:<20d} | {sm_b['language_drift_count'] - sm_a['language_drift_count']:<+15d}")
    print(f"{'Echoed Tag Leakage':<25} | {sm_a['echoed_tag_count']:<20d} | {sm_b['echoed_tag_count']:<20d} | {sm_b['echoed_tag_count'] - sm_a['echoed_tag_count']:<+15d}")
    print(f"{'False Confidence (N)':<25} | {sm_a['false_confidence_count']:<20d} | {sm_b['false_confidence_count']:<20d} | {sm_b['false_confidence_count'] - sm_a['false_confidence_count']:<+15d}")
    print("=" * 85)


if __name__ == "__main__":
    asyncio.run(run_micro_ablation())
