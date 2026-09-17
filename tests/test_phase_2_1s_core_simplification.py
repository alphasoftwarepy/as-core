"""
AS-Core — Fase 2.1S: Surgical Core Simplification Contracts (S1 - S15)
=============================================================================
Defines executable contract specifications for decoupling the hot path of
normal chat from weak keyword intent heuristics.

Tests S1 - S5 are EXPECTED RED on the current codebase because the current
PureCoordinator allows analyze_intent to hijack active_skill, profile,
prompt_family, and inject 'Habilidad activa: programming' into normal chat.
Tests S7 - S15 define invariant behaviors that must remain GREEN.
"""

import pytest
from unittest.mock import MagicMock
from runtime.coordinator.manager import PureCoordinator
from runtime.coordinator.models import RuntimeContract, SessionSnapshot
from runtime.coordinator.profiles import (
    resolve_cognitive_profile,
    PROFILE_BALANCED,
    PROFILE_CREATIVE,
    PROFILE_CODE,
    PROFILE_TO_PRESET,
)
from runtime.skills.models import SkillManifest


def make_mock_db():
    db = MagicMock()
    # Return empty lists for memory and RAG queries by default
    db.query.return_value.filter_by.return_value.all.return_value = []
    db.query.return_value.filter_by.return_value.count.return_value = 0
    db.query.return_value.filter.return_value.count.return_value = 0
    return db


def make_mock_skill_service():
    service = MagicMock()
    manifests = {
        "programming": SkillManifest(
            id="programming",
            name="Programming",
            description="Coding capabilities",
            prompt_family="SOFTWARE_PROMPT",
            uses_capabilities=True,
        ),
        "business": SkillManifest(
            id="business",
            name="Business",
            description="Business strategy",
            prompt_family="BUSINESS_PROMPT",
            uses_capabilities=False,
        ),
    }
    prompts = {
        "programming": "Instrucciones especializadas de programación.",
        "business": "Instrucciones especializadas de negocio.",
    }
    service.get_skill_manifest.side_effect = lambda sid: manifests.get(sid)
    service.get_skill_prompt.side_effect = lambda sid: prompts.get(sid)
    return service


# ============================================================================
# S1 — S5: AMBIGUOUS WORDS IN NATURAL LANGUAGE (EXPECTED RED TODAY)
# ============================================================================

def test_s1_false_programming_activation_biz05_prompt():
    """
    S1: 'desarrollo' in business context must NOT trigger programming authority.
    Input: BIZ-05 prompt.
    Expected:
      - active_skill is NOT 'programming'
      - system_prompt does NOT contain 'Habilidad activa: programming' or 'Active skill: programming'
      - prompt_family is NOT 'SOFTWARE_PROMPT'
      - resolved_profile is NOT 'CODE'
      - capability_gate_open is False
    """
    coord = PureCoordinator()
    db = make_mock_db()
    skill_service = make_mock_skill_service()

    contract = RuntimeContract(
        request_id="req-s1",
        session_id="sess-s1",
        model_id="chat",
        user_message=(
            "Durante el desarrollo de un proyecto el cliente solicitó funciones fuera "
            "del alcance acordado. Redacta un correo profesional explicando el impacto."
        ),
        manual_skill=None,  # Normal chat, no explicit skill
        profile="AUTO",
        timestamp=100.0,
        snapshot=SessionSnapshot(session_id="sess-s1", turn_number=1),
    )

    manifest = coord.assemble(db=db, contract=contract, skill_service=skill_service)

    assert manifest.active_skill is None, f"Expected active_skill to be None, got {manifest.active_skill!r}"
    assert "Habilidad activa:" not in manifest.system_prompt_snapshot
    assert "Active skill:" not in manifest.system_prompt_snapshot
    assert manifest.prompt_family != "SOFTWARE_PROMPT"
    assert manifest.resolved_profile != PROFILE_CODE
    assert manifest.capability_gate_open is False


def test_s2_ambiguous_architecture_word():
    """
    S2: 'arquitectura' in organizational context must NOT activate programming or any skill.
    """
    coord = PureCoordinator()
    db = make_mock_db()
    skill_service = make_mock_skill_service()

    contract = RuntimeContract(
        request_id="req-s2",
        session_id="sess-s2",
        model_id="chat",
        user_message="Explícame la arquitectura de una empresa pequeña.",
        manual_skill=None,
        profile="AUTO",
        timestamp=100.0,
        snapshot=SessionSnapshot(session_id="sess-s2", turn_number=1),
    )

    manifest = coord.assemble(db=db, contract=contract, skill_service=skill_service)

    assert manifest.active_skill is None, f"Expected active_skill to be None, got {manifest.active_skill!r}"
    assert manifest.resolved_profile != PROFILE_CODE
    assert "Habilidad activa:" not in manifest.system_prompt_snapshot


