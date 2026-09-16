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


@pytest.mark.skipif(not HAS_E2B, reason="Requires models/gemma/gemma-3n-E2B-it-int4.litertlm")
def test_logical_alias_reuses_physical_model():
    """Validates that two logical models (chat and code) pointing to the
    exact same physical artifact and provider reuse the resident engine
    without triggering physical unloads or reloads.
    Sequence: chat -> code -> chat
    EXPECTED:
      physical_load_count == 1
      physical_unload_count == 0 (before shutdown)
      engine_id_chat_1 == engine_id_code == engine_id_chat_2
    """
    async def _run():
        registry = ProviderRegistry()
        provider = LiteRTEmbeddedProvider(models_dir="models")
        registry.register("litert_embedded", provider)
        await registry.set_active("litert_embedded")

        # Instrument physical load/unload counts
        load_count = 0
        unload_count = 0
        orig_load = provider.load_model
        orig_unload = provider.unload_model

        async def spied_load(m_id, m_path):
            nonlocal load_count
            load_count += 1
            return await orig_load(m_id, m_path)

        async def spied_unload(m_id):
            nonlocal unload_count
            unload_count += 1
            return await orig_unload(m_id)

        provider.load_model = spied_load
        provider.unload_model = spied_unload

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
        engine.register_model(
            model_id="code",
            model_path=MODEL_E2B,
            model_type="coding",
            estimated_vram_mb=1500,
            provider_id="litert_embedded",
        )

        await engine.start()

        # 1. First request with role 'chat'
        req1 = InferenceRequest(prompt="Say hi", model_id="chat", stream=False, max_tokens=10)
        await engine.generate(req1)
        engine_id_chat_1 = id(provider._engine)
        assert load_count == 1, f"Expected 1 physical load on chat start, got {load_count}"
        assert unload_count == 0, f"Expected 0 unloads, got {unload_count}"

        # 2. Second request with role 'code' (same physical artifact)
        req2 = InferenceRequest(prompt="Say code", model_id="code", stream=False, max_tokens=10)
        await engine.generate(req2)
        engine_id_code = id(provider._engine)

        assert engine_id_code == engine_id_chat_1, (
            f"Physical engine reconstructed on role alias change! "
            f"chat_1={engine_id_chat_1} vs code={engine_id_code}"
        )
        assert load_count == 1, f"Expected load_count to remain 1, got {load_count}"
        assert unload_count == 0, f"Expected unload_count to remain 0, got {unload_count}"

        # 3. Third request with role 'chat'
        req3 = InferenceRequest(prompt="Say back", model_id="chat", stream=False, max_tokens=10)
        await engine.generate(req3)
        engine_id_chat_2 = id(provider._engine)

        assert engine_id_chat_2 == engine_id_chat_1, (
            f"Physical engine reconstructed when returning to chat! "
            f"chat_1={engine_id_chat_1} vs chat_2={engine_id_chat_2}"
        )
        assert load_count == 1, f"Expected load_count to remain 1, got {load_count}"
        assert unload_count == 0, f"Expected unload_count to remain 0, got {unload_count}"

        # 4. Clean shutdown
        await engine.stop()
        assert provider._engine is None, "Engine should be released on stop"
        assert not await provider.is_model_loaded("chat")

    asyncio.run(_run())


def test_physical_identity_different_models_trigger_swap():
    """Negative control test:
    Validates that when physical identity is DIFFERENT (different artifact path
    or different provider), EngineManager does NOT treat them as aliases and
    properly unloads the previous model and loads the new one.
    Uses a controlled MockProvider to avoid the known FFI E2B/E4B issue (deferred to 0.2C).
    """
    from providers.base import (
        InferenceProvider,
        InferenceResult,
        ProviderCapabilities,
        ProviderStatus,
        ProviderType,
    )

    class MockProvider(InferenceProvider):
        def __init__(self, p_type: ProviderType = ProviderType.LITERT_NATIVE):
            super().__init__()
            self._type = p_type
            self._loaded: dict[str, str] = {}
            self.load_history: list[str] = []
            self.unload_history: list[str] = []

        def capabilities(self) -> ProviderCapabilities:
            return ProviderCapabilities(provider_type=self._type)

        async def initialize(self) -> None:
            self._status = ProviderStatus.READY

        async def shutdown(self) -> None:
            self._loaded.clear()
            self._status = ProviderStatus.SHUTDOWN

        async def load_model(self, model_id: str, model_path: str) -> None:
            self._loaded[model_id] = model_path
            self.load_history.append(model_id)

        async def unload_model(self, model_id: str) -> None:
            self._loaded.pop(model_id, None)
            self.unload_history.append(model_id)

        async def is_model_loaded(self, model_id: str) -> bool:
            return model_id in self._loaded

        async def loaded_models(self) -> list[str]:
            return list(self._loaded.keys())

        async def generate(self, request: InferenceRequest) -> InferenceResult:
            return InferenceResult(text="mock", tokens_generated=1, model_id=request.model_id)

        async def generate_stream(self, request: InferenceRequest):
            yield InferenceResult(text="mock", tokens_generated=1, model_id=request.model_id)

        async def cancel_generation(self, request_id: str) -> None:
            pass

        async def health_check(self) -> bool:
            return True

        async def get_metrics(self) -> dict:
            return {}

    async def _test():
        registry = ProviderRegistry()
        mock_p = MockProvider()
        registry.register("mock_p", mock_p)
        await registry.set_active("mock_p")

        engine = EngineManager(
            provider_registry=registry,
            hardware_info=detect_hardware(),
            max_vram_mb=4000,
        )

        # Register two different physical artifacts under same provider
        engine.register_model("model_a", r"models\fake_artifact_a.bin", provider_id="mock_p")
        engine.register_model("model_b", r"models\fake_artifact_b.bin", provider_id="mock_p")
        # Register same artifact filename under different provider
        mock_p2 = MockProvider(ProviderType.LLAMACPP)
        registry.register("mock_p2", mock_p2)
        engine.register_model("model_c", r"models\fake_artifact_a.bin", provider_id="mock_p2")

        await engine.start()

        # 1. Generate model_a
        await engine.generate(InferenceRequest(prompt="hi", model_id="model_a", stream=False))
        assert mock_p.load_history == ["model_a"]
        assert await mock_p.is_model_loaded("model_a")
        assert engine.active_model == "model_a"
        assert engine.active_physical_model == engine.get_physical_identity("model_a")

        # 2. Generate model_b (different artifact) -> MUST trigger swap!
        await engine.generate(InferenceRequest(prompt="hi", model_id="model_b", stream=False))
        assert "model_a" in mock_p.unload_history, "Expected model_a to be unloaded when swapping to model_b"
        assert mock_p.load_history == ["model_a", "model_b"]
        assert await mock_p.is_model_loaded("model_b")
        assert not await mock_p.is_model_loaded("model_a")
        assert engine.active_model == "model_b"
        assert engine.active_physical_model == engine.get_physical_identity("model_b")

        # 3. Generate model_c (same artifact path but different provider) -> MUST trigger swap!
        await engine.generate(InferenceRequest(prompt="hi", model_id="model_c", stream=False))
        assert "model_b" in mock_p.unload_history, "Expected model_b to be unloaded when swapping to model_c"
        assert mock_p2.load_history == ["model_c"]
        assert engine.active_model == "model_c"
        assert engine.active_physical_model == engine.get_physical_identity("model_c")

        await engine.stop()

    asyncio.run(_test())



