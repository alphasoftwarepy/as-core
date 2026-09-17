"""Audit-only capability evidence harness for AS-Core Phase 1.2.

This module is intentionally isolated from production routing and lifecycle code.
It consumes public runtime interfaces without modifying EngineManager, providers,
SmartRouter, the coordinator, skills, or the agent loop.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.engine import EngineManager
from core.hardware import detect_hardware, get_ram_available_mb, get_vram_free_mb
from providers.base import InferenceRequest
from providers.litert_embedded import LiteRTEmbeddedProvider
from providers.llamacpp_provider import LlamaCppProvider
from providers.registry import ProviderRegistry
from router.smart_router import SmartRouter


DATASET_PATH = ROOT / "benchmarks" / "phase_1_2_dataset.json"
LLAMA_SERVER = ROOT / "moe_poc" / "bins" / "llama-server.exe"

MODELS = {
    "e2b": {
        "model_id": "audit-e2b",
        "physical_name": "Gemma 3n E2B int4",
        "provider": "litert_embedded",
        "path": ROOT / "models" / "gemma" / "gemma-3n-E2B-it-int4.litertlm",
        "estimated_vram_mb": 1500,
    },
    "olmoe": {
        "model_id": "audit-olmoe",
        "physical_name": "OLMoE-1B-7B-0924-Instruct Q4_K_M",
        "provider": "llamacpp",
        "path": ROOT / "moe_poc" / "models" / "OLMoE-1B-7B-0924-Instruct-Q4_K_M.gguf",
        "estimated_vram_mb": 3900,
    },
    "qwen": {
        "model_id": "audit-qwen",
        "physical_name": "Qwen1.5-MoE-A2.7B Q4_K_M",
        "provider": "llamacpp",
        "path": ROOT / "moe_poc" / "models" / "qwen1.5-moe-a2.7b-q4_k_m.gguf",
        "estimated_vram_mb": 3893,
    },
}


def _clean_text(text: str) -> str:
    return text.strip().replace("\r\n", "\n")


def _json_value(text: str) -> Any:
    value = _clean_text(text)
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    return json.loads(value)


def _nested_get(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(path)
        current = current[part]
    return current


def _python_source(text: str) -> str:
    value = _clean_text(text)
    match = re.search(r"```(?:python)?\s*(.*?)```", value, flags=re.I | re.S)
    return match.group(1).strip() if match else value


def _check(text: str, spec: dict[str, Any]) -> tuple[bool, str]:
    kind = spec["type"]
    clean = _clean_text(text)
    try:
        if kind == "exact":
            ok = clean == spec["value"]
        elif kind == "contains_ci":
            ok = str(spec["value"]).casefold() in clean.casefold()
        elif kind == "not_contains_ci":
            ok = str(spec["value"]).casefold() not in clean.casefold()
        elif kind == "max_words":
            ok = len(re.findall(r"\S+", clean)) <= int(spec["value"])
        elif kind == "bullet_count":
            count = sum(bool(re.match(r"^\s*(?:[-*•]|\d+[.)])\s+", line)) for line in clean.splitlines())
            ok = count == int(spec["value"])
        elif kind == "json_valid":
            _json_value(clean)
            ok = True
        elif kind == "json_field":
            ok = _nested_get(_json_value(clean), spec["path"]) == spec["value"]
        elif kind == "json_array_exact":
            ok = _json_value(clean) == spec["value"]
        elif kind == "python_ast":
            tree = ast.parse(_python_source(clean))
            functions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            target = next((n for n in functions if n.name == spec["function"]), None)
            has_import = any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree))
            has_append = any(isinstance(n, ast.Attribute) and n.attr == "append" for n in ast.walk(tree))
            has_branch = any(isinstance(n, ast.If) for n in ast.walk(tree))
            ok = target is not None and not has_import and has_append and has_branch
        elif kind == "sql_contract":
            sql = re.sub(r"```(?:sql)?|```", " ", clean, flags=re.I).casefold()
            requirements = [
                r"select\s+customer_id",
                r"sum\s*\(\s*amount\s*\)\s+as\s+total_paid",
                r"from\s+payments",
                r"status\s*=\s*['\"]paid['\"]",
                r"group\s+by\s+customer_id",
                r"having\s+(?:sum\s*\(\s*amount\s*\)|total_paid)\s*>=\s*10000",
                r"order\s+by\s+total_paid\s+desc",
            ]
            ok = all(re.search(pattern, sql, flags=re.I) for pattern in requirements)
        elif kind == "sql_only":
            sql = clean
            fenced = re.fullmatch(r"```(?:sql)?\s*(.*?)\s*```", sql, flags=re.I | re.S)
            if fenced:
                sql = fenced.group(1).strip()
            ok = bool(re.fullmatch(r"select\b.*(?:;)?", sql, flags=re.I | re.S))
        else:
            raise ValueError(f"Unknown check type: {kind}")
    except Exception as exc:
        return False, f"{kind}: {type(exc).__name__}: {exc}"
    return ok, f"{kind}: {'PASS' if ok else 'FAIL'}"


def evaluate(text: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = []
    passed = 0
    fatal_failed = False
    for spec in checks:
        ok, detail = _check(text, spec)
        evidence.append({"check": spec, "passed": ok, "detail": detail})
        passed += int(ok)
        fatal_failed = fatal_failed or (bool(spec.get("fatal")) and not ok)
    if passed == len(checks):
        status = "PASS"
    elif passed > 0 and not fatal_failed:
        status = "PARTIAL"
    else:
        status = "FAIL"
    return {"status": status, "checks_passed": passed, "checks_total": len(checks), "evidence": evidence}


def machine_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "vram_free_mb": get_vram_free_mb(),
        "ram_available_mb": get_ram_available_mb(),
    }
    try:
        raw = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,driver_version",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        ).strip()
        name, total, used, free, driver = [part.strip() for part in raw.split(",", 4)]
        snapshot.update(
            {
                "gpu": name,
                "vram_total_mb": int(total),
                "vram_used_mb": int(used),
                "vram_free_mb_nvidia": int(free),
                "driver": driver,
            }
        )
    except Exception as exc:
        snapshot["nvidia_smi_error"] = f"{type(exc).__name__}: {exc}"
    return snapshot


async def build_engine(model_key: str) -> tuple[EngineManager, Any, dict[str, Any]]:
    cfg = MODELS[model_key]
    if not cfg["path"].exists():
        raise FileNotFoundError(cfg["path"])
    registry = ProviderRegistry()
    if cfg["provider"] == "litert_embedded":
        provider = LiteRTEmbeddedProvider(models_dir=str(ROOT / "models"))
        registry.register("litert_embedded", provider)
    else:
        if not LLAMA_SERVER.exists():
            raise FileNotFoundError(LLAMA_SERVER)
        provider = LlamaCppProvider(
            server_bin_path=str(LLAMA_SERVER),
            host="127.0.0.1",
            port=8892,
            n_gpu_layers=10,
            context_size=2048,
        )
        registry.register("llamacpp", provider)
    await registry.set_active(cfg["provider"])
    engine = EngineManager(
        provider_registry=registry,
        hardware_info=detect_hardware(),
        max_vram_mb=3900,
        anti_oom_threshold_mb=300,
        runtime_mode="single_user",
    )
    engine.register_model(
        cfg["model_id"],
        str(cfg["path"]),
        model_type="audit",
        estimated_vram_mb=cfg["estimated_vram_mb"],
        provider_id=cfg["provider"],
    )
    await engine.start()
    return engine, provider, cfg


async def run_model(model_key: str, dataset: dict[str, Any]) -> dict[str, Any]:
    before_suite = machine_snapshot()
    engine, provider, cfg = await build_engine(model_key)
    cases = []
    try:
        for index, case in enumerate(dataset["cases"]):
            before = machine_snapshot()
            start = time.perf_counter()
            first_text_at = None
            text_parts: list[str] = []
            finish_reason = None
            technical_error = None
            try:
                request = InferenceRequest(
                    prompt=case["input"],
                    model_id=cfg["model_id"],
                    temperature=0.0,
                    max_tokens=case["max_tokens"],
                    top_p=1.0,
                    top_k=1,
                    request_id=f"phase12-{model_key}-{case['id']}",
                )
                async for chunk in engine.generate_stream(request):
                    if chunk.text:
                        if first_text_at is None:
                            first_text_at = time.perf_counter()
                        text_parts.append(chunk.text)
                    if chunk.finish_reason:
                        finish_reason = chunk.finish_reason
            except Exception as exc:
                technical_error = f"{type(exc).__name__}: {exc}"
            end = time.perf_counter()
            response = "".join(text_parts)
            during = machine_snapshot()
            if technical_error:
                evaluation = {"status": "BLOCKED", "reason": technical_error, "evidence": []}
            else:
                evaluation = evaluate(response, case["checks"])
            metrics = await provider.get_metrics()
            cases.append(
                {
                    "id": case["id"],
                    "capability": case["capability"],
                    "state": "cold" if index == 0 else "warm",
                    "response": response,
                    "finish_reason": finish_reason,
                    "evaluation": evaluation,
                    "operational": {
                        "ttft_ms": round((first_text_at - start) * 1000, 2) if first_text_at else None,
                        "elapsed_ms": round((end - start) * 1000, 2),
                        "provider_metrics": metrics,
                        "before": before,
                        "during_or_immediately_after": during,
                    },
                }
            )
    finally:
        await engine.stop()
    return {
        "model_key": model_key,
        "model_id": cfg["model_id"],
        "physical_name": cfg["physical_name"],
        "physical_path": str(cfg["path"]),
        "provider": cfg["provider"],
        "machine_before_suite": before_suite,
        "machine_after_suite": machine_snapshot(),
        "cases": cases,
    }


def audit_router(dataset: dict[str, Any]) -> list[dict[str, str]]:
    router = SmartRouter(chat_model="chat", coding_model="code", reasoning_model="reasoning")
    rows = []
    for case in dataset["cases"]:
        model_id, _ = router.route(case["input"], explicit_model="auto")
        rows.append(
            {
                "id": case["id"],
                "capability": case["capability"],
                "router_result": model_id,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=sorted(MODELS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    result = {
        "schema_version": 1,
        "dataset_id": dataset["dataset_id"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "router_audit": audit_router(dataset),
        "model_evidence": asyncio.run(run_model(args.model, dataset)),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "model": args.model, "cases": len(dataset["cases"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