def test_s3_generic_error_word():
    """
    S3: 'error' in billing context must NOT activate programming or any skill.
    """
    coord = PureCoordinator()
    db = make_mock_db()
    skill_service = make_mock_skill_service()

    contract = RuntimeContract(
        request_id="req-s3",
        session_id="sess-s3",
        model_id="chat",
        user_message="Cometí un error al enviar una factura. Redacta un mensaje para el cliente.",
        manual_skill=None,
        profile="AUTO",
        timestamp=100.0,
        snapshot=SessionSnapshot(session_id="sess-s3", turn_number=1),
    )

    manifest = coord.assemble(db=db, contract=contract, skill_service=skill_service)

    assert manifest.active_skill is None, f"Expected active_skill to be None, got {manifest.active_skill!r}"
    assert manifest.resolved_profile != PROFILE_CODE


def test_s4_test_as_ordinary_language():
    """
    S4: 'test' in customer satisfaction context must NOT activate programming or any skill.
    """
    coord = PureCoordinator()
    db = make_mock_db()
    skill_service = make_mock_skill_service()

    contract = RuntimeContract(
        request_id="req-s4",
        session_id="sess-s4",
        model_id="chat",
        user_message="Necesito preparar un test de satisfacción para mis clientes.",
        manual_skill=None,
        profile="AUTO",
        timestamp=100.0,
        snapshot=SessionSnapshot(session_id="sess-s4", turn_number=1),
    )

    manifest = coord.assemble(db=db, contract=contract, skill_service=skill_service)

    assert manifest.active_skill is None, f"Expected active_skill to be None, got {manifest.active_skill!r}"
    assert manifest.resolved_profile != PROFILE_CODE


def test_s5_script_as_non_programming():
    """
    S5: 'script' in social video context must NOT activate programming or any skill.
    """
    coord = PureCoordinator()
    db = make_mock_db()
    skill_service = make_mock_skill_service()

    contract = RuntimeContract(
        request_id="req-s5",
        session_id="sess-s5",
        model_id="chat",
        user_message="Escribe un script para un video de Instagram.",
        manual_skill=None,
        profile="AUTO",
        timestamp=100.0,
        snapshot=SessionSnapshot(session_id="sess-s5", turn_number=1),
    )

    manifest = coord.assemble(db=db, contract=contract, skill_service=skill_service)

    assert manifest.active_skill is None, f"Expected active_skill to be None, got {manifest.active_skill!r}"
    assert manifest.resolved_profile != PROFILE_CODE


# ============================================================================
# S6 — S15: POSITIVE CONTRACTS & INVARIANTS (EXPECTED GREEN / INVARIANTS)
# ============================================================================

def test_s6_real_programming_construct_detection():
    """
    S6: Clear programming syntax resolves to CODE profile without keyword intent.
    """
    coord = PureCoordinator()
    db = make_mock_db()

    contract = RuntimeContract(
        request_id="req-s6",
        session_id="sess-s6",
        model_id="chat",
        user_message="def calculate_vat(price: float) -> float:\n    return price * 0.21",
        manual_skill=None,
        profile="AUTO",
        timestamp=100.0,
        snapshot=SessionSnapshot(session_id="sess-s6", turn_number=1),
    )

    manifest = coord.assemble(db=db, contract=contract)
    assert manifest.resolved_profile == PROFILE_CODE
    assert manifest.prompt_family == "SOFTWARE_PROMPT"


def test_s7_explicit_code_profile():
    """
    S7: Explicit profile=CODE deterministically applies SOFTWARE_PROMPT and PRECISE preset.
    """
    coord = PureCoordinator()
    db = make_mock_db()

    contract = RuntimeContract(
        request_id="req-s7",
        session_id="sess-s7",
        model_id="chat",
        user_message="Crea una función Python que calcule el IVA.",
        manual_skill=None,
        profile="CODE",  # Explicit override
        timestamp=100.0,
        snapshot=SessionSnapshot(session_id="sess-s7", turn_number=1),
    )

    manifest = coord.assemble(db=db, contract=contract)
    assert manifest.resolved_profile == PROFILE_CODE
    assert manifest.prompt_family == "SOFTWARE_PROMPT"
    assert PROFILE_TO_PRESET[manifest.resolved_profile] == "PRECISE"


def test_s8_explicit_skill_preserved():
    """
    S8: Explicit manual_skill preserves the skill, prompt, and manifest authority.
    """
    coord = PureCoordinator()
    db = make_mock_db()
    skill_service = make_mock_skill_service()

    contract = RuntimeContract(
        request_id="req-s8",
        session_id="sess-s8",
        model_id="chat",
        user_message="Escribe un informe de balance.",
        manual_skill="business",  # Explicit user choice
        profile="AUTO",
        timestamp=100.0,
        snapshot=SessionSnapshot(session_id="sess-s8", turn_number=1),
    )

    manifest = coord.assemble(db=db, contract=contract, skill_service=skill_service)
    assert manifest.active_skill == "business"
    assert "Instrucciones especializadas de negocio" in manifest.system_prompt_snapshot


