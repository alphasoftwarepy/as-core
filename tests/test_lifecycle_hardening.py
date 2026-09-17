"""
AS Core — Subfase 0.2D Lifecycle Hardening Tests
================================================
Deterministic tests validating:
- Invariant I1: MAX ACTIVE PHYSICAL INFERENCE = 1
- Invariant I2: ACTIVE INFERENCE => NO PHYSICAL UNLOAD
- Invariant I3: SAME PHYSICAL IDENTITY => NO RELOAD
- Invariant I4: TARGET LOAD FAILURE => TARGET NOT ACTIVE
- Invariant I5: GENERATION FAILURE => BUSY GUARD RELEASED
- Invariant I6: CANCELLATION => BUSY GUARD RELEASED
- Invariant I7: SHUTDOWN COMPLETE => NO OWNED CHILD PROCESS
- Invariant I8: ACTIVE_MODEL STATE = PHYSICAL REALITY
- Invariant I9: MULTI_USER = FAIL FAST
- Invariant I10: NO CONCURRENT INCOMPATIBLE PHYSICAL LOADS
"""

import asyncio
import time
from typing import AsyncIterator, List, Optional
import pytest

from core.engine import EngineBusyError, EngineManager
from core.hardware import HardwareInfo, HardwareTier, MemoryInfo, GPUInfo, CPUInfo
from providers.base import (
    InferenceProvider,
    InferenceRequest,
    InferenceResult,
    ProviderCapabilities,
    ProviderStatus,
    ProviderType,
)
from providers.registry import ProviderRegistry


class MockHardenedProvider(InferenceProvider):
    """Mock provider with instrumentation for concurrency, load counts, and events."""

    def __init__(self, provider_type: ProviderType = ProviderType.LITERT_NATIVE):
        super().__init__()
        self._provider_type = provider_type
        self._loaded_models: dict[str, str] = {}
        self.load_count: int = 0
        self.unload_count: int = 0
        self.active_inferences: int = 0
        self.max_concurrent_inferences: int = 0
        self.concurrent_loads: int = 0
        self.max_concurrent_loads: int = 0

        # Hooks/events for deterministic synchronization
        self.before_load_event: Optional[asyncio.Event] = None
        self.load_in_progress_event: Optional[asyncio.Event] = None
        self.generation_started_event: Optional[asyncio.Event] = None
        self.generation_release_event: Optional[asyncio.Event] = None
        self.generate_fail: bool = False

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
            provider_type=self._provider_type,
        )

    async def initialize(self) -> None:
        self._status = ProviderStatus.READY

    async def shutdown(self) -> None:
        self._loaded_models.clear()
        self._status = ProviderStatus.SHUTDOWN

    async def load_model(self, model_id: str, model_path: str) -> None:
        self.concurrent_loads += 1
        if self.concurrent_loads > self.max_concurrent_loads:
            self.max_concurrent_loads = self.concurrent_loads

        if self.before_load_event:
            await self.before_load_event.wait()

        if self.load_in_progress_event:
            self.load_in_progress_event.set()

        # Simulate non-zero async load duration
        await asyncio.sleep(0.05)
        self.load_count += 1
        self._loaded_models[model_id] = model_path
        self.concurrent_loads -= 1

    async def unload_model(self, model_id: str) -> None:
        self.unload_count += 1
        self._loaded_models.pop(model_id, None)

    async def is_model_loaded(self, model_id: str) -> bool:
        return model_id in self._loaded_models

    async def loaded_models(self) -> List[str]:
        return list(self._loaded_models.keys())

    async def generate(self, request: InferenceRequest) -> InferenceResult:
        self.active_inferences += 1
        if self.active_inferences > self.max_concurrent_inferences:
            self.max_concurrent_inferences = self.active_inferences

        if self.generation_started_event:
            self.generation_started_event.set()

        try:
            if self.generation_release_event:
                await self.generation_release_event.wait()
            else:
                await asyncio.sleep(0.02)

            if self.generate_fail:
                raise RuntimeError("Simulated provider failure during generate")

            return InferenceResult(
                text="Hardened response",
                finish_reason="stop",
                tokens_generated=5,
                prompt_tokens=2,
                model_id=request.model_id,
                provider_type=self._provider_type.value,
            )
        finally:
            self.active_inferences -= 1

    async def generate_stream(
        self, request: InferenceRequest
    ) -> AsyncIterator[InferenceResult]:
        self.active_inferences += 1
        if self.active_inferences > self.max_concurrent_inferences:
            self.max_concurrent_inferences = self.active_inferences

        if self.generation_started_event:
            self.generation_started_event.set()

        try:
            for i in range(3):
                if self.generate_fail and i == 1:
                    raise RuntimeError("Simulated provider stream error at chunk 1")
                if self.generation_release_event:
                    await self.generation_release_event.wait()
                else:
                    await asyncio.sleep(0.01)
                yield InferenceResult(
                    text=f"token_{i} ",
                    finish_reason=None,
                    tokens_generated=i + 1,
                    model_id=request.model_id,
                    provider_type=self._provider_type.value,
                )
            yield InferenceResult(
                text="",
                finish_reason="stop",
                tokens_generated=3,
                model_id=request.model_id,
                provider_type=self._provider_type.value,
            )
        finally:
            self.active_inferences -= 1

    async def cancel_generation(self, request_id: str) -> None:
        pass

    async def health_check(self) -> bool:
        return True

    async def get_metrics(self) -> dict:
        return {"loaded_models": list(self._loaded_models.keys())}


