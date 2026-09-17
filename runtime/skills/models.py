from pydantic import BaseModel, field_validator
from typing import List, Optional

class SkillManifest(BaseModel):
    id: str
    name: str
    description: str
    required_scopes: List[str] = []
    enabled: bool = True
    prompt_family: Optional[str] = None
    uses_capabilities: bool = False

    # DEPRECATED (Phase 1.4B): Physical model recommendation from Skills.
    # Under Single Resident Model Policy, this field is advisory-only and
    # is always coerced to None. The runtime NEVER uses this to select a model.
    # Retained here only to gracefully handle legacy skill YAML that may include it.
    recommended_model: Optional[str] = None

    @field_validator("recommended_model", mode="before")
    @classmethod
    def strip_deprecated_recommended_model(cls, v: Optional[str]) -> None:
        """Discard any recommended_model value — it must never influence physical routing."""
        return None

class SkillStatus(BaseModel):
    id: str
    name: str
    description: str
    compatible: bool
    reason: Optional[str] = None
    enabled: bool