def test_s9_authorized_capability_gate_open_with_explicit_skill():
    """
    S9: Skill with uses_capabilities=True opens capability gate.
    """
    coord = PureCoordinator()
    db = make_mock_db()
    skill_service = make_mock_skill_service()

    contract = RuntimeContract(
        request_id="req-s9",
        session_id="sess-s9",
        model_id="chat",
        user_message="Implementa un algoritmo.",
        manual_skill="programming",  # Explicit skill with uses_capabilities=True
        profile="AUTO",
        timestamp=100.0,
        snapshot=SessionSnapshot(session_id="sess-s9", turn_number=1),
    )

    manifest = coord.assemble(db=db, contract=contract, skill_service=skill_service)
    assert manifest.active_skill == "programming"
    assert manifest.capability_gate_open is True


def test_s10_no_skill_capability_gate_closed():
    """
    S10: Normal conversation without skill must keep capability gate CLOSED.
    """
    coord = PureCoordinator()
    db = make_mock_db()
    skill_service = make_mock_skill_service()

    contract = RuntimeContract(
        request_id="req-s10",
        session_id="sess-s10",
        model_id="chat",
        user_message="Hola, ¿cómo estás hoy?",
        manual_skill=None,
        profile="AUTO",
        timestamp=100.0,
        snapshot=SessionSnapshot(session_id="sess-s10", turn_number=1),
    )

    manifest = coord.assemble(db=db, contract=contract, skill_service=skill_service)
    assert manifest.capability_gate_open is False


def test_s11_workflow_continuation_contract():
    """
    S11: Workflow state persistence and continuation resolver function properly.
    """
    from runtime.coordinator.workflow_continuation import WorkflowContinuationResolver
    from runtime.coordinator.models import WorkflowState

    resolver = WorkflowContinuationResolver()
    state = WorkflowState(
        active_skill="business",
        objective="Analyze quarterly results",
        current_phase="analysis",
    )

    decision = resolver.resolve(
        user_message="Continuemos con los costos operativos",
        current_state=state,
        inferred_skill=None,
        manual_skill=None,
        session_id="sess-wf",
    )
    assert decision is True


def test_s12_rag_independence():
    """
    S12: RAG context assembly functions independently of skill inference.
    """
    coord = PureCoordinator()
    db = make_mock_db()
    rag_service = MagicMock()
    rag_service.build_context.return_value = "Contenido de documento RAG recuperado."

    contract = RuntimeContract(
        request_id="req-s12",
        session_id="sess-s12",
        model_id="chat",
        user_message="Resume el archivo subido.",
        manual_skill=None,
        profile="AUTO",
        timestamp=100.0,
        snapshot=SessionSnapshot(session_id="sess-s12", turn_number=1),
    )

    manifest = coord.assemble(db=db, contract=contract, rag_service=rag_service, enable_rag=True)
    assert manifest.rag_enabled is True
    assert "Contenido de documento RAG recuperado." in manifest.system_prompt_snapshot


def test_s13_graph_independence():
    """
    S13: Graph context functions independently of skill inference.
    """
    coord = PureCoordinator()
    db = make_mock_db()
    graph_provider = MagicMock()
    graph_provider.query_entities.return_value = ["EntityA -> EntityB"]

    contract = RuntimeContract(
        request_id="req-s13",
        session_id="sess-s13",
        model_id="chat",
        user_message="¿Qué relación tiene el cliente X con el proyecto Y?",
        manual_skill=None,
        profile="AUTO",
        timestamp=100.0,
        snapshot=SessionSnapshot(session_id="sess-s13", turn_number=1),
    )

    manifest = coord.assemble(db=db, contract=contract, graph_provider=graph_provider)
    assert manifest.graph_enabled is True


def test_s14_memory_independence():
    """
    S14: Working memory block functions independently of skill inference.
    """
    coord = PureCoordinator()
    db = make_mock_db()
    memory_service = MagicMock()
    memory_service.format_prompt_block.return_value = "## MEMORIA\nVariable: user_name = Juan"

    contract = RuntimeContract(
        request_id="req-s14",
        session_id="sess-s14",
        model_id="chat",
        user_message="¿Recuerdas mi nombre?",
        manual_skill=None,
        profile="AUTO",
        timestamp=100.0,
        snapshot=SessionSnapshot(session_id="sess-s14", turn_number=1),
    )

    manifest = coord.assemble(db=db, contract=contract, memory_service=memory_service)
    assert "Variable: user_name = Juan" in manifest.system_prompt_snapshot


def test_s15_profile_independence():
    """
    S15: Profiles AUTO, BALANCED, CREATIVE, CODE resolve without analyze_intent.
    """
    assert resolve_cognitive_profile(explicit_override=PROFILE_CODE) == PROFILE_CODE
    assert resolve_cognitive_profile(explicit_override=PROFILE_CREATIVE) == PROFILE_CREATIVE
    assert resolve_cognitive_profile(explicit_override=PROFILE_BALANCED) == PROFILE_BALANCED
    assert resolve_cognitive_profile(explicit_override="AUTO", skill_prompt_family=None) == PROFILE_BALANCED
