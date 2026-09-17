"""
Tests for Phase 2.1T: Language Anchor Removal Contract
=============================================================================
Validates that:
1. PureCoordinator.assemble produces clean system prompts without [LANG=...] prefix.
2. Software/General root prompts start directly without any language tag artifact.
3. Language resolution remains intact in snapshot (resolved_language='es').
4. Skill prompt injection cleanly appends to root prompt without tag pollution.
5. Backward compatibility across coordinator assembly remains 100% GREEN.
"""

import time
import pytest
from unittest.mock import MagicMock

from runtime.coordinator.manager import PureCoordinator
from runtime.coordinator.models import RuntimeContract, SessionSnapshot
from runtime.coordinator.prompts import resolve_root_prompt
from runtime.skills.models import SkillManifest


def make_contract(req_id: str, msg: str, manual_skill=None, profile=None) -> RuntimeContract:
    return RuntimeContract(
        request_id=req_id,
        session_id=f"sess-{req_id}",
        model_id="chat",
        user_message=msg,
        manual_skill=manual_skill,
        profile=profile,
        timestamp=time.time(),
        snapshot=SessionSnapshot(session_id=f"sess-{req_id}", turn_number=1, resolved_language="es"),
    )


@pytest.fixture
def coordinator():
    return PureCoordinator()


@pytest.fixture
def db():
    mock = MagicMock()
    mock.query.return_value.filter_by.return_value.all.return_value = []
    mock.query.return_value.filter_by.return_value.count.return_value = 0
    return mock


def test_t1_assemble_general_has_no_lang_anchor(coordinator, db):
    """General prompt should not start with [LANG=...] prefix."""
    contract = make_contract("test-1t-gen", "¿Cuál es la capital de Paraguay?", profile="BALANCED")
    manifest = coordinator.assemble(db=db, contract=contract)
    system_prompt = manifest.system_prompt_snapshot
    assert not system_prompt.startswith("[LANG=")
    assert "[LANG=" not in system_prompt
    assert system_prompt.startswith("Eres un asistente de inteligencia artificial directo")


def test_t2_assemble_code_has_no_lang_anchor(coordinator, db):
    """Code prompt should not start with [LANG=...] prefix."""
    contract = make_contract("test-1t-code", "def fibonacci(n):", profile="CODE")
    manifest = coordinator.assemble(db=db, contract=contract)
    system_prompt = manifest.system_prompt_snapshot
    assert not system_prompt.startswith("[LANG=")
    assert "[LANG=" not in system_prompt
    assert system_prompt.startswith("Eres un ingeniero de software y operador")


def test_t3_language_resolution_remains_es(coordinator, db):
    """Language resolution logic remains active and resolves 'es' even without the tag prefix."""
    from runtime.coordinator.continuity_resolver import DeterministicContinuityResolver
    resolver = DeterministicContinuityResolver()
    contract = make_contract("test-1t-lang", "Hola mundo")
    decision = resolver.resolve(contract)
    assert decision.detected_language == "ES"

    manifest = coordinator.assemble(db=db, contract=contract)
    assert "[LANG=es]" not in manifest.system_prompt_snapshot
    assert "[LANG=ES]" not in manifest.system_prompt_snapshot


def test_t4_skill_injection_cleanly_appends_without_anchor(coordinator, db):
    """When a skill is explicitly active, its prompt appends after root prompt cleanly."""
    mock_skill_service = MagicMock()
    mock_skill_service.get_skill_manifest.return_value = SkillManifest(
        id="programming",
        name="Programming",
        description="Coding",
        prompt_family="SOFTWARE_PROMPT",
        uses_capabilities=True,
    )
    mock_skill_service.get_skill_prompt.return_value = "## REGLAS DE PROGRAMACION ADICIONALES"

    contract = make_contract("test-1t-skill", "Ayuda con esta función", manual_skill="programming", profile="CODE")
    manifest = coordinator.assemble(
        db=db,
        contract=contract,
        skill_service=mock_skill_service,
    )
    system_prompt = manifest.system_prompt_snapshot
    assert "[LANG=" not in system_prompt
    assert "Eres un ingeniero de software y operador" in system_prompt
    assert "## REGLAS DE PROGRAMACION ADICIONALES" in system_prompt


def test_t5_root_prompt_resolution_unchanged():
    """Verify resolve_root_prompt returns clean text."""
    general_es = resolve_root_prompt("es", "GENERAL_PROMPT")
    software_es = resolve_root_prompt("es", "SOFTWARE_PROMPT")
    assert not general_es.startswith("[LANG=")
    assert not software_es.startswith("[LANG=")
