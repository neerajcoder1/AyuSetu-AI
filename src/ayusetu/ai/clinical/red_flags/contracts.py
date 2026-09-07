"""
Internal data contracts for the red-flag and priority triage engine (PRD §12).

Rule shape mirrors the PRD §22.7 example verbatim:

    { "id": "RF-CARD-01", "tier": 1, "version": 3,
      "title": "Possible acute coronary syndrome",
      "when": {"all": [...]},
      "action": {"escalate": "triage_desk", "queue_priority": "immediate",
                 "patient_message_key": "calm_wait"},
      "approved_by": "CAB-2026-03", "approved_at": "2026-03-14" }

Rules are DATA (plain dicts/JSON), not code — "adding a red flag must never
require a code deployment" (§16.3, §22.7). RedFlagRule.when is therefore a
raw dict evaluated by ayusetu.ai.clinical.red_flags.dsl, not a typed model.

RedFlagEvent mirrors the PRD §22.3 `red_flag_event` table.
"""

from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class Tier(IntEnum):
    TIER_1 = 1  # human-interrupting alert
    TIER_2 = 2  # silent queue re-prioritisation
    TIER_3 = 3  # inline flag only, attached to the summary


class RuleAction(BaseModel):
    escalate: Optional[str] = None
    queue_priority: Optional[str] = None
    patient_message_key: Optional[str] = None


class RedFlagRule(BaseModel):
    id: str
    tier: Tier
    version: int
    title: str
    category: str
    when: Dict[str, Any]
    action: RuleAction
    approved_by: str
    approved_at: str


class RedFlagEvent(BaseModel):
    encounter_id: str
    rule_id: str
    tier: Tier
    category: str
    title: str
    trigger_text: str
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    detection_layer: str = Field(..., description='"rule" or "classifier"')
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    outcome: Optional[str] = None

    def acknowledge(self, by: str, at: Optional[datetime] = None, outcome: Optional[str] = None) -> None:
        self.acknowledged_by = by
        self.acknowledged_at = at or datetime.now(timezone.utc)
        self.outcome = outcome
