"""Hindsight optional long-term memory module for AyuSetu AI.

Provides resilient, patient-isolated long-term historical memory lookup
and encounter recording without mutating session-scoped ClinicalMemory.
"""

from ayusetu.ai.clinical.hindsight.adapter import (
    HindsightAdapterProtocol,
    HindsightHTTPAdapter,
    HindsightInMemoryAdapter,
)
from ayusetu.ai.clinical.hindsight.contracts import (
    HindsightConfig,
    HindsightMemoryRecord,
    HindsightQueryResult,
)
from ayusetu.ai.clinical.hindsight.manager import HindsightMemoryManager

__all__ = [
    "HindsightConfig",
    "HindsightMemoryRecord",
    "HindsightQueryResult",
    "HindsightAdapterProtocol",
    "HindsightInMemoryAdapter",
    "HindsightHTTPAdapter",
    "HindsightMemoryManager",
]
