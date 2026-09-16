"""
AS-Core — Primary Regression Test: Model Residency Contract
===========================================================
Protects the residency contract for local models (Gemma E2B):
- Warmup produces real physical load before first user request
- A -> A -> A produces exactly 1 physical load
- Persistent engine identity across multiple sequential requests (id(engine1) == id(engine2) == id(engine3))
- Clean release on shutdown
"""

import asyncio
import os
import pytest

from core.engine import EngineManager
from core.hardware import detect_hardware
from providers.base import InferenceRequest
from providers.litert_embedded import LiteRTEmbeddedProvider
from providers.registry import ProviderRegistry

MODEL_E2B = r"models\gemma\gemma-3n-E2B-it-int4.litertlm"
HAS_E2B = os.path.exists(MODEL_E2B)


@pytest.mark.skipif(not HAS_E2B, reason="Requires models/gemma/gemma-3n-E2B-it-int4.litertlm")
def test_embedded_model_residency_contract():
    """Validates the core physical residency contract:
    1 physical load, engine identity preserved across requests A -> A -> A, clean shutdown.
    """
    async def _run():
        registry = ProviderRegistry()
        provider = LiteRTEmbeddedProvider(models_dir="models")
        registry.register("litert_embedded", provider)
        await registry.set_active("litert_embedded")

        engine = EngineManager(
            provider_registry=registry,
            hardware_info=detect_hardware(),
            max_vram_mb=4000,
        )
        engine.register_model(
            model_id="chat",
            model_path=MODEL_E2B,
            model_type="general",
            estimated_vram_mb=1500,
            provider_id="litert_embedded",
        )

        await engine.start()

        # Step 1: Warmup test
        assert provider._engine is None
        assert not await provider.is_model_loaded("chat")

        await engine.warmup_model("chat")

        assert await provider.is_model_loaded("chat")
        assert provider._engine is not None
        warmup_engine_id = id(provider._engine)

        # Step 2: Sequential requests A -> A -> A
        req1 = InferenceRequest(prompt="Say 1", model_id="chat", stream=False, max_tokens=10)
        res1 = await engine.generate(req1)
        engine_id_1 = id(provider._engine)
        assert engine_id_1 == warmup_engine_id, "Request 1 did not reuse warmup engine!"

        req2 = InferenceRequest(prompt="Say 2", model_id="chat", stream=False, max_tokens=10)
        res2 = await engine.generate(req2)
        engine_id_2 = id(provider._engine)
        assert engine_id_2 == engine_id_1, "Request 2 did not reuse resident engine!"

        req3 = InferenceRequest(prompt="Say 3", model_id="chat", stream=False, max_tokens=10)
        res3 = await engine.generate(req3)
        engine_id_3 = id(provider._engine)
        assert engine_id_3 == engine_id_1, "Request 3 did not reuse resident engine!"

        # Step 3: Clean shutdown
        await engine.stop()
        assert provider._engine is None, "Engine was not released on shutdown!"
        assert not await provider.is_model_loaded("chat")

    asyncio.run(_run())


def test_cli_lacks_physical_residency():
    """Demonstrates why LiteRTCLIProvider caused the regression:
    load_model only registers a file path string without any in-memory engine,
    and each generation spawns a new subprocess instead of reusing a resident engine.
    """
    from providers.litert_cli import LiteRTCLIProvider

    cli_provider = LiteRTCLIProvider()
    async def _test():
        await cli_provider.load_model("chat", MODEL_E2B)
        # load_model does NOT load an in-memory engine
        assert getattr(cli_provider, "_engine", None) is None
        # is_model_loaded is merely a string check in _model_refs
        assert await cli_provider.is_model_loaded("chat")
        assert cli_provider._spawn_counts.get("chat", 0) == 0

    asyncio.run(_test())

