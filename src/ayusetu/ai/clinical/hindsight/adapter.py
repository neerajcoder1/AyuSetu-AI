"""
Hindsight Long-Term Memory Layer — Provider Abstraction & Adapters
================================================───────────────────
Abstract interface and concrete adapters (HTTP API & In-Memory Fallback).
"""

import logging
from typing import Dict, List, Optional, Protocol, runtime_checkable
import httpx

from ayusetu.ai.clinical.hindsight.contracts import (
    HindsightConfig,
    HindsightMemoryRecord,
    HindsightQueryResult,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class HindsightAdapterProtocol(Protocol):
    """Abstract interface for Hindsight memory storage and retrieval."""

    def store_memory(self, record: HindsightMemoryRecord) -> bool:
        """Store a memory record into long-term storage."""
        ...

    def retrieve_context(
        self, patient_id: str, query: str, top_k: int = 3
    ) -> HindsightQueryResult:
        """Query relevant historical memory records for a patient."""
        ...


class HindsightInMemoryAdapter:
    """
    Thread-safe in-memory adapter for offline testing, local execution,
    and fallback when no external API is configured.
    """

    def __init__(self) -> None:
        # Partition records by patient_id to guarantee strict patient isolation
        self._store: Dict[str, List[HindsightMemoryRecord]] = {}

    def store_memory(self, record: HindsightMemoryRecord) -> bool:
        if not record.patient_id or not record.content:
            return False
        if record.patient_id not in self._store:
            self._store[record.patient_id] = []
        self._store[record.patient_id].append(record)
        logger.debug(
            "HindsightInMemoryAdapter: stored record for patient=%s",
            record.patient_id,
        )
        return True

    def retrieve_context(
        self, patient_id: str, query: str, top_k: int = 3
    ) -> HindsightQueryResult:
        if not patient_id or patient_id not in self._store:
            return HindsightQueryResult(patient_id=patient_id, query=query, records=[], relevance_scores=[])

        records = self._store[patient_id]
        if not query or not query.strip():
            # Return most recent records if query is empty
            selected = records[-top_k:]
            scores = [1.0] * len(selected)
            return HindsightQueryResult(
                patient_id=patient_id,
                query=query,
                records=selected,
                relevance_scores=scores,
            )

        # Keyword overlap relevance scoring
        query_words = set(query.lower().split())
        scored_records = []
        for rec in records:
            content_words = set(rec.content.lower().split())
            overlap = len(query_words.intersection(content_words))
            score = float(overlap) / max(len(query_words), 1)
            scored_records.append((score, rec))

        # Sort by relevance score descending
        scored_records.sort(key=lambda x: x[0], reverse=True)
        top_matches = [r for score, r in scored_records[:top_k] if score > 0.0]
        top_scores = [score for score, r in scored_records[:top_k] if score > 0.0]

        # If no keywords matched, fall back to recent records with low relevance score
        if not top_matches and records:
            top_matches = records[-top_k:]
            top_scores = [0.1] * len(top_matches)

        return HindsightQueryResult(
            patient_id=patient_id,
            query=query,
            records=top_matches,
            relevance_scores=top_scores,
        )


class HindsightHTTPAdapter:
    """
    Production HTTP adapter connecting to external Hindsight REST API.

    Resilience & Safety Principles:
    - Never throws uncaught network or API exceptions to callers.
    - If API key is missing or endpoint is unreachable, logs a warning and
      returns a graceful fallback without interrupting the consultation.
    - Never logs authorization headers or secrets.
    """

    def __init__(self, config: Optional[HindsightConfig] = None) -> None:
        self.config = config or HindsightConfig()

    def store_memory(self, record: HindsightMemoryRecord) -> bool:
        if not self.config.enabled or not self.config.api_key:
            logger.debug("Hindsight is disabled or API key missing; skipping HTTP store.")
            return False

        url = f"{self.config.api_url.rstrip('/')}/records"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = record.model_dump(mode="json")

        try:
            with httpx.Client(timeout=self.config.timeout_sec) as client:
                res = client.post(url, json=payload, headers=headers)
                if res.status_code in (200, 201):
                    return True
                logger.warning(
                    "Hindsight API store_memory returned status %d", res.status_code
                )
                return False
        except Exception as exc:
            logger.warning("Hindsight API store_memory request failed: %s", exc)
            return False

    def retrieve_context(
        self, patient_id: str, query: str, top_k: int = 3
    ) -> HindsightQueryResult:
        fallback = HindsightQueryResult(
            patient_id=patient_id, query=query, records=[], relevance_scores=[]
        )
        if not self.config.enabled or not self.config.api_key or not patient_id:
            return fallback

        url = f"{self.config.api_url.rstrip('/')}/query"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        params = {"patient_id": patient_id, "query": query, "top_k": top_k}

        try:
            with httpx.Client(timeout=self.config.timeout_sec) as client:
                res = client.get(url, params=params, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    return HindsightQueryResult.model_validate(data)
                logger.warning(
                    "Hindsight API retrieve_context returned status %d", res.status_code
                )
                return fallback
        except Exception as exc:
            logger.warning("Hindsight API retrieve_context request failed: %s", exc)
            return fallback
