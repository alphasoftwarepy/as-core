"""
AS-Core — Tests for Generic Physical Model Transition Contract (0.2C.2B)
=========================================================================
Validates:
1. BUSY GUARD: active generation on Model A prevents transition to Model B with finish_reason="busy",
   leaving Model A unaffected and continuing to generate.
2. RUNTIME MODE:
   - single_user: startup OK
   - multi_user: FAIL FAST with RuntimeError
3. TARGET LOAD FAILURE:
   - A active -> swap to B -> A released -> B load fails -> active_model is None, active_physical_model is None
   - B does not appear as active_model or active_physical_model.
"""

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.engine import EngineManager, EngineBusyError
from core.hardware import detect_hardware
from providers.base import (
    InferenceProvider,
    InferenceRequest,
    InferenceResult,
    ProviderCapabilities,
    ProviderStatus,
    ProviderType,
)
from providers.registry import ProviderRegistry


class MockProvider(InferenceProvider):
    """Mock provider for unit testing transition state machines safely."""

    def __init__(self, provider_id: str = "mock") -> None:
        super().__init__()
        self.provider_id = provider_id
        self._loaded_models: dict[str, str] = {}
        self.load_failures: set[str] = set()
        self.generation_delay: float = 0.0

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_gpu=True,
            supports_npu=False,
            supports_streaming=True,
            supports_speculative_decoding=False,
            supports_multi_model=False,
            supports_vision=False,
            supports_audio=False,
            max_context_length=2048,
            supported_quantizations=("int4",),
            provider_type=ProviderType.LITERT_NATIVE,
        )

    async def initialize(self) -> None:
        self._status = ProviderStatus.READY

    async def shutdown(self) -> None:
        self._loaded_models.clear()
        self._status = ProviderStatus.SHUTDOWN

    async def load_model(self, model_id: str, model_path: str) -> None:
        if model_id in self.load_failures:
            raise RuntimeError(f"Simulated load failure for {model_id}")
        self._loaded_models[model_id] = model_path

    async def unload_model(self, model_id: str) -> None:
        self._loaded_models.pop(model_id, None)

    async def is_model_loaded(self, model_id: str) -> bool:
        return model_id in self._loaded_models

    async def loaded_models(self) -> list[str]:
        return list(self._loaded_models.keys())

    async def generate(self, request: InferenceRequest) -> InferenceResult:
        if self.generation_delay > 0:
            await asyncio.sleep(self.generation_delay)
        return InferenceResult(
            text=f"Response from {request.model_id}",
            finish_reason="stop",
            model_id=request.model_id,
        )

    async def generate_stream(self, request: InferenceRequest):
        res = await self.generate(request)
        yield res

    async def cancel_generation(self, request_id: str) -> None:
        pass

    async def health_check(self) -> bool:
        return True

    async def get_metrics(self) -> dict:
        return {"provider_id": self.provider_id, "models": list(self._loaded_models.keys())}


def test_runtime_mode_single_user_ok():
    """Validates single_user mode starts up normally."""
    registry = ProviderRegistry()
    engine = EngineManager(
        provider_registry=registry,
        runtime_mode="single_user",
    )
    assert engine.runtime_mode == "single_user"


def test_runtime_mode_multi_user_fail_fast():
    """Validates multi_user mode fails fast with RuntimeError (reserved/not implemented)."""
    registry = ProviderRegistry()
    with pytest.raises(RuntimeError, match="RESERVED / NOT IMPLEMENTED"):
        EngineManager(
            provider_registry=registry,
            runtime_mode="multi_user",
        )


def test_runtime_mode_invalid_value():
    """Validates unknown runtime mode raises ValueError."""
    registry = ProviderRegistry()
    with pytest.raises(ValueError, match="Unknown runtime_mode"):
        EngineManager(
            provider_registry=registry,
            runtime_mode="invalid_mode",
        )


def test_target_load_failure_preserves_state_consistency():
    """Validates that when model A is unloaded and model B fails to load:
    - Model B does NOT appear as active_model or active_physical_model.
    - Model A is unloaded.
    - Runtime active state is None (true explicit state).
    """
    async def _test():
        registry = ProviderRegistry()
        mock_p = MockProvider("mock_p")
        registry.register("mock_p", mock_p)
        await registry.set_active("mock_p")

        engine = EngineManager(provider_registry=registry)
        engine.register_model("model_a", "path/a", estimated_vram_mb=1000, provider_id="mock_p")
        engine.register_model("model_b", "path/b", estimated_vram_mb=1000, provider_id="mock_p")

        # 1. Load Model A
        req_a = InferenceRequest(prompt="hi", model_id="model_a")
        res_a = await engine.generate(req_a)
        assert res_a.finish_reason == "stop"
        assert engine.active_model == "model_a"
        assert os.path.normpath("path/a") in engine.active_physical_model

        # 2. Configure Model B to fail on load
        mock_p.load_failures.add("model_b")

        # 3. Request transition to Model B
        req_b = InferenceRequest(prompt="hi", model_id="model_b")
        with pytest.raises(RuntimeError, match="Simulated load failure for model_b"):
            await engine.generate(req_b)

        # 4. Verify state consistency:
        # B does NOT appear as active
        assert engine.active_model is None
        assert engine.active_physical_model is None
        # Model A was unloaded during swap
        assert not await mock_p.is_model_loaded("model_a")
        # Model B is not loaded
        assert not await mock_p.is_model_loaded("model_b")

    asyncio.run(_test())


def test_busy_guard_protects_active_generation():
    """Validates BUSY guard:
    - Model A is actively generating (delay = 0.4s)
    - Transition request to Model B arrives while A is generating
    - Request B receives finish_reason='busy'
    - Model A completes its generation successfully
    - Model A is NOT unloaded, Model B is NOT loaded
    - No crash, no deadlock
    """
    async def _test():
        registry = ProviderRegistry()
        mock_p = MockProvider("mock_p")
        mock_p.generation_delay = 0.4  # Model A will take 0.4s to generate
        registry.register("mock_p", mock_p)
        await registry.set_active("mock_p")

        engine = EngineManager(provider_registry=registry)
        engine.register_model("model_a", "path/a", estimated_vram_mb=1000, provider_id="mock_p")
        engine.register_model("model_b", "path/b", estimated_vram_mb=1000, provider_id="mock_p")

        # Start generating with Model A in background task
        req_a = InferenceRequest(prompt="hello A", model_id="model_a")
        task_a = asyncio.create_task(engine.generate(req_a))

        # Give task_a enough time to acquire generation lock
        await asyncio.sleep(0.1)

        # Ensure Model A is currently generating
        assert engine._is_generating is True
        assert engine.active_model == "model_a"

        # Now send transition request for Model B
        req_b = InferenceRequest(prompt="hello B", model_id="model_b")
        res_b = await engine.generate(req_b)

        # Assert BUSY guard rejected B
        assert res_b.finish_reason == "busy"
        assert "BUSY" in res_b.text

        # Wait for Model A to finish
        res_a = await task_a
        assert res_a.finish_reason == "stop"
        assert res_a.text == "Response from model_a"

        # Model A is STILL the active model and loaded
        assert engine.active_model == "model_a"
        assert await mock_p.is_model_loaded("model_a")
        assert not await mock_p.is_model_loaded("model_b")

        # Now that A finished, transition to B should succeed
        mock_p.generation_delay = 0.0
        res_b2 = await engine.generate(req_b)
        assert res_b2.finish_reason == "stop"
        assert engine.active_model == "model_b"
        assert await mock_p.is_model_loaded("model_b")

    asyncio.run(_test())
