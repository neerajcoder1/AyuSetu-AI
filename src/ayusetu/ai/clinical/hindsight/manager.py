"""
Hindsight Long-Term Memory Layer — Manager
===========================================
High-level manager orchestrating memory storage and context retrieval for patients.
"""

import logging
from typing import Optional

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

logger = logging.getLogger(__name__)


class HindsightMemoryManager:
    """
    Orchestrates long-term contextual memory retrieval and storage.

    Safety Principles:
    - Never mutates active ClinicalMemory slots or deterministic extractions.
    - Operates as a purely supplementary contextual layer.
    - Cleanly partitions memory by patient_id.
    - If disabled or unavailable, operations complete silently without error.
    """

    def __init__(
        self,
        config: Optional[HindsightConfig] = None,
        adapter: Optional[HindsightAdapterProtocol] = None,
    ) -> None:
        self.config = config or HindsightConfig()
        if adapter is not None:
            self.adapter = adapter
        elif self.config.enabled and self.config.api_key:
            self.adapter = HindsightHTTPAdapter(self.config)
        else:
            # Fall back to in-memory adapter if HTTP credentials missing or disabled
            self.adapter = HindsightInMemoryAdapter()

    def store_encounter_summary(
        self, patient_id: str, session_id: str, summary_text: str
    ) -> bool:
        """Store a completed encounter summary into long-term memory."""
        if not patient_id or not summary_text:
            return False

        record = HindsightMemoryRecord(
            patient_id=patient_id,
            session_id=session_id,
            content=summary_text,
            metadata={"source": "encounter_summary"},
        )
        try:
            return self.adapter.store_memory(record)
        except Exception as exc:
            logger.warning("Hindsight store_encounter_summary failed: %s", exc)
            return False

    def retrieve_historical_context(
        self, patient_id: str, current_query: str, top_k: int = 3
    ) -> Optional[str]:
        """
        Query relevant historical context snippets for the patient.

        Returns a formatted multi-line string suitable for background context injection,
        or None if no relevant context exists or Hindsight is unavailable.
        """
        if not patient_id:
            return None

        try:
            result: HindsightQueryResult = self.adapter.retrieve_context(
                patient_id=patient_id, query=current_query, top_k=top_k
            )
            return result.format_as_context()
        except Exception as exc:
            logger.warning("Hindsight retrieve_historical_context failed: %s", exc)
            return None
