"""
AS-Core — Fase 1 / Subfase 1.4A: Single Resident Model Policy Contract Tests
=============================================================================
Architectural contract tests (R1 - R20) governing:
1. Single resident physical model in memory across all cognitive profile variations.
2. Complete decoupling between physical model residency and cognitive profile/preset.
3. Deterministic profile resolution (AUTO -> BALANCED/CREATIVE/CODE).
4. Truthful state representation: selected_model vs active_model vs active_physical_model.
5. Tool gating strictly owned by Skill authorization and approval scopes, not model identity.
6. Zero physical model swaps on the hot path (SmartRouter never changes physical model).

Classification:
- UNIT: Pure function / resolver logic
- CONTRACT: State machine and architectural boundary invariants
- API: HTTP / Pydantic schema validation
- PHYSICAL: Provider load/unload/canonical residency execution
"""

import asyncio
import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

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
from api.models import (
    ChatCompletionRequest,
    ChatMessage,
    StatusResponse,
)
from router.smart_router import SmartRouter
from runtime.coordinator.models import (
    RuntimeContract,
    SessionSnapshot,
    WorkflowState,
    ContextManifest,
)
from runtime.coordinator.manager import PureCoordinator
from runtime.skills.models import SkillManifest


# ── Test Infrastructure: SpyProvider ──────────────────────────────


class SpyProvider(InferenceProvider):
    """In-memory spy provider tracking physical load/unload/generation calls."""

    def __init__(self, provider_id: str = "spy_provider") -> None:
        super().__init__()
        self.provider_id = provider_id
        self.load_calls: list[tuple[str, str]] = []
        self.unload_calls: list[str] = []
        self.generate_calls: list[InferenceRequest] = []
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
        self.load_calls.append((model_id, model_path))
        if model_id in self.load_failures:
            raise RuntimeError(f"Simulated load failure for {model_id}")
        self._loaded_models[model_id] = model_path

    async def unload_model(self, model_id: str) -> None:
        self.unload_calls.append(model_id)
        self._loaded_models.pop(model_id, None)

    async def is_model_loaded(self, model_id: str) -> bool:
        return model_id in self._loaded_models

    async def loaded_models(self) -> list[str]:
        return list(self._loaded_models.keys())

    async def generate(self, request: InferenceRequest) -> InferenceResult:
        self.generate_calls.append(request)
        if self.generation_delay > 0:
            await asyncio.sleep(self.generation_delay)
        return InferenceResult(text=f"Response for {request.model_id}", model_id=request.model_id)

    async def generate_stream(self, request: InferenceRequest):
        res = await self.generate(request)
        yield res

    async def cancel_generation(self, request_id: str) -> None:
        pass

    async def health_check(self) -> bool:
        return True

    async def get_metrics(self) -> dict:
        return {"provider_id": self.provider_id, "models": list(self._loaded_models.keys())}


async def create_test_engine(spy: SpyProvider) -> EngineManager:
    """Creates an EngineManager with standardized test models registered."""
    registry = ProviderRegistry()
    registry.register(spy.provider_id, spy)
    await registry.set_active(spy.provider_id)

    engine = EngineManager(
        provider_registry=registry,
        hardware_info=detect_hardware(),
        max_vram_mb=4000,
    )
    # Chat and Code share the exact same physical model file (E2B)
    engine.register_model(
        model_id="chat",
        model_path="models/gemma/gemma-3n-E2B-it-int4.litertlm",
        model_type="general",
        estimated_vram_mb=1500,
        provider_id=spy.provider_id,
    )
    engine.register_model(
        model_id="code",
        model_path="models/gemma/gemma-3n-E2B-it-int4.litertlm",
        model_type="coding",
        estimated_vram_mb=1500,
        provider_id=spy.provider_id,
    )
    # Reasoning points to a different physical model (E4B)
    engine.register_model(
        model_id="reasoning",
        model_path="models/gemma/gemma-4-E4B-it.litertlm",
        model_type="reasoning",
        estimated_vram_mb=3660,
        provider_id=spy.provider_id,
    )
    # OLMoE points to an MoE model
    engine.register_model(
        model_id="olmoe",
        model_path="models/olmoe/olmoe-1b-7b.gguf",
        model_type="moe",
        estimated_vram_mb=2500,
        provider_id=spy.provider_id,
    )
    return engine


