"""
AS-Core — Physical Cross-Provider Transition Test (0.2C.2B)
============================================================
Physical execution of:
E2B (LiteRTEmbeddedProvider) -> MoE (LlamaCppProvider) -> E2B (LiteRTEmbeddedProvider)

Validates:
- Release of source provider resources
- Initialization and generation of target provider (llama-server daemon)
- Full lifecycle swap across distinct physical model architectures and providers
- Clean shutdown
"""

import asyncio
import os
import sys
import time
import psutil
import pytest

# Ensure litert-lm site-packages is in path
LITERT_LM_PATH = r"C:\Users\rva10\AppData\Roaming\uv\tools\litert-lm\Lib\site-packages"
if LITERT_LM_PATH not in sys.path:
    sys.path.append(LITERT_LM_PATH)

from core.engine import EngineManager
from core.hardware import detect_hardware, get_vram_free_mb, get_ram_available_mb
from providers.base import InferenceRequest
from providers.litert_embedded import LiteRTEmbeddedProvider
from providers.llamacpp_provider import LlamaCppProvider
from providers.registry import ProviderRegistry

E2B_PATH = os.path.abspath("models/gemma/gemma-3n-E2B-it-int4.litertlm")
MOE_BIN = os.path.abspath("moe_poc/bins/llama-server.exe")
OLMOE_PATH = os.path.abspath("moe_poc/models/OLMoE-1B-7B-0924-Instruct-Q4_K_M.gguf")

HAS_PREREQS = os.path.exists(E2B_PATH) and os.path.exists(MOE_BIN) and os.path.exists(OLMOE_PATH)


def _mem():
    proc = psutil.Process()
    return {
        "vram_free_mb": get_vram_free_mb(),
        "ram_avail_mb": get_ram_available_mb(),
        "proc_rss_mb": round(proc.memory_info().rss / (1024 * 1024), 1),
    }


@pytest.mark.skipif(not HAS_PREREQS, reason="Requires E2B model, llama-server.exe, and OLMoE model")
def test_physical_cross_provider_e2b_moe_cycle():
    """Executes real physical cross-provider transitions:
    E2B (litert_embedded) -> MoE (llamacpp) -> E2B (litert_embedded)
    """
    async def _run():
        registry = ProviderRegistry()
        litert_p = LiteRTEmbeddedProvider(models_dir="models")
        llamacpp_p = LlamaCppProvider(
            server_bin_path=MOE_BIN,
            port=8794,
            n_gpu_layers=0,
            context_size=512,
        )
        registry.register("litert_embedded", litert_p)
        registry.register("llamacpp", llamacpp_p)
        await registry.set_active("litert_embedded")

        engine = EngineManager(
            provider_registry=registry,
            hardware_info=detect_hardware(),
            max_vram_mb=3500,
            anti_oom_threshold_mb=300,
        )

        engine.register_model(
            "e2b-chat",
            E2B_PATH,
            model_type="general",
            estimated_vram_mb=1500,
            provider_id="litert_embedded",
        )
        engine.register_model(
            "olmoe-moe",
            OLMOE_PATH,
            model_type="moe",
            estimated_vram_mb=2000,
            provider_id="llamacpp",
        )

        # ── STEP 1: E2B Generate ─────────────────────────
        mem_init = _mem()
        t0 = time.time()
        req1 = InferenceRequest(prompt="Hello from E2B", model_id="e2b-chat", max_tokens=10)
        res1 = await engine.generate(req1)
        t_e2b_1 = time.time() - t0

        assert res1.finish_reason in ("stop", "length")
        assert len(res1.text) > 0
        assert engine.active_model == "e2b-chat"
        assert await litert_p.is_model_loaded("e2b-chat")
        assert not await llamacpp_p.is_model_loaded("olmoe-moe")

        # ── STEP 2: Swap E2B -> MoE ──────────────────────
        t0 = time.time()
        req2 = InferenceRequest(prompt="Hello from MoE", model_id="olmoe-moe", max_tokens=10)
        res2 = await engine.generate(req2)
        t_swap_to_moe = time.time() - t0

        assert res2.finish_reason in ("stop", "length")
        assert len(res2.text) > 0
        assert engine.active_model == "olmoe-moe"
        assert not await litert_p.is_model_loaded("e2b-chat"), "E2B was not unloaded during swap!"
        assert await llamacpp_p.is_model_loaded("olmoe-moe"), "MoE was not loaded!"
        assert llamacpp_p._proc is not None and llamacpp_p._proc.poll() is None

        # ── STEP 3: Swap MoE -> E2B ──────────────────────
        t0 = time.time()
        req3 = InferenceRequest(prompt="Hello again from E2B", model_id="e2b-chat", max_tokens=10)
        res3 = await engine.generate(req3)
        t_swap_to_e2b = time.time() - t0

        assert res3.finish_reason in ("stop", "length")
        assert len(res3.text) > 0
        assert engine.active_model == "e2b-chat"
        assert llamacpp_p._proc is None or llamacpp_p._proc.poll() is not None, "MoE daemon should be stopped!"
        assert await litert_p.is_model_loaded("e2b-chat"), "E2B was not reloaded!"

        # ── STEP 4: Clean Stop ───────────────────────────
        await engine.stop()
        assert engine.active_model is None
        assert engine.active_physical_model is None
        assert not await litert_p.is_model_loaded("e2b-chat")
        assert not await llamacpp_p.is_model_loaded("olmoe-moe")

    asyncio.run(_run())
