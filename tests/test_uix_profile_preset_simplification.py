"""
AS-Core — Tests de Validación UX: Simplificación Quirúrgica de UIX
Profile vs Preset Decoupling (Fase 1.4C)
=============================================================================
Valida:
UX1. Primary UI contains MODEL selector.
UX2. Primary UI contains COGNITIVE PROFILE selector.
UX3. Primary UI does NOT contain Runtime Preset as a third primary selector.
UX4. BALANCED profile resolves BALANCED preset.
UX5. CREATIVE profile resolves CREATIVE preset.
UX6. CODE profile resolves PRECISE preset.
UX7. AUTO uses resolved profile preset.
UX8. Changing profile does not invoke /v1/models/select.
UX9. Changing model DOES invoke explicit model selection control plane.
UX10. Profile change causes zero physical transition.
UX11. API compatibility with explicit preset remains if previously supported.
UX12. Advanced Runtime Settings does not override profile accidentally.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.models import ChatCompletionRequest, ChatMessage
from runtime.coordinator.manager import PureCoordinator
from runtime.coordinator.models import RuntimeContract, SessionSnapshot
from runtime.coordinator.profiles import (
    PROFILE_AUTO,
    PROFILE_BALANCED,
    PROFILE_CODE,
    PROFILE_CREATIVE,
    PROFILE_TO_PRESET,
    resolve_cognitive_profile,
)


@pytest.fixture
def index_html_content() -> str:
    path = Path("ui/index.html")
    assert path.exists(), "ui/index.html must exist"
    return path.read_text(encoding="utf-8")


@pytest.fixture
def app_js_content() -> str:
    path = Path("ui/app.js")
    assert path.exists(), "ui/app.js must exist"
    return path.read_text(encoding="utf-8")


# ── UX1: Primary UI contains MODEL selector ────────────────────────
def test_ux1_primary_ui_contains_model_selector(index_html_content: str):
    """Primary UI must provide model/backend selection."""
    assert 'id="modelSelect"' in index_html_content
    assert 'id="quickModelSelect"' in index_html_content
    assert "Model / Backend" in index_html_content


# ── UX2: Primary UI contains COGNITIVE PROFILE selector ────────────
def test_ux2_primary_ui_contains_cognitive_profile_selector(index_html_content: str):
    """Primary UI must provide cognitive profile selection with user-friendly labels."""
    assert 'id="profileSelect"' in index_html_content
    assert 'id="quickProfileSelect"' in index_html_content
    assert "AUTO — Adaptativo" in index_html_content
    assert "BALANCED — Equilibrado" in index_html_content
    assert "CODE — Código" in index_html_content
    assert "CREATIVE — Creativo" in index_html_content


# ── UX3: Primary UI does NOT contain Runtime Preset as third primary selector
def test_ux3_primary_ui_does_not_contain_preset_as_third_primary_selector(index_html_content: str):
    """Runtime preset must NOT appear in the primary settings grid.

    It must only be inside <details> Advanced Runtime Settings.
    """
    # Extract primary settings-grid block (before <details>)
    match = re.search(
        r'<div[^>]*id="settingsPanel"[^>]*>\s*<div class="settings-grid">(.*?)</div>\s*<!-- Collapsible Advanced Settings -->',
        index_html_content,
        re.DOTALL,
    )
    assert match is not None, "Primary settings-grid block not found"
    primary_grid = match.group(1)

    # Primary grid must have modelSelect and profileSelect, but NOT presetSelect
    assert 'id="modelSelect"' in primary_grid
    assert 'id="profileSelect"' in primary_grid
    assert 'id="presetSelect"' not in primary_grid

    # presetSelect must exist strictly inside <details>
    details_match = re.search(r"<details.*?</details>", index_html_content, re.DOTALL)
    assert details_match is not None
    assert 'id="presetSelect"' in details_match.group(0)
    assert "Advanced Runtime Settings" in details_match.group(0)


# ── UX4: BALANCED profile resolves BALANCED preset ─────────────────
def test_ux4_balanced_profile_resolves_balanced_preset():
    """BALANCED profile deterministically maps to BALANCED runtime preset."""
    resolved = resolve_cognitive_profile(explicit_override="BALANCED")
    assert resolved == PROFILE_BALANCED
    assert PROFILE_TO_PRESET[resolved] == "BALANCED"


# ── UX5: CREATIVE profile resolves CREATIVE preset ─────────────────
def test_ux5_creative_profile_resolves_creative_preset():
    """CREATIVE profile deterministically maps to CREATIVE runtime preset."""
    resolved = resolve_cognitive_profile(explicit_override="CREATIVE")
    assert resolved == PROFILE_CREATIVE
    assert PROFILE_TO_PRESET[resolved] == "CREATIVE"


# ── UX6: CODE profile resolves PRECISE preset ──────────────────────
def test_ux6_code_profile_resolves_precise_preset():
    """CODE profile deterministically maps to PRECISE runtime preset."""
    resolved = resolve_cognitive_profile(explicit_override="CODE")
    assert resolved == PROFILE_CODE
    assert PROFILE_TO_PRESET[resolved] == "PRECISE"


# ── UX7: AUTO uses resolved profile preset ─────────────────────────
def test_ux7_auto_uses_resolved_profile_preset():
    """AUTO profile first resolves the cognitive profile, then uses its mapped preset."""
    # General conversation -> resolves BALANCED -> BALANCED preset
    resolved_general = resolve_cognitive_profile(
        explicit_override="AUTO", user_message="Hello, can you help me write a plan?"
    )
    assert resolved_general == PROFILE_BALANCED
    assert PROFILE_TO_PRESET[resolved_general] == "BALANCED"

    # Programming query -> resolves CODE -> PRECISE preset
    resolved_code = resolve_cognitive_profile(
        explicit_override="AUTO", user_message="def calculate_total(items):\n    return sum(items)"
    )
    assert resolved_code == PROFILE_CODE
    assert PROFILE_TO_PRESET[resolved_code] == "PRECISE"


# ── UX8: Changing profile does not invoke /v1/models/select ────────
def test_ux8_changing_profile_does_not_invoke_model_select(app_js_content: str):
    """Changing cognitive profile must never trigger POST /v1/models/select."""
    # Inspect updateProfileSelection function
    match = re.search(
        r"function updateProfileSelection\(val\)\s*\{(.*?)\n    \}",
        app_js_content,
        re.DOTALL,
    )
    assert match is not None, "updateProfileSelection function must exist"
    func_body = match.group(1)
    assert "/v1/models/select" not in func_body
    assert "fetch" not in func_body


# ── UX9: Changing model DOES invoke explicit model selection ───────
def test_ux9_changing_model_invokes_explicit_selection(app_js_content: str):
    """Changing physical model selector MUST trigger POST /v1/models/select."""
    match = re.search(
        r"async function updateModelSelection\(val\)\s*\{(.*?)\n    \}",
        app_js_content,
        re.DOTALL,
    )
    assert match is not None, "updateModelSelection function must exist"
    func_body = match.group(1)
    assert "/v1/models/select" in func_body
    assert "POST" in func_body


# ── UX10: Profile change causes zero physical transition ───────────
def test_ux10_profile_change_causes_zero_physical_transition():
    """PureCoordinator.assemble with varying profiles retains contract.model_id without reloading."""
    coord = PureCoordinator()
    db = MagicMock()

    for prof in ["BALANCED", "CODE", "CREATIVE", "AUTO"]:
        contract = RuntimeContract(
            request_id=f"req-{prof}",
            session_id="sess-ux10",
            model_id="chat",  # Resident model remains 'chat'
            user_message="Test prompt",
            timestamp=1000.0,
            profile=prof,
            snapshot=SessionSnapshot(session_id="sess-ux10", turn_number=1),
        )
        manifest = coord.assemble(
            db=db,
            contract=contract,
            skill_service=None,
            rag_service=None,
            memory_service=None,
            enable_rag=False,
        )
        # Contract model_id is never modified by assemble
        assert contract.model_id == "chat"
        # Manifest reports resolved profile without physical transition
        assert manifest.resolved_profile in (PROFILE_BALANCED, PROFILE_CODE, PROFILE_CREATIVE)


# ── UX11: API compatibility with explicit preset remains ───────────
def test_ux11_api_compatibility_with_explicit_preset():
    """ChatCompletionRequest accepts explicit preset override for external client compatibility."""
    req = ChatCompletionRequest(
        model="chat",
        profile="CREATIVE",
        preset="PRECISE",  # Explicit override
        messages=[ChatMessage(role="user", content="Test")],
    )
    assert req.preset == "PRECISE"
    assert req.profile == "CREATIVE"
    assert req.model == "chat"


# ── UX12: Advanced Runtime Settings does not override profile accidentally
def test_ux12_advanced_settings_from_profile_default(index_html_content: str, app_js_content: str):
    """presetSelect in Advanced Settings defaults to FROM_PROFILE and does not force override."""
    # Verify HTML default option
    assert '<option value="FROM_PROFILE">FROM PROFILE (Automatic)</option>' in index_html_content

    # Verify app.js only sends header when NOT FROM_PROFILE
    assert "elements.presetSelect.value !== 'FROM_PROFILE'" in app_js_content