# ═════════════════════════════════════════════════════════════════════
# 20 ARCHITECTURAL RED TEST CONTRACTS (R1 - R20)
# ═════════════════════════════════════════════════════════════════════


# ── R1: Default model remains resident across profile changes ──────
def test_r01_default_model_remains_resident_across_profile_changes():
    """
    CLASSIFICATION: CONTRACT
    EXPECTED FUTURE CONTRACT:
        A request specifying a cognitive profile (BALANCED, CODE, CREATIVE) operates
        on the currently resident model (default: chat) without triggering a physical reload.
        The request contract must accept `profile` as a first-class field.
    CURRENT BEHAVIOR:
        `ChatCompletionRequest` does not have a `profile` field; clients can only pass `model`.
    WHY IT FAILS TODAY:
        `ChatCompletionRequest.model_fields` lacks 'profile'.
    EXPECTED FAILURE POINT:
        assert "profile" in ChatCompletionRequest.model_fields
    """
    assert "profile" in ChatCompletionRequest.model_fields, (
        "ChatCompletionRequest must define a 'profile' field to support cognitive profiles"
    )


# ── R2: BALANCED -> CODE causes zero physical reload ───────────────
def test_r02_balanced_to_code_causes_zero_physical_reload():
    """
    CLASSIFICATION: CONTRACT
    EXPECTED FUTURE CONTRACT:
        Switching profile from BALANCED to CODE alters the prompt/preset parameters
        (e.g., SOFTWARE_PROMPT and PRECISE), but causes ZERO physical reload calls
        on the resident model.
    CURRENT BEHAVIOR:
        Coding behavior is tightly coupled to `contract.model_id == 'code'`.
        PureCoordinator only applies SOFTWARE_PROMPT if `contract.model_id == 'code'`.
        With resident model 'chat', setting a code profile is not recognized.
    WHY IT FAILS TODAY:
        PureCoordinator does not accept or resolve profile on contract; when model_id='chat',
        prompt_family resolves to None (GENERAL_PROMPT) instead of SOFTWARE_PROMPT.
    EXPECTED FAILURE POINT:
        assert manifest.prompt_family == "SOFTWARE_PROMPT" (when resident model is 'chat')
    """
    coord = PureCoordinator()
    db = MagicMock()

    # Request with resident model 'chat' asking for code behavior via profile
    contract = RuntimeContract(
        request_id="req-r2",
        session_id="sess-r2",
        model_id="chat",  # Resident model remains 'chat'
        user_message="def calculate_total(items): pass",
        timestamp=123.0,
        snapshot=SessionSnapshot(session_id="sess-r2", turn_number=1),
    )

    manifest = coord.assemble(
        db=db,
        contract=contract,
        skill_service=None,
        rag_service=None,
        memory_service=None,
        enable_rag=False,
    )

    # In target architecture, PureCoordinator or profile resolution must assign
    # SOFTWARE_PROMPT even when resident model_id is 'chat'
    assert getattr(contract, "profile", None) == "CODE" or manifest.prompt_family == "SOFTWARE_PROMPT", (
        "Switching to CODE profile on resident model 'chat' must produce SOFTWARE_PROMPT without swapping models"
    )


# ── R3: CODE -> CREATIVE causes zero physical reload ───────────────
def test_r03_code_to_creative_causes_zero_physical_reload():
    """
    CLASSIFICATION: CONTRACT
    EXPECTED FUTURE CONTRACT:
        Transitioning from CODE profile to CREATIVE profile preserves physical residency.
        ChatCompletionRequest must accept profile='CREATIVE'.
    CURRENT BEHAVIOR:
        ChatCompletionRequest has no profile field.
    WHY IT FAILS TODAY:
        Pydantic validation rejects or ignores profile='CREATIVE'.
    EXPECTED FAILURE POINT:
        ChatCompletionRequest(profile="CREATIVE", messages=[...])
    """
    req = ChatCompletionRequest(
        profile="CREATIVE",
        messages=[ChatMessage(role="user", content="Write a creative story")],
    )
    assert getattr(req, "profile", None) == "CREATIVE"


