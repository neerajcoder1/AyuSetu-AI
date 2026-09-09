"""
Evaluator for the `when` condition tree in a RedFlagRule (PRD §22.7).

Supported node shapes:
    {"all": [cond, cond, ...]}                  -- AND
    {"any": [cond, cond, ...]}                   -- OR
    {"slot": "<path>", "in": [v1, v2, ...]}       -- slot value is one of v1..vn
    {"slot": "<path>", "contains": "<needle>"}    -- slot value contains needle
                                                      (substring for strings,
                                                       membership for lists)

`context` is a flat dict of slot-path -> value. Missing slot paths evaluate
every leaf condition on them to False rather than raising, since "not
elicited" must never be treated as a match (the same elicited/not-elicited
discipline as Gate 5 in Module C, and the `memory` module's timeline).
"""

from typing import Any, Dict


def evaluate_condition(condition: Dict[str, Any], context: Dict[str, Any]) -> bool:
    if "all" in condition:
        return all(evaluate_condition(c, context) for c in condition["all"])

    if "any" in condition:
        return any(evaluate_condition(c, context) for c in condition["any"])

    if "slot" in condition:
        value = context.get(condition["slot"])
        if value is None:
            return False

        if "in" in condition:
            return value in condition["in"]

        if "contains" in condition:
            needle = condition["contains"]
            if isinstance(value, (list, tuple, set)):
                return any(_contains_ci(str(v), needle) for v in value)
            return _contains_ci(str(value), needle)

    raise ValueError(f"Unrecognised condition node: {condition!r}")


def _contains_ci(haystack: str, needle: str) -> bool:
    return needle.lower() in haystack.lower()
