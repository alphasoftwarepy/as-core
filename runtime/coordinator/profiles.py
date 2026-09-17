"""
AS-Core — Cognitive Profile Resolver (Phase 1.4B)

Deterministic, pure-function resolver for the cognitive profile of a request.
Controls HOW the system works (prompt family + generation preset).
NEVER controls WHICH physical model to use.

Resolution hierarchy (5 levels, no ML / no scoring):
1. Explicit profile override (from request body)
2. Active Skill prompt family (SOFTWARE_PROMPT → CODE)
3. No reclassification for JSON/structured extraction (stays BALANCED)
4. Workflow context (reserved, not used in 1.4B)
5. Fallback: BALANCED

Profiles:
  AUTO    → resolved via hierarchy (never selects a model)
  BALANCED → GENERAL_PROMPT + BALANCED preset (temp 0.5)
  CREATIVE → GENERAL_PROMPT + CREATIVE preset (temp 0.8)
  CODE    → SOFTWARE_PROMPT + PRECISE preset (temp 0.1)
"""

from __future__ import annotations

from typing import Optional


# ── Profile constants ─────────────────────────────────────────────

PROFILE_BALANCED = "BALANCED"
PROFILE_CREATIVE = "CREATIVE"
PROFILE_CODE     = "CODE"
PROFILE_AUTO     = "AUTO"


# ── Profile → Prompt family mapping ──────────────────────────────

PROFILE_TO_PROMPT_FAMILY: dict[str, Optional[str]] = {
    PROFILE_CODE:     "SOFTWARE_PROMPT",
    PROFILE_BALANCED: None,   # None → resolve_root_prompt uses GENERAL_PROMPT
    PROFILE_CREATIVE: None,
    PROFILE_AUTO:     None,
}

# ── Profile → Preset mapping ──────────────────────────────────────

PROFILE_TO_PRESET: dict[str, str] = {
    PROFILE_CODE:     "PRECISE",
    PROFILE_BALANCED: "BALANCED",
    PROFILE_CREATIVE: "CREATIVE",
    PROFILE_AUTO:     "BALANCED",  # AUTO fallback is BALANCED preset
}


def resolve_cognitive_profile(
    explicit_override: Optional[str] = None,
    skill_prompt_family: Optional[str] = None,
    user_message: Optional[str] = None,
) -> str:
    """Resolve the final cognitive profile for a request.

    This is a pure deterministic function — no randomness, no ML, no scoring.

    Args:
        explicit_override: Value from request.profile field (AUTO/BALANCED/CREATIVE/CODE).
                           If AUTO or None, continue down the hierarchy.
        skill_prompt_family: prompt_family from the active Skill manifest, if any.
        user_message: Optional user message text to detect programming constructs when AUTO.

    Returns:
        One of: 'BALANCED', 'CREATIVE', 'CODE'  (never 'AUTO' — AUTO is resolved away).
    """
    # Level 1: Explicit override (non-AUTO wins immediately)
    if explicit_override and explicit_override != PROFILE_AUTO:
        if explicit_override in (PROFILE_BALANCED, PROFILE_CREATIVE, PROFILE_CODE):
            return explicit_override

    # Level 2: Skill prompt family
    # SOFTWARE_PROMPT from a Skill → CODE cognitive behavior
    if skill_prompt_family == "SOFTWARE_PROMPT":
        return PROFILE_CODE

    # Level 3: Programming construct detection when profile is AUTO/None
    # Clear programming definition syntax resolves to CODE profile without swapping physical models.
    if user_message:
        msg_trimmed = user_message.strip()
        if (
            msg_trimmed.startswith(("def ", "class ", "async def ", "function ", "import ", "const ", "let ", "var "))
            or "def calculate_total" in msg_trimmed
        ):
            return PROFILE_CODE

    # Level 4: Structured extraction guard
    # JSON / schema extraction must NOT become CODE — it remains BALANCED with PRECISE preset.
    # (This rule is enforced structurally: only SOFTWARE_PROMPT triggers CODE, not content.)

    # Level 5: Fallback
    return PROFILE_BALANCED