# ── R4: AUTO profile never changes physical model ──────────────────
def test_r04_auto_profile_never_changes_physical_model():
    """
    CLASSIFICATION: CONTRACT
    EXPECTED FUTURE CONTRACT:
        When a request uses AUTO profile, SmartRouter / profile resolver must NEVER
        change the physical model. Specifically, complex reasoning prompts must NOT
        route to 'reasoning' (E4B) and trigger an implicit physical swap.
    CURRENT BEHAVIOR:
        SmartRouter evaluates keywords. Reasoning keywords ('induction', 'deduce',
        'theorem', 'proof') return model_id='reasoning', forcing an implicit swap to E4B.
    WHY IT FAILS TODAY:
        router.route(...) returns model_id='reasoning'.
    EXPECTED FAILURE POINT:
        assert routed_model != "reasoning"
    """
    router = SmartRouter(chat_model="chat", coding_model="code", reasoning_model="reasoning")
    prompt_with_reasoning = "Deduce step by step the truth table and formal logic theorem for inductive reasoning"

    # In current implementation, passing explicit_model=None (or 'auto') scores keywords
    routed_model, _ = router.route(prompt_with_reasoning, None)

    # Under target Single Resident Model Policy, AUTO must NEVER return 'reasoning'
    # to trigger physical model swap
    assert routed_model != "reasoning", (
        f"SmartRouter routed AUTO request to '{routed_model}'. Under Single Resident Model Policy, "
        f"AUTO must never change physical model implicitly."
    )


# ── R5: Explicit user model change uses existing transition contract
def test_r05_explicit_user_model_change_uses_existing_transition_contract():
    """
    CLASSIFICATION: CONTRACT / API
    EXPECTED FUTURE CONTRACT:
        Explicit model selection is managed via a dedicated control plane contract
        (e.g., app.state.selected_model or explicit transition endpoint), which
        invokes EngineManager.ensure_model() safely under the Phase 0 contract.
    CURRENT BEHAVIOR:
        No selected_model state exists in app.state; model selection is ad-hoc per-request.
    WHY IT FAILS TODAY:
        app.state does not track selected_model.
    EXPECTED FAILURE POINT:
        assert hasattr(app.state, "selected_model")
    """
    from api.main import app
    assert hasattr(app.state, "selected_model"), (
        "Application state must explicitly track 'selected_model' for control plane ownership"
    )


# ── R6: After explicit model change, new model remains selected ────
def test_r06_after_explicit_model_change_new_model_remains_selected_for_subsequent_profiles():
    """
    CLASSIFICATION: CONTRACT
    EXPECTED FUTURE CONTRACT:
        When a user explicitly selects Model B ('olmoe'), subsequent requests
        with AUTO or BALANCED profile execute against Model B.
        Core MUST NOT revert back to Model A ('chat').
    CURRENT BEHAVIOR:
        Every request with model='auto' (or omitted) is re-routed by SmartRouter
        which defaults to 'chat', discarding the user's explicit model choice.
    WHY IT FAILS TODAY:
        SmartRouter.route() has no awareness of the currently resident model.
    EXPECTED FAILURE POINT:
        assert routed_model == "olmoe"
    """
    # Simulate user explicitly selected 'olmoe'
    resident_model = "olmoe"
    router = SmartRouter(chat_model="chat", coding_model="code", default_model="chat")

    # Next request arrives with AUTO (general conversation)
    user_message = "Hello, summarize the quarterly project updates"
    routed_model, _ = router.route(user_message, None)

    # If the system reverts to 'chat', it violates residency persistence
    assert routed_model == resident_model, (
        f"Subsequent AUTO request reverted to '{routed_model}' instead of preserving resident model '{resident_model}'"
    )


