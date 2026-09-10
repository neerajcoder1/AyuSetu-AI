"""
k-Anonymity Evaluator for De-Identified Datasets
================================================
Implements PRD v2.0 §21.9 dynamic k-anonymity validation (k >= 5)
over the centrally approved quasi-identifier set:
(age_band, sex, district_or_state, department).

Calculates exact equivalence classes across the complete set without omitting fields.
"""

from collections import Counter
from typing import Dict, List, NamedTuple, Tuple

from ayusetu.deid.models import DeidentifiedRecord
from ayusetu.deid.policy import APPROVED_QUASI_IDENTIFIERS, MIN_K_ANONYMITY_THRESHOLD


class KAnonymityResult(NamedTuple):
    is_compliant: bool
    k_threshold: int
    min_class_size: int
    total_records: int
    total_classes: int
    class_distribution: Dict[Tuple[str, ...], int]


def get_quasi_identifier_tuple(record: DeidentifiedRecord) -> Tuple[str, ...]:
    """
    Extracts the exact tuple corresponding to all approved quasi-identifiers.
    """
    return tuple(getattr(record, qi_name, "") for qi_name in APPROVED_QUASI_IDENTIFIERS)


def evaluate_k_anonymity(
    records: List[DeidentifiedRecord],
    k_threshold: int = MIN_K_ANONYMITY_THRESHOLD,
) -> KAnonymityResult:
    """
    Calculates exact equivalence classes across the complete quasi-identifier set.
    Fails closed (is_compliant = False) if any class has fewer than k_threshold records
    or if dataset is empty.
    """
    if not records:
        return KAnonymityResult(
            is_compliant=False,
            k_threshold=k_threshold,
            min_class_size=0,
            total_records=0,
            total_classes=0,
            class_distribution={},
        )

    class_counts: Counter = Counter()
    for record in records:
        qi_tuple = get_quasi_identifier_tuple(record)
        class_counts[qi_tuple] += 1

    min_size = min(class_counts.values()) if class_counts else 0
    is_compliant = (min_size >= k_threshold) and (len(records) >= k_threshold)

    return KAnonymityResult(
        is_compliant=is_compliant,
        k_threshold=k_threshold,
        min_class_size=min_size,
        total_records=len(records),
        total_classes=len(class_counts),
        class_distribution=dict(class_counts),
    )
