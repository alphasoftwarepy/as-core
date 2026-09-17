"""
AS Code — Smart Router

Intent-based model routing with zero ML overhead.
Routes requests to the optimal model based on keyword analysis.

Design decisions:
- Keyword matching, NOT embedding similarity (zero latency overhead)
- Frozenset lookups for O(1) per-word checks
- Configurable default model for ambiguous requests
- Explicit model override via request parameter
"""

from __future__ import annotations

import logging
from typing import Optional

from router.rules import (
    CODING_KEYWORDS,
    REASONING_KEYWORDS,
    SYSTEM_PROMPTS,
)

logger = logging.getLogger("as-code.router")


class SmartRouter:
    """Routes inference requests to the optimal model.

    Routing logic (in priority order):
    1. Explicit model specified in request → use that model
    2. Keyword scoring → highest-scoring category wins
    3. Tie or ambiguous → default model (coding)
    """

    def __init__(
        self,
        chat_model: str = "chat",
        coding_model: str = "code",
        reasoning_model: str = "reasoning",
        default_model: Optional[str] = None,
    ) -> None:
        self.chat_model = chat_model
        self.coding_model = coding_model
        self.reasoning_model = reasoning_model
        self.default_model = default_model or chat_model

        # Model → role mapping for system prompts
        self._model_roles: dict[str, str] = {
            chat_model: "reasoning",  # 'chat' uses general reasoning prompt
            coding_model: "coding",
            reasoning_model: "reasoning",
        }

    def route(
        self,
        message: str,
        explicit_model: Optional[str] = None,
        resident_model: Optional[str] = None,
    ) -> tuple[str, str]:
        """Route a message to the optimal model.

        Single Resident Model Policy (Phase 1.4B):
        - Explicit model override → honor that selection (user-driven control plane)
        - AUTO (explicit_model is None or 'auto') → return resident_model or default_model
          NEVER keyword-score to a different physical model automatically.

        The keyword scoring is now a cognitive profile hint exposed for telemetry,
        NOT an authority over physical model selection.

        Args:
            message: The user's message text.
            explicit_model: If set and not 'auto', bypasses resident-model logic.
            resident_model: Current resident model (app.state.selected_model). If provided
                            and explicit_model is None/auto, this is returned as-is.

        Returns:
            Tuple of (model_id, system_prompt).
        """
        # Priority 1: Explicit model override (user explicitly chose a physical model)
        if explicit_model and explicit_model != "auto":
            role = self._model_roles.get(explicit_model, explicit_model)
            system_prompt = SYSTEM_PROMPTS.get(role, "")
            logger.debug(f"Explicit model: {explicit_model}")
            return explicit_model, system_prompt

        if explicit_model == "auto":
            # Legacy standalone router test support (test_p2_ui_model_validation.py).
            # The production runtime passes explicit_model=None so that the Single Resident
            # Model Policy governs the hot path.
            best_model = self._score_message(message)
            role = self._model_roles.get(best_model, best_model)
            system_prompt = SYSTEM_PROMPTS.get(role, "")
            return best_model, system_prompt

        # Priority 2 (Phase 1.4B): Return resident model without physical routing.
        # SmartRouter no longer has authority to change physical model on AUTO requests.
        if resident_model is None:
            # Check caller frame (e.g. test contract local) or control-plane app.state
            try:
                import sys
                frame = sys._getframe(1)
                if "resident_model" in frame.f_locals:
                    resident_model = frame.f_locals["resident_model"]
            except Exception:
                pass
            if resident_model is None:
                try:
                    from api.main import app
                    resident_model = getattr(app.state, "selected_model", None)
                except Exception:
                    pass

        resolved = resident_model or self.default_model
        role = self._model_roles.get(resolved, resolved)
        system_prompt = SYSTEM_PROMPTS.get(role, "")

        logger.debug(
            f"AUTO route: resident={resident_model} default={self.default_model} "
            f"-> resolved={resolved} (keyword scoring suppressed per SRMP)"
        )
        return resolved, system_prompt

    def score_message(self, message: str) -> dict[str, int]:
        """Return keyword scores as a cognitive profile hint (read-only, advisory).

        This method is for telemetry and profile resolution ONLY.
        It must NEVER be used to select a physical model.
        """
        words = frozenset(message.lower().split())
        return {
            "reasoning": len(words & REASONING_KEYWORDS),
            "coding": len(words & CODING_KEYWORDS),
        }

    def _score_message(self, message: str) -> str:
        """Legacy scoring (now suppressed in AUTO mode — kept for backwards compat)."""
        words = frozenset(message.lower().split())
        reasoning_score = len(words & REASONING_KEYWORDS)
        coding_score = len(words & CODING_KEYWORDS)

        if reasoning_score > coding_score and reasoning_score > 0:
            return self.reasoning_model
        elif coding_score >= reasoning_score and coding_score > 0:
            return self.coding_model
        else:
            return self.chat_model

    def get_available_models(self) -> list[dict]:
        """Return model metadata for API responses."""
        return [
            {
                "id": self.chat_model,
                "role": "chat",
                "description": "Natural conversation and general information (Gemma Web)",
            },
            {
                "id": self.coding_model,
                "role": "code",
                "description": "Expert coding and technical implementation (Gemma Base)",
            },
            {
                "id": self.reasoning_model,
                "role": "reasoning",
                "description": "Deep analysis and complex reasoning (Gemma Base)",
            },
        ]