# ── R7: Core never automatically reverts to default ────────────────
def test_r07_core_never_automatically_reverts_to_default_because_of_prompt_skill_capability_or_router():
    """
    CLASSIFICATION: CONTRACT
    EXPECTED FUTURE CONTRACT:
        When resident model is 'reasoning' (or 'olmoe'), an incoming request with
        a Skill (such as 'programming', which recommends 'code') must execute on
        the resident model, NOT revert to 'code' or 'chat'.
    CURRENT BEHAVIOR:
        Skills specify recommended_model='code', which is forwarded as the physical model.
    WHY IT FAILS TODAY:
        Skill recommendations are treated as physical model selectors.
    EXPECTED FAILURE POINT:
        assert contract.model_id == "reasoning" (retained across skill execution)
    """
    resident_model = "reasoning"
    skill_manifest = SkillManifest(
        id="programming",
        name="Programming",
        description="Programming skill",
        recommended_model="code",  # Legacy recommendation
    )

    # In target architecture, resolved model for execution must remain resident_model
    execution_model = getattr(skill_manifest, "resolved_model", resident_model)
    if skill_manifest.recommended_model == "code":
        # Current behavior: recommended_model is used to swap model
        execution_model = skill_manifest.recommended_model

    assert execution_model == resident_model, (
        f"Skill recommended_model caused revert to '{execution_model}' instead of staying on '{resident_model}'"
    )


# ── R8: Physical aliases preserve identity and do not reload ───────
def test_r08_physical_aliases_preserve_identity_and_do_not_reload():
    """
    CLASSIFICATION: PHYSICAL / CONTRACT (ALREADY SATISFIED - ACCIDENTAL GREEN)
    EXPECTED FUTURE CONTRACT:
        Switching between logical aliases that map to the identical physical canonical
        file (e.g., 'chat' and 'code' -> gemma-3n-E2B-it-int4.litertlm) performs ZERO
        physical reloads because canonical identity matches.
    CURRENT BEHAVIOR:
        EngineManager._ensure_model_loaded checks canonical physical identity (Phase 0.2B/0.2C).
    WHY IT PASSES TODAY:
        Already implemented and frozen in core/engine.py.
    """
    async def _run():
        spy = SpyProvider()
        engine = await create_test_engine(spy)
        await engine.start()

        # Step 1: Load 'chat'
        await engine._ensure_model_loaded("chat")
        assert len(spy.load_calls) == 1
        assert len(spy.unload_calls) == 0

        # Step 2: Transition to 'code' (same physical file)
        await engine._ensure_model_loaded("code")
        # Must NOT have reloaded or unloaded
        assert len(spy.load_calls) == 1, "Physical alias transition must not call load_model again"
        assert len(spy.unload_calls) == 0, "Physical alias transition must not call unload_model"

        await engine.stop()

    asyncio.run(_run())


# ── R9: Phase 0 invariants remain GREEN ────────────────────────────
def test_r09_phase_0_invariants_remain_green():
    """
    CLASSIFICATION: CONTRACT (ALREADY SATISFIED - ACCIDENTAL GREEN)
    EXPECTED FUTURE CONTRACT:
        Phase 0 transition contract invariants remain strictly intact:
        Active generation on Model A prevents transition to Model B with finish_reason='busy',
        leaving Model A unaffected and continuing to generate.
    CURRENT BEHAVIOR:
        EngineManager.generate returns finish_reason='busy' on transition attempt during active generation.
    WHY IT PASSES TODAY:
        Already implemented and frozen in core/engine.py.
    """
    async def _run():
        spy = SpyProvider()
        spy.generation_delay = 0.2
        engine = await create_test_engine(spy)
        await engine.start()
        await engine._ensure_model_loaded("chat")

        # Start generation in background
        req_a = InferenceRequest(prompt="Busy test", model_id="chat")
        gen_task = asyncio.create_task(engine.generate(req_a))
        await asyncio.sleep(0.05)

        # Attempt transition to 'reasoning' (different physical model) while busy
        req_b = InferenceRequest(prompt="Swap while busy", model_id="reasoning")
        res_b = await engine.generate(req_b)

        assert res_b.finish_reason == "busy"
        assert engine.active_model == "chat"

        res_a = await gen_task
        assert res_a.text == "Response for chat"

        await engine.stop()

    asyncio.run(_run())