def create_test_engine(provider: MockHardenedProvider, model_unload_timeout: float = 300.0) -> EngineManager:
    registry = ProviderRegistry()
    registry.register("mock_p", provider)
    
    hw = HardwareInfo(
        tier=HardwareTier.BALANCED,
        cpu=CPUInfo(cores_logical=8),
        memory=MemoryInfo(total_mb=16384, available_mb=8192),
        gpu=GPUInfo(is_available=True, name="Test GPU", vram_total_mb=6144, vram_free_mb=4096),
    )
    
    engine = EngineManager(
        provider_registry=registry,
        hardware_info=hw,
        max_vram_mb=4000,
        model_unload_timeout=model_unload_timeout,
        model_absolute_lifetime=1800.0,
    )
    engine.register_model(
        model_id="model_a",
        model_path="C:/models/model_a.bin",
        model_type="general",
        estimated_vram_mb=1000,
        provider_id="mock_p",
    )
    engine.register_model(
        model_id="model_b",
        model_path="C:/models/model_b.bin",
        model_type="reasoning",
        estimated_vram_mb=1000,
        provider_id="mock_p",
    )
    return engine


def test_same_model_concurrency_rejected_with_busy():
    """Invariant I1: In single_user mode, same-model concurrent requests must NOT run in parallel.
    Second request must be rejected with BUSY."""
    async def _test():
        provider = MockHardenedProvider()
        engine = create_test_engine(provider)
        await engine.start()

        provider.generation_started_event = asyncio.Event()
        provider.generation_release_event = asyncio.Event()

        # Task A starts generating model_a
        req_a = InferenceRequest(prompt="Hello A", model_id="model_a")
        task_a = asyncio.create_task(engine.generate(req_a))

        # Wait until Task A is actively generating
        await provider.generation_started_event.wait()
        assert engine._is_generating is True
        assert engine._generating_model == "model_a"

        # Task B arrives for the SAME model while Task A is actively generating
        req_b = InferenceRequest(prompt="Hello B", model_id="model_a")
        try:
            result_b = await asyncio.wait_for(engine.generate(req_b), timeout=0.5)
        except asyncio.TimeoutError:
            provider.generation_release_event.set()
            await task_a
            pytest.fail("Same-model concurrency allowed Task B to enter generate() instead of rejecting with BUSY (hung)")

        # Invariant I1 verification:
        assert result_b.finish_reason == "busy", f"Expected BUSY but got {result_b.finish_reason}"
        assert "BUSY" in result_b.text

        # Release Task A
        provider.generation_release_event.set()
        result_a = await task_a
        assert result_a.finish_reason == "stop"

        # Concurrency verification: Max concurrent inferences must strictly be 1
        assert provider.max_concurrent_inferences == 1
        await engine.stop()

    asyncio.run(_test())


