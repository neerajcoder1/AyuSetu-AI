"""
AyuSetu Red-Flag Engine Package
===============================
Deterministic clinical safety rule evaluation, 3-tier severity classification,
and clinician escalation lifecycle.
"""

from ayusetu.redflag.models import (
    RedFlagTier,
    RedFlagStatus,
    StructuredClinicalFact,
    RedFlagEvaluateRequest,
    RedFlagEventDTO,
    AcknowledgeRequest,
    EscalateRequest,
    ResolveRequest,
    Tier1AlertQueueItem,
)
from ayusetu.redflag.rules import ClinicalRule, CLINICAL_RULES_REGISTRY, get_rule_by_id
from ayusetu.redflag.engine import RedFlagEngine, red_flag_engine
from ayusetu.redflag.escalation import RedFlagLifecycle, red_flag_lifecycle
from ayusetu.redflag.service import RedFlagService, red_flag_service

__all__ = [
    "RedFlagTier",
    "RedFlagStatus",
    "StructuredClinicalFact",
    "RedFlagEvaluateRequest",
    "RedFlagEventDTO",
    "AcknowledgeRequest",
    "EscalateRequest",
    "ResolveRequest",
    "Tier1AlertQueueItem",
    "ClinicalRule",
    "CLINICAL_RULES_REGISTRY",
    "get_rule_by_id",
    "RedFlagEngine",
    "red_flag_engine",
    "RedFlagLifecycle",
    "red_flag_lifecycle",
    "RedFlagService",
    "red_flag_service",
]