# ── R10: Unknown / blocked model selection fails truthfully ────────
def test_r10_unknown_blocked_provider_unavailable_model_selection_fails_truthfully():
    """
    CLASSIFICATION: API / CONTRACT
    EXPECTED FUTURE CONTRACT:
        Requesting an explicit physical model that is unknown or unregistered fails
        truthfully with a client error (HTTP 400 or 404), without crashing with 500
        or corrupting active residency.
    CURRENT BEHAVIOR:
        Calling chat completions with an unregistered model raises unhandled ValueError,
        resulting in HTTP 500 Internal Server Error.
    WHY IT FAILS TODAY:
        routes.py does not validate model_id before dispatch, raising 500.
    EXPECTED FAILURE POINT:
        assert response.status_code in (400, 404)
    """
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "completely_unregistered_model_xyz",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    assert response.status_code in (400, 404), (
        f"Expected client error (400/404) for unregistered model, got HTTP {response.status_code}"
    )


# ── R11: Explicit profile override deterministically dominates AUTO
def test_r11_explicit_profile_override_deterministically_dominates_auto():
    """
    CLASSIFICATION: UNIT / CONTRACT
    EXPECTED FUTURE CONTRACT:
        When a request specifies an explicit profile override (e.g., profile='CODE'),
        the deterministic profile resolver MUST select CODE regardless of message content
        (even if the message contains reasoning keywords or conversational keywords).
    CURRENT BEHAVIOR:
        Deterministic profile resolver does not exist; routing uses keyword counts.
    WHY IT FAILS TODAY:
        PureCoordinator does not have resolve_cognitive_profile().
    EXPECTED FAILURE POINT:
        assert hasattr(PureCoordinator, "resolve_cognitive_profile")
    """
    assert hasattr(PureCoordinator, "resolve_cognitive_profile"), (
        "PureCoordinator must provide a deterministic resolve_cognitive_profile method"
    )


# ── R12: No hidden physical model recommendation path remains active
def test_r12_no_hidden_physical_model_recommendation_path_remains_active():
    """
    CLASSIFICATION: CONTRACT
    EXPECTED FUTURE CONTRACT:
        Execution pipeline must decouple Skill execution from physical model recommendation.
        Activating a skill with recommended_model='code' and uses_capabilities=True
        must NOT require changing contract.model_id to 'code' to open its capability gate.
        The gate must function on resident model 'chat'.
    CURRENT BEHAVIOR:
        PureCoordinator (manager.py:243-262) evaluates capability mode based on
        settings.models[contract.model_id].type. Because 'chat' has type='general',
        cap_mode is 'off'. The UI was forced to send model=skill.recommended_model ('code')
        to open the gate, turning an advisory tag into a physical model selector.
    WHY IT FAILS TODAY:
        When contract.model_id is resident model 'chat', manifest.capability_gate_open is False.
    EXPECTED FAILURE POINT:
        assert manifest.capability_gate_open is True
    """
    coord = PureCoordinator()
    db = MagicMock()
    skill_service = MagicMock()
    manifest_mock = SkillManifest(
        id="programming",
        name="Programming",
        description="Coding skill",
        recommended_model="code",  # Advisory recommendation only
        uses_capabilities=True,
    )
    skill_service.get_skill_manifest.return_value = manifest_mock
    skill_service.get_skill_prompt.return_value = "Coding prompt"

    contract = RuntimeContract(
        request_id="req-r12",
        session_id="sess-r12",
        model_id="chat",  # Resident model remains 'chat'
        user_message="Implement quicksort",
        manual_skill="programming",
        timestamp=100.0,
        snapshot=SessionSnapshot(session_id="sess-r12", turn_number=1),
    )

    manifest = coord.assemble(
        db=db,
        contract=contract,
        skill_service=skill_service,
        rag_service=None,
        memory_service=None,
        enable_rag=False,
    )

    # In target architecture, recommended_model is strictly advisory;
    # capability gate opens on resident model 'chat' without needing physical switch to 'code'
    assert manifest.capability_gate_open is True, (
        "Capability gate is closed on resident model 'chat' because system requires "
        "switching physical model to recommended_model 'code'. This hidden physical routing path "
        "must be eliminated."
    )


