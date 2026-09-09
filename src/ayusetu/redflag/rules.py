"""
Red-Flag Declarative Clinical Rules Loader & Engine
===================================================
Loads, validates, and evaluates versioned clinical-content rules per PRD v2.0 §12, §16.3 & §22.7.
Treats clinical-content files strictly as DATA (zero eval, zero dynamic execution).
Fail-closed on invalid schema, missing approval metadata, duplicate IDs, or missing content.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from ayusetu.redflag.models import RedFlagTier


@dataclass(frozen=True)
class RuleAction:
    """Action specification executed when a rule matches."""
    escalate: str
    queue_priority: str
    patient_message_key: str = "calm_wait"


@dataclass(frozen=True)
class ClinicalRule:
    """Declarative, versioned clinical safety rule loaded from clinical-content."""
    rule_id: str
    tier: RedFlagTier
    version: int
    title: str
    description: str
    action: RuleAction
    approved_by: str
    approved_at: str
    required_paths: List[str]
    predicate: Callable[[Dict[str, Any]], bool]
    raw_spec: Dict[str, Any] = field(default_factory=dict, repr=False)


# ==============================================================================
# Declarative Predicate Evaluator (Safe Data-Driven Execution)
# ==============================================================================

VALID_OPERATORS = {
    "all", "any", "slot", "in", "contains",
    "is_true", "equals", "eq", "value",
    "min", "max", "lt", "gt", "gte", "lte"
}


def _is_truthy(val: Any) -> bool:
    """Explicit truthiness helper: returns True ONLY if value is explicitly True or positive text."""
    if val is True:
        return True
    if isinstance(val, str) and val.strip().lower() in ("true", "yes", "positive", "present"):
        return True
    return False


def _safe_float(val: Any) -> Optional[float]:
    """Safely convert a value to float for numerical comparisons, returning None on failure."""
    if val is None or isinstance(val, bool):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _evaluate_leaf_predicate(clause: Dict[str, Any], facts: Dict[str, Any]) -> bool:
    """Evaluate a single leaf predicate against structured facts."""
    slot_path = clause.get("slot")
    if not slot_path or not isinstance(slot_path, str):
        raise ValueError(f"Leaf predicate missing valid 'slot' path: {clause}")

    fact_val = facts.get(slot_path)

    # 1. is_true operator
    if "is_true" in clause:
        expected = clause["is_true"]
        if expected is True:
            return _is_truthy(fact_val)
        return not _is_truthy(fact_val)

    # 2. in operator
    if "in" in clause:
        allowed = clause["in"]
        if not isinstance(allowed, (list, tuple, set)):
            raise ValueError(f"'in' operator requires a list: {clause}")
        if fact_val is None:
            return False
        return fact_val in allowed or str(fact_val).lower() in [str(a).lower() for a in allowed]

    # 3. contains operator
    if "contains" in clause:
        needle = clause["contains"]
        if fact_val is None:
            return False
        if isinstance(fact_val, (list, tuple, set)):
            return needle in fact_val or any(str(needle).lower() == str(item).lower() for item in fact_val)
        return str(needle).lower() in str(fact_val).lower()

    # 4. equals / eq / value operator
    for eq_key in ("equals", "eq", "value"):
        if eq_key in clause:
            target = clause[eq_key]
            if fact_val is None:
                return False
            return str(fact_val).strip().lower() == str(target).strip().lower()

    # 5. Numerical comparisons (min / max / lt / gt / gte / lte)
    numeric_val = _safe_float(fact_val)
    if numeric_val is None:
        # If the fact is missing or non-numeric, numerical predicates evaluate to False
        return False

    if "lt" in clause:
        threshold = _safe_float(clause["lt"])
        if threshold is None or not (numeric_val < threshold):
            return False

    if "gt" in clause:
        threshold = _safe_float(clause["gt"])
        if threshold is None or not (numeric_val > threshold):
            return False

    if "min" in clause or "gte" in clause:
        raw_t = clause.get("min", clause.get("gte"))
        threshold = _safe_float(raw_t)
        if threshold is None or not (numeric_val >= threshold):
            return False

    if "max" in clause or "lte" in clause:
        raw_t = clause.get("max", clause.get("lte"))
        threshold = _safe_float(raw_t)
        if threshold is None or not (numeric_val <= threshold):
            return False

    return True


def _evaluate_expression(when_spec: Dict[str, Any], facts: Dict[str, Any]) -> bool:
    """
    Recursively evaluate a declarative 'when' specification without dynamic code execution.
    Fails closed on any unexpected or malformed structure.
    """
    if not isinstance(when_spec, dict):
        raise ValueError(f"Predicate clause must be a dictionary, got: {type(when_spec)}")

    # Check for invalid operators
    for k in when_spec.keys():
        if k not in VALID_OPERATORS:
            raise ValueError(f"Unsupported or dangerous predicate operator '{k}' in rule clause")

    # Handle 'all' (conjunction)
    if "all" in when_spec:
        clauses = when_spec["all"]
        if not isinstance(clauses, list) or len(clauses) == 0:
            raise ValueError(f"'all' operator requires a non-empty list of clauses: {when_spec}")
        return all(_evaluate_expression(c, facts) for c in clauses)

    # Handle 'any' (disjunction)
    if "any" in when_spec:
        clauses = when_spec["any"]
        if not isinstance(clauses, list) or len(clauses) == 0:
            raise ValueError(f"'any' operator requires a non-empty list of clauses: {when_spec}")
        return any(_evaluate_expression(c, facts) for c in clauses)

    # Handle leaf predicate on a slot
    if "slot" in when_spec:
        return _evaluate_leaf_predicate(when_spec, facts)

    raise ValueError(f"Invalid predicate clause: missing 'all', 'any', or 'slot': {when_spec}")


def _extract_slot_paths(when_spec: Dict[str, Any]) -> Set[str]:
    """Recursively extract all referenced slot paths for provenance and telemetry."""
    paths: Set[str] = set()
    if not isinstance(when_spec, dict):
        return paths

    if "slot" in when_spec and isinstance(when_spec["slot"], str):
        paths.add(when_spec["slot"])

    for sub in when_spec.get("all", []):
        paths.update(_extract_slot_paths(sub))

    for sub in when_spec.get("any", []):
        paths.update(_extract_slot_paths(sub))

    return paths


# ==============================================================================
# Declarative Clinical Rule Loader
# ==============================================================================

def get_clinical_content_dir() -> Path:
    """Resolve the authoritative clinical-content redflags directory."""
    env_path = os.getenv("CLINICAL_CONTENT_DIR")
    if env_path:
        path = Path(env_path) / "redflags"
        if path.is_dir():
            return path

    # Traverse upward from current file to find packages/clinical-content/redflags
    cur = Path(__file__).resolve()
    for parent in [cur] + list(cur.parents):
        candidate = parent / "packages" / "clinical-content" / "redflags"
        if candidate.is_dir():
            return candidate

    # Absolute fallback relative to standard workspace layout
    return Path("e:/AyuSetu-AI/packages/clinical-content/redflags")


class DeclarativeRuleLoader:
    """
    Authoritative loader for versioned clinical-content red-flag rules.
    Enforces CAB approval metadata, schema validity, uniqueness, and fail-closed security.
    """

    @classmethod
    def parse_rule_dict(cls, data: Dict[str, Any], source_file: str = "<data>") -> ClinicalRule:
        """Validate and parse a single rule dictionary into a ClinicalRule."""
        # 1. Validate required fields
        required_fields = ["id", "tier", "version", "title", "description", "when", "action", "approved_by", "approved_at"]
        for rf in required_fields:
            if rf not in data:
                raise ValueError(f"Rule in {source_file} missing mandatory field '{rf}'")

        rule_id = str(data["id"]).strip()
        if not rule_id:
            raise ValueError(f"Rule in {source_file} has empty 'id'")

        # 2. Validate tier
        try:
            tier_val = int(data["tier"])
            tier = RedFlagTier(tier_val)
        except (ValueError, TypeError):
            raise ValueError(f"Rule '{rule_id}' in {source_file} has invalid tier: {data.get('tier')}")

        # 3. Validate version
        try:
            version = int(data["version"])
            if version < 1:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError(f"Rule '{rule_id}' in {source_file} has invalid version: {data.get('version')}")

        # 4. Validate approval metadata
        approved_by = str(data["approved_by"]).strip()
        approved_at = str(data["approved_at"]).strip()
        if not approved_by or not approved_at:
            raise ValueError(f"Rule '{rule_id}' in {source_file} missing required CAB approval metadata")

        # 5. Validate action
        action_data = data["action"]
        if not isinstance(action_data, dict) or "escalate" not in action_data or "queue_priority" not in action_data:
            raise ValueError(f"Rule '{rule_id}' in {source_file} has invalid 'action' block")
        action = RuleAction(
            escalate=str(action_data["escalate"]),
            queue_priority=str(action_data["queue_priority"]),
            patient_message_key=str(action_data.get("patient_message_key", "calm_wait")),
        )

        # 6. Validate predicate structure and pre-extract paths
        when_spec = data["when"]
        if not isinstance(when_spec, dict):
            raise ValueError(f"Rule '{rule_id}' in {source_file} has non-dict 'when' specification")

        # Dry-run evaluation on empty dict to validate syntax and fail closed if malformed
        try:
            _evaluate_expression(when_spec, {})
        except ValueError as e:
            raise ValueError(f"Rule '{rule_id}' in {source_file} has malformed predicate: {e}")

        required_paths = sorted(list(_extract_slot_paths(when_spec)))

        # Create safe closure for predicate evaluation
        def predicate(facts: Dict[str, Any]) -> bool:
            return _evaluate_expression(when_spec, facts)

        return ClinicalRule(
            rule_id=rule_id,
            tier=tier,
            version=version,
            title=str(data["title"]).strip(),
            description=str(data["description"]).strip(),
            action=action,
            approved_by=approved_by,
            approved_at=approved_at,
            required_paths=required_paths,
            predicate=predicate,
            raw_spec=data,
        )

    @classmethod
    def load_from_directory(cls, directory: Optional[Path] = None) -> List[ClinicalRule]:
        """
        Load and validate all JSON rules from the target clinical-content directory.
        Fails closed on missing directory, malformed JSON, schema violation, or duplicate IDs.
        """
        dir_path = directory or get_clinical_content_dir()
        if not dir_path.is_dir():
            raise RuntimeError(f"Clinical-content rules directory does not exist: {dir_path}")

        json_files = sorted(dir_path.glob("*.json"))
        if not json_files:
            raise RuntimeError(f"No clinical-content rule files found in: {dir_path}")

        loaded_rules: List[ClinicalRule] = []
        seen_rule_ids: Set[str] = set()

        for json_file in json_files:
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    content = json.load(f)
            except Exception as e:
                raise ValueError(f"Failed to read/parse JSON from {json_file}: {e}")

            rule = cls.parse_rule_dict(content, source_file=json_file.name)
            if rule.rule_id in seen_rule_ids:
                raise ValueError(f"Duplicate clinical rule ID '{rule.rule_id}' detected in {json_file.name}")

            seen_rule_ids.add(rule.rule_id)
            loaded_rules.append(rule)

        return loaded_rules


# ==============================================================================
# Global Rules Registry (Lazily Initialized from Versioned Content)
# ==============================================================================

_ACTIVE_REGISTRY: Optional[List[ClinicalRule]] = None


def get_clinical_rules_registry() -> List[ClinicalRule]:
    """Retrieve active clinical rules registry loaded from versioned clinical-content."""
    global _ACTIVE_REGISTRY
    if _ACTIVE_REGISTRY is None:
        _ACTIVE_REGISTRY = DeclarativeRuleLoader.load_from_directory()
    return _ACTIVE_REGISTRY


def reset_rules_registry_for_testing(rules: Optional[List[ClinicalRule]] = None) -> None:
    """Reset or override active rules registry for test isolation."""
    global _ACTIVE_REGISTRY
    _ACTIVE_REGISTRY = rules


def get_rule_by_id(rule_id: str) -> Optional[ClinicalRule]:
    """Look up a clinical rule by its authoritative identifier."""
    for rule in get_clinical_rules_registry():
        if rule.rule_id == rule_id:
            return rule
    return None


# Module-level alias for backward-compatible engine consumption
class _RegistryProxy(list):
    """Proxy list dynamically reflecting active loaded registry."""
    def __iter__(self):
        return iter(get_clinical_rules_registry())

    def __len__(self):
        return len(get_clinical_rules_registry())

    def __getitem__(self, idx):
        return get_clinical_rules_registry()[idx]


CLINICAL_RULES_REGISTRY = _RegistryProxy()