def test_cross_model_concurrency_rejected_with_busy():
    """Invariant I1 & I2: Cross-model request arriving during active generation must be rejected with BUSY.
    Active model must NOT be unloaded."""
    async def _test():
        provider = MockHardenedProvider()
        engine = create_test_engine(provider)
        await engine.start()

        provider.generation_started_event = asyncio.Event()
        provider.generation_release_event = asyncio.Event()

        # Task A starts generating model_a
        req_a = InferenceRequest(prompt="Hello A", model_id="model_a")
        task_a = asyncio.create_task(engine.generate(req_a))

        await provider.generation_started_event.wait()
        assert engine._is_generating is True

        # Task B arrives for model_b (different model requiring swap)
        req_b = InferenceRequest(prompt="Hello B", model_id="model_b")
        result_b = await engine.generate(req_b)

        assert result_b.finish_reason == "busy"
        assert provider.unload_count == 0  # model_a was NOT unloaded

        provider.generation_release_event.set()
        result_a = await task_a
        assert result_a.finish_reason == "stop"
        assert engine.active_model == "model_a"

        await engine.stop()

    asyncio.run(_test())


def test_concurrent_load_serialization_same_model():
    """Invariant I10: Concurrent requests to load the same model must be serialized.
    load_model must only be called once, not concurrently."""
    async def _test():
        provider = MockHardenedProvider()
        engine = create_test_engine(provider)
        await engine.start()

        # Trigger two concurrent ensure_model_loaded / generate calls
        req1 = InferenceRequest(prompt="Req 1", model_id="model_a")
        req2 = InferenceRequest(prompt="Req 2", model_id="model_a")

        # Launch both concurrently
        t1 = asyncio.create_task(engine.generate(req1))
        t2 = asyncio.create_task(engine.generate(req2))

        res1, res2 = await asyncio.gather(t1, t2)

        # One must succeed with stop, one may succeed or be busy, but load_count must be 1
        # and max_concurrent_loads must be <= 1 (no concurrent physical loads)
        assert provider.max_concurrent_loads <= 1, f"Expected max_concurrent_loads <= 1, got {provider.max_concurrent_loads}"
        assert provider.load_count == 1, f"Expected exactly 1 physical load, got {provider.load_count}"
        
        # At least one succeeded
        assert res1.finish_reason == "stop" or res2.finish_reason == "stop"

        await engine.stop()

    asyncio.run(_test())


def test_double_stop_is_idempotent():
    """Shutdown lifecycle: Calling stop() multiple times must be safe and idempotent."""
    async def _test():
        provider = MockHardenedProvider()
        engine = create_test_engine(provider)
        await engine.start()
        
        # First stop
        await engine.stop()
        assert engine._running is False
        assert engine.active_model is None

        # Second stop (must not raise CancelledError or crash)
        await engine.stop()
        assert engine._running is False
        assert engine.active_model is None

    asyncio.run(_test())


def test_generation_exception_releases_busy_guard():
    """Invariant I5: Exception during generation must release BUSY guard and leave state truthful."""
    async def _test():
        provider = MockHardenedProvider()
        engine = create_test_engine(provider)
        await engine.start()

        provider.generate_fail = True
        req = InferenceRequest(prompt="Fail prompt", model_id="model_a")

        with pytest.raises(RuntimeError, match="Simulated provider failure"):
            await engine.generate(req)

        # State verification
        assert engine._is_generating is False
        assert engine._generating_model is None
        # The physical model remains loaded and truthful
        assert engine.active_model == "model_a"

        # Now unbreak provider and verify engine accepts new requests cleanly
        provider.generate_fail = False
        req2 = InferenceRequest(prompt="Success prompt", model_id="model_a")
        res2 = await engine.generate(req2)
        assert res2.finish_reason == "stop"
        assert engine._is_generating is False

        await engine.stop()

    asyncio.run(_test())