# ── R13: selected / active / physical state are not collapsed ──────
def test_r13_selected_active_and_physical_state_are_not_collapsed():
    """
    CLASSIFICATION: API / CONTRACT
    EXPECTED FUTURE CONTRACT:
        The telemetry / status model must expose three distinct dimensions:
        - selected_model (user preference in control plane)
        - active_model (logical model active in engine)
        - active_physical_model (canonical physical path in VRAM)
    CURRENT BEHAVIOR:
        StatusResponse only exposes active_model.
    WHY IT FAILS TODAY:
        'selected_model' and 'active_physical_model' are missing from StatusResponse.model_fields.
    EXPECTED FAILURE POINT:
        assert "selected_model" in StatusResponse.model_fields
    """
    fields = StatusResponse.model_fields
    assert "selected_model" in fields, "StatusResponse must expose 'selected_model'"
    assert "active_physical_model" in fields, "StatusResponse must expose 'active_physical_model'"


# ── R14: Restart returns to documented default ─────────────────────
def test_r14_restart_initialization_returns_to_documented_default_for_process_scoped_policy():
    """
    CLASSIFICATION: UNIT / CONTRACT
    EXPECTED FUTURE CONTRACT:
        Under the process-scoped policy, application initialization always resets
        selected_model to the documented DEFAULT_MODEL_ID ('chat').
    CURRENT BEHAVIOR:
        app.state does not define selected_model.
    WHY IT FAILS TODAY:
        getattr(app.state, 'selected_model', None) is None instead of 'chat'.
    EXPECTED FAILURE POINT:
        assert getattr(app.state, "selected_model", None) == "chat"
    """
    from api.main import app
    assert getattr(app.state, "selected_model", None) == "chat", (
        "Process initialization must set selected_model to DEFAULT_MODEL_ID ('chat')"
    )


# ── R15: CODE preserves SOFTWARE_PROMPT without alias 'code' ───────
def test_r15_code_preserves_software_prompt_and_precise_without_physical_alias_code():
    """
    CLASSIFICATION: UNIT / CONTRACT
    EXPECTED FUTURE CONTRACT:
        A request on resident model 'chat' (or 'olmoe') specifying profile='CODE'
        receives SOFTWARE_PROMPT and PRECISE parameters without requiring model_id='code'.
    CURRENT BEHAVIOR:
        PureCoordinator.assemble (lines 226-227) only applies SOFTWARE_PROMPT if
        `contract.model_id == "code" or resolved_skill == "programming"`.
    WHY IT FAILS TODAY:
        With contract.model_id='chat' and no skill, prompt_family is None (resolving to GENERAL_PROMPT).
    EXPECTED FAILURE POINT:
        assert root_prompt contains software engineering instructions
    """
    coord = PureCoordinator()
    db = MagicMock()

    # Request with profile='CODE' on model_id='chat'
    contract = RuntimeContract(
        request_id="req-r15",
        session_id="sess-r15",
        model_id="chat",  # Physical resident model is 'chat', not 'code'
        user_message="Refactor this function to be async",
        timestamp=100.0,
        snapshot=SessionSnapshot(session_id="sess-r15", turn_number=1),
    )
    # Inject profile attribute if target contract supports it
    setattr(contract, "profile", "CODE")

    manifest = coord.assemble(
        db=db,
        contract=contract,
        skill_service=None,
        rag_service=None,
        memory_service=None,
        enable_rag=False,
    )

    # Must have SOFTWARE_PROMPT in system prompt snapshot
    assert "software engineer" in manifest.system_prompt_snapshot.lower() or "ingeniero de software" in manifest.system_prompt_snapshot.lower(), (
        "CODE profile must produce SOFTWARE_PROMPT even when model_id is 'chat'"
    )


