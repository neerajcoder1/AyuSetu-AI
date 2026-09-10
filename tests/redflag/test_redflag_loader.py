"""
Red-Flag Declarative Clinical-Content Rule Loader Tests
=======================================================
Validates the declarative JSON rule loader, schema enforcement, CAB approval metadata,
expression safety, fail-closed error handling, and zero-eval execution.
"""

import json
import os
import tempfile
from pathlib import Path
import pytest

from ayusetu.redflag.models import RedFlagTier
from ayusetu.redflag.rules import (
    DeclarativeRuleLoader,
    ClinicalRule,
    get_clinical_rules_registry,
    get_rule_by_id,
    reset_rules_registry_for_testing,
)


def test_loader_loads_all_15_authoritative_rules():
    """Verify loader successfully parses all 15 versioned clinical-content rules."""
    reset_rules_registry_for_testing(None)
    rules = get_clinical_rules_registry()
    assert len(rules) == 15

    rule_ids = {r.rule_id for r in rules}
    expected_ids = {
        "RF-CARD-001", "RF-RESP-001", "RF-NEURO-001", "RF-IMM-001", "RF-HEM-001",
        "RF-CARD-002", "RF-INF-001", "RF-GI-001", "RF-ENDO-001",
        "RF-ALLERGY-001", "RF-OB-001", "RF-SEPSIS-001", "RF-PAED-001",
        "RF-PSYCH-001", "RF-TRAUMA-001"
    }
    assert rule_ids == expected_ids


def test_rule_versions_and_cab_approval_metadata_exposed():
    """Verify version, approved_by, and approved_at are populated on all loaded rules."""
    rules = get_clinical_rules_registry()
    for rule in rules:
        assert isinstance(rule.version, int)
        assert rule.version >= 1
        assert rule.approved_by.startswith("CAB-")
        assert len(rule.approved_at) >= 10  # Valid ISO date string
        assert isinstance(rule.tier, RedFlagTier)
        assert rule.description
        assert rule.title
        assert len(rule.required_paths) > 0


def test_missing_approved_by_fails_closed():
    """Verify missing approved_by metadata raises ValueError and fails closed."""
    invalid_data = {
        "id": "RF-TEST-001",
        "tier": 1,
        "version": 1,
        "title": "Unapproved Rule",
        "description": "Rule without CAB signoff",
        "when": {"slot": "symptoms.chest_pain", "is_true": True},
        "action": {"escalate": "triage_desk", "queue_priority": "immediate"},
        # "approved_by" missing
        "approved_at": "2026-03-14",
    }
    with pytest.raises(ValueError, match="missing mandatory field 'approved_by'"):
        DeclarativeRuleLoader.parse_rule_dict(invalid_data, source_file="test.json")


def test_missing_approved_at_fails_closed():
    """Verify missing approved_at metadata raises ValueError and fails closed."""
    invalid_data = {
        "id": "RF-TEST-001",
        "tier": 1,
        "version": 1,
        "title": "Unapproved Rule",
        "description": "Rule without CAB timestamp",
        "when": {"slot": "symptoms.chest_pain", "is_true": True},
        "action": {"escalate": "triage_desk", "queue_priority": "immediate"},
        "approved_by": "CAB-2026-03",
        # "approved_at" missing
    }
    with pytest.raises(ValueError, match="missing mandatory field 'approved_at'"):
        DeclarativeRuleLoader.parse_rule_dict(invalid_data, source_file="test.json")


def test_missing_version_fails_closed():
    """Verify missing version raises ValueError and fails closed."""
    invalid_data = {
        "id": "RF-TEST-001",
        "tier": 1,
        # "version" missing
        "title": "Unversioned Rule",
        "description": "Rule without version",
        "when": {"slot": "symptoms.chest_pain", "is_true": True},
        "action": {"escalate": "triage_desk", "queue_priority": "immediate"},
        "approved_by": "CAB-2026-03",
        "approved_at": "2026-03-14",
    }
    with pytest.raises(ValueError, match="missing mandatory field 'version'"):
        DeclarativeRuleLoader.parse_rule_dict(invalid_data, source_file="test.json")