def test_streaming_exception_releases_busy_guard():
    """Invariant I5: Exception during streaming generation releases BUSY guard."""
    async def _test():
        provider = MockHardenedProvider()
        engine = create_test_engine(provider)
        await engine.start()

        provider.generate_fail = True
        req = InferenceRequest(prompt="Fail stream", model_id="model_a")

        with pytest.raises(RuntimeError, match="Simulated provider stream error"):
            async for chunk in engine.generate_stream(req):
                pass

        assert engine._is_generating is False
        assert engine._generating_model is None

        # Verify recovery
        provider.generate_fail = False
        req2 = InferenceRequest(prompt="Success stream", model_id="model_a")
        chunks = []
        async for chunk in engine.generate_stream(req2):
            chunks.append(chunk)

        assert len(chunks) > 0
        assert chunks[-1].finish_reason == "stop"
        assert engine._is_generating is False

        await engine.stop()

    asyncio.run(_test())


def test_streaming_cancellation_releases_busy_guard():
    """Invariant I6: Caller cancellation of streaming generation releases BUSY guard."""
    async def _test():
        provider = MockHardenedProvider()
        engine = create_test_engine(provider)
        await engine.start()

        provider.generation_started_event = asyncio.Event()
        provider.generation_release_event = asyncio.Event()
        req = InferenceRequest(prompt="Cancel stream", model_id="model_a")

        gen = engine.generate_stream(req)
        # Start iterating in a background task
        async def run_stream():
            async for _ in gen:
                pass

        task = asyncio.create_task(run_stream())
        await provider.generation_started_event.wait()
        assert engine._is_generating is True

        # Cancel the task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Aclose generator
        await gen.aclose()

        assert engine._is_generating is False
        assert engine._generating_model is None

        await engine.stop()

    asyncio.run(_test())


def test_concurrent_incompatible_models_never_load_concurrently():
    """Invariant I10: Concurrent load requests for incompatible models must be serialized.
    Under no condition should two incompatible physical loads execute in parallel."""
    async def _test():
        provider = MockHardenedProvider()
        engine = create_test_engine(provider)
        await engine.start()

        req_a = InferenceRequest(prompt="Hello A", model_id="model_a")
        req_b = InferenceRequest(prompt="Hello B", model_id="model_b")

        t1 = asyncio.create_task(engine.generate(req_a))
        t2 = asyncio.create_task(engine.generate(req_b))

        res1, res2 = await asyncio.gather(t1, t2)

        # Max concurrent loads MUST be <= 1 (Invariant I10)
        assert provider.max_concurrent_loads <= 1, f"Expected max_concurrent_loads <= 1, got {provider.max_concurrent_loads}"
        # At least one request completed or rejected with busy
        assert res1.finish_reason in ("stop", "busy")
        assert res2.finish_reason in ("stop", "busy")

        await engine.stop()

    asyncio.run(_test())


def test_idle_unload_never_unloads_active_generating_model():
    """Invariant I2: Idle unload loop must never unload a model while it is generating."""
    async def _test():
        provider = MockHardenedProvider()
        # Very short unload timeout: 0.1s
        engine = create_test_engine(provider, model_unload_timeout=0.1)
        await engine.start()

        provider.generation_started_event = asyncio.Event()
        provider.generation_release_event = asyncio.Event()

        req = InferenceRequest(prompt="Long generation", model_id="model_a")
        task = asyncio.create_task(engine.generate(req))

        await provider.generation_started_event.wait()
        assert engine._is_generating is True

        # Wait 0.3s (longer than the 0.1s unload timeout) while generation is still running
        await asyncio.sleep(0.3)

        # Must NOT have unloaded
        assert provider.unload_count == 0
        assert engine.active_model == "model_a"

        # Finish generation
        provider.generation_release_event.set()
        res = await task
        assert res.finish_reason == "stop"

        await engine.stop()

    asyncio.run(_test())