# ── R16: Structured extraction does not become CODE on JSON ────────
def test_r16_structured_extraction_does_not_become_code_merely_because_json_requested():
    """
    CLASSIFICATION: UNIT / CONTRACT
    EXPECTED FUTURE CONTRACT:
        A prompt requesting structured JSON extraction under AUTO profile:
        'Extrae los datos en formato JSON según el esquema especificado'
        must resolve to cognitive profile BALANCED (with PRECISE generation parameters),
        and MUST NOT be classified as CODE profile or route to physical model 'code'.
    CURRENT BEHAVIOR:
        SmartRouter contains 'json' in CODING_KEYWORDS, returning model_id='code'.
    WHY IT FAILS TODAY:
        router.route() returns model_id='code'.
    EXPECTED FAILURE POINT:
        assert routed_model != "code"
    """
    router = SmartRouter(chat_model="chat", coding_model="code", default_model="chat")
    extraction_prompt = "Extrae los datos del cliente en formato JSON con los campos nombre y edad"

    routed_model, _ = router.route(extraction_prompt, None)

    assert routed_model != "code", (
        f"SmartRouter routed structured JSON extraction to '{routed_model}'. "
        f"Structured extraction must not be conflated with coding profile."
    )


# ── R17: Tools controlled by Skill, not physical model identity ─────
def test_r17_tools_controlled_by_skill_not_physical_model_identity():
    """
    CLASSIFICATION: UNIT / CONTRACT
    EXPECTED FUTURE CONTRACT:
        Tool capability gate must be governed strictly by Skill permissions and scopes:
        A) CODE profile alone on 'chat' without Skill MUST NOT open capability gate.
        B) BALANCED profile on 'chat' WITH an authorized Skill (uses_capabilities=True)
           MUST open capability gate.
    CURRENT BEHAVIOR:
        PureCoordinator (manager.py:243-252) checks settings.models.get(contract.model_id).type.
        Since 'chat' has type='general', cap_mode='off', capability_gate_open is ALWAYS False!
    WHY IT FAILS TODAY:
        Case B fails because 'chat' model forces cap_mode='off', blocking tools even with skill.
    EXPECTED FAILURE POINT:
        assert manifest_b.capability_gate_open is True
    """
    coord = PureCoordinator()
    db = MagicMock()

    # Setup B: Resident model 'chat', but Skill has uses_capabilities=True
    skill_service = MagicMock()
    skill_manifest = SkillManifest(
        id="file_manager",
        name="File Manager",
        description="Manages local documents",
        uses_capabilities=True,
    )
    skill_service.get_skill_manifest.return_value = skill_manifest
    skill_service.get_skill_prompt.return_value = "File manager instructions"

    contract_b = RuntimeContract(
        request_id="req-r17-b",
        session_id="sess-r17-b",
        model_id="chat",  # Resident model is 'chat'
        user_message="Lee el archivo de notas",
        manual_skill="file_manager",
        timestamp=100.0,
        snapshot=SessionSnapshot(session_id="sess-r17-b", turn_number=1),
    )

    manifest_b = coord.assemble(
        db=db,
        contract=contract_b,
        skill_service=skill_service,
        rag_service=None,
        memory_service=None,
        enable_rag=False,
    )

    # In target architecture, authorized skill opens the gate even on 'chat' model
    assert manifest_b.capability_gate_open is True, (
        "Authorized Skill with uses_capabilities=True must open capability gate regardless of model_id='chat'"
    )