def test_invalid_tier_fails_closed():
    """Verify invalid tier (e.g. tier 4 or 0) raises ValueError."""
    invalid_data = {
        "id": "RF-TEST-001",
        "tier": 99,
        "version": 1,
        "title": "Invalid Tier Rule",
        "description": "Rule with invalid tier",
        "when": {"slot": "symptoms.chest_pain", "is_true": True},
        "action": {"escalate": "triage_desk", "queue_priority": "immediate"},
        "approved_by": "CAB-2026-03",
        "approved_at": "2026-03-14",
    }
    with pytest.raises(ValueError, match="invalid tier"):
        DeclarativeRuleLoader.parse_rule_dict(invalid_data, source_file="test.json")


def test_duplicate_rule_ids_fail_closed():
    """Verify duplicate rule IDs in clinical-content directory cause load_from_directory to fail closed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        rule_data_1 = {
            "id": "RF-DUP-001",
            "tier": 1,
            "version": 1,
            "title": "Rule One",
            "description": "First instance",
            "when": {"slot": "symptoms.chest_pain", "is_true": True},
            "action": {"escalate": "triage_desk", "queue_priority": "immediate"},
            "approved_by": "CAB-2026-03",
            "approved_at": "2026-03-14",
        }
        rule_data_2 = {
            "id": "RF-DUP-001",
            "tier": 1,
            "version": 2,
            "title": "Rule Duplicate",
            "description": "Duplicate ID instance",
            "when": {"slot": "symptoms.chest_pain", "is_true": True},
            "action": {"escalate": "triage_desk", "queue_priority": "immediate"},
            "approved_by": "CAB-2026-03",
            "approved_at": "2026-03-14",
        }

        with open(tmp_path / "rule1.json", "w", encoding="utf-8") as f:
            json.dump(rule_data_1, f)
        with open(tmp_path / "rule2.json", "w", encoding="utf-8") as f:
            json.dump(rule_data_2, f)

        with pytest.raises(ValueError, match="Duplicate clinical rule ID 'RF-DUP-001'"):
            DeclarativeRuleLoader.load_from_directory(tmp_path)


def test_unsupported_or_malicious_operator_fails_closed():
    """Verify unsupported operator or injection attempt fails closed at parse time."""
    malicious_data = {
        "id": "RF-INJ-001",
        "tier": 1,
        "version": 1,
        "title": "Injection Attempt",
        "description": "Attempts code evaluation",
        "when": {
            "slot": "symptoms.chest_pain",
            "__import__": "os.system('id')",
        },
        "action": {"escalate": "triage_desk", "queue_priority": "immediate"},
        "approved_by": "CAB-2026-03",
        "approved_at": "2026-03-14",
    }
    with pytest.raises(ValueError, match="Unsupported or dangerous predicate operator"):
        DeclarativeRuleLoader.parse_rule_dict(malicious_data, source_file="inj.json")


def test_nonexistent_directory_fails_closed():
    """Verify attempting to load from non-existent directory raises RuntimeError."""
    fake_path = Path("/nonexistent/clinical/content/path/12345")
    with pytest.raises(RuntimeError, match="does not exist"):
        DeclarativeRuleLoader.load_from_directory(fake_path)


def test_empty_directory_fails_closed():
    """Verify loading from an empty directory raises RuntimeError without silent empty fallback."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        with pytest.raises(RuntimeError, match="No clinical-content rule files found"):
            DeclarativeRuleLoader.load_from_directory(tmp_path)


def test_declarative_predicate_evaluation_no_eval_used():
    """Verify declarative predicate evaluates accurately without eval."""
    rule = get_rule_by_id("RF-CARD-001")
    assert rule is not None

    # Positive match
    assert rule.predicate({"symptoms.chest_pain": True, "symptoms.radiation": True}) is True
    assert rule.predicate({"symptoms.chest_pain": "yes", "symptoms.diaphoresis": "true"}) is True

    # Negative match
    assert rule.predicate({"symptoms.chest_pain": True, "symptoms.radiation": False}) is False
    assert rule.predicate({"symptoms.chest_pain": False}) is False
    assert rule.predicate({}) is False