# ── R18: API contract separates model selection from profile ───────
def test_r18_ui_api_contract_separates_model_selection_from_profile_selection():
    """
    CLASSIFICATION: API / CONTRACT
    EXPECTED FUTURE CONTRACT:
        ChatCompletionRequest schema separates physical model from cognitive profile:
        - model: physical model ID (e.g., 'gemma-e2b', 'olmoe', 'gemma-e4b')
        - profile: cognitive profile ('AUTO', 'BALANCED', 'CREATIVE', 'CODE')
    CURRENT BEHAVIOR:
        ChatCompletionRequest defaults model to 'auto', confusing profile and model.
    WHY IT FAILS TODAY:
        ChatCompletionRequest does not accept profile parameter in constructor.
    EXPECTED FAILURE POINT:
        assert "profile" in ChatCompletionRequest.model_fields
    """
    assert "profile" in ChatCompletionRequest.model_fields, (
        "ChatCompletionRequest must accept 'profile' separately from 'model'"
    )


# ── R19: API and UI share deterministic profile fallback semantics ─
def test_r19_api_and_ui_share_the_same_profile_fallback_semantics():
    """
    CLASSIFICATION: UNIT / CONTRACT
    EXPECTED FUTURE CONTRACT:
        Coordinator must export a deterministic profile resolver enforcing the hierarchy:
        1. explicit profile override
        2. explicit Skill / prompt_family
        3. structured request metadata
        4. known operational context
        5. BALANCED fallback.
    CURRENT BEHAVIOR:
        No deterministic resolve_profile method exists on PureCoordinator.
    WHY IT FAILS TODAY:
        PureCoordinator lacks resolve_profile().
    EXPECTED FAILURE POINT:
        assert hasattr(PureCoordinator, "resolve_profile")
    """
    assert hasattr(PureCoordinator, "resolve_profile"), (
        "PureCoordinator must provide a single source of truth 'resolve_profile()' method"
    )


# ── R20: Profile change during active inference never violates Busy Guard
def test_r20_profile_change_during_active_inference_never_requests_physical_transition():
    """
    CLASSIFICATION: CONTRACT
    EXPECTED FUTURE CONTRACT:
        When the engine is actively generating on the resident model ('chat'),
        receiving a request with reasoning or coding prompt under AUTO profile
        must NOT route to a different physical model ('reasoning') and must NOT
        attempt a physical model transition that triggers finish_reason='busy'.
    CURRENT BEHAVIOR:
        SmartRouter routes complex reasoning prompts to model_id='reasoning'.
        When dispatched to EngineManager while actively generating on 'chat',
        EngineManager detects a transition to a different physical model and
        returns finish_reason='busy'.
    WHY IT FAILS TODAY:
        SmartRouter.route() selects 'reasoning', and dispatching it during active
        inference returns finish_reason='busy'.
    EXPECTED FAILURE POINT:
        assert routed_model == engine.active_model (must remain on resident model)
    """
    async def _run():
        spy = SpyProvider()
        spy.generation_delay = 0.2
        engine = await create_test_engine(spy)
        await engine.start()
        await engine._ensure_model_loaded("chat")

        # Start generation on 'chat'
        req1 = InferenceRequest(prompt="Active inference", model_id="chat")
        gen_task = asyncio.create_task(engine.generate(req1))
        await asyncio.sleep(0.05)

        # Incoming request arrives with reasoning prompt
        router = SmartRouter(chat_model="chat", coding_model="code", reasoning_model="reasoning")
        reasoning_prompt = "Deduce step by step the truth table and formal logic theorem"
        routed_model, _ = router.route(reasoning_prompt, None)

        # In target architecture, profile routing during active inference must NOT
        # select a different physical model away from resident model ('chat')
        assert routed_model == engine.active_model, (
            f"SmartRouter routed incoming request to physical model '{routed_model}' while engine "
            f"is actively generating on '{engine.active_model}'. Under Single Resident Model Policy, "
            f"profile changes must execute on the resident model without physical transitions."
        )

        res1 = await gen_task
        assert res1.text == "Response for chat"

        await engine.stop()

    asyncio.run(_run())
