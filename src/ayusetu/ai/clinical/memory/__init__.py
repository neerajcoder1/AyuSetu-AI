"""
AyuSetu AI — Session-Scoped Clinical Memory
=============================================
Persists structured clinical information extracted across conversation turns
for a single patient session.

Design principles
-----------------
* One `ClinicalMemory` instance per session — never a global singleton.
  The `DialogueEngine` holds the reference; the `SessionManager` in
  `voice_pipeline.py` owns the lifecycle.
* The memory does NOT influence the interview flow.  The ontology/planner
  still owns the sequence of questions.  The memory is a side-channel
  read by downstream components (red-flag detection, summary generation,
  FHIR export) once those modules are implemented.
* A lower-confidence extraction never overwrites a higher-confidence one.
* Every update is traceable: source utterance, confidence, timestamp, and
  the full history of previous values are preserved.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from contracts.dialogue import ClinicalSlot
from contracts.extraction import ExtractedSlot

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class SlotEntry:
    """The current best value for a single clinical slot, with full history."""
    slot: ClinicalSlot
    value: str
    confidence: float
    source_utterance: str
    extracted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    history: List["SlotEntry"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "slot": self.slot.value,
            "value": self.value,
            "confidence": self.confidence,
            "source_utterance": self.source_utterance,
            "extracted_at": self.extracted_at.isoformat(),
            "history": [h.to_dict() for h in self.history],
        }


@dataclass
class ClinicalSnapshot:
    """
    A read-only, typed view of the current memory state.

    Intended for downstream components (red-flag detection, summary
    generation, FHIR export).  Not used to drive the interview flow.
    """
    slots: Dict[ClinicalSlot, SlotEntry] = field(default_factory=dict)

    def get(self, slot: ClinicalSlot) -> Optional[SlotEntry]:
        return self.slots.get(slot)

    def collected_slots(self) -> List[ClinicalSlot]:
        return list(self.slots.keys())

    def to_dict(self) -> dict:
        return {k.value: v.to_dict() for k, v in self.slots.items()}


# ---------------------------------------------------------------------------
# ClinicalMemory
# ---------------------------------------------------------------------------

class ClinicalMemory:
    """
    Session-scoped clinical memory.

    Stores the best-confidence extraction for each ``ClinicalSlot`` and
    maintains a full update history for traceability.

    Thread-safety
    -------------
    Each session runs synchronously (FastAPI's default thread-pool model
    with one request at a time per session), so no locking is needed.
    If async handlers are introduced, add an ``asyncio.Lock``.

    Usage
    -----
    Created once per session by ``DialogueEngine.__init__``:

        engine = DialogueEngine(memory=ClinicalMemory())

    Updated after every extraction:

        memory.update_from_extractions(extracted_slots, source_utterance)

    Read by downstream code:

        snapshot = memory.get_current_snapshot()
    """

    def __init__(self) -> None:
        self._slots: Dict[ClinicalSlot, SlotEntry] = {}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def update_from_extractions(
        self,
        extracted_slots: Sequence[ExtractedSlot],
        source_utterance: str,
    ) -> None:
        """
        Merge a list of extracted slots into the memory.

        Rules
        -----
        * A new slot is stored unconditionally.
        * An existing slot is **only overwritten** when the incoming
          confidence is **strictly greater than** the stored confidence.
          This guarantees that a weak extraction never clobbers a strong one.
        * The superseded entry is pushed onto the ``history`` list for
          traceability.

        Parameters
        ----------
        extracted_slots:
            Slots produced by the clinical extractor for a single turn.
        source_utterance:
            The raw transcribed text that produced these extractions.
            Stored for audit / traceability.
        """
        for ext in extracted_slots:
            existing = self._slots.get(ext.slot)

            if existing is None:
                # First time seeing this slot — store it.
                entry = SlotEntry(
                    slot=ext.slot,
                    value=ext.value,
                    confidence=ext.confidence,
                    source_utterance=source_utterance,
                )
                self._slots[ext.slot] = entry
                logger.debug(
                    "ClinicalMemory: new slot %s = %r (conf=%.2f)",
                    ext.slot.value, ext.value, ext.confidence,
                )
            elif ext.confidence > existing.confidence:
                # Higher-confidence extraction — promote it, archive old.
                archived = SlotEntry(
                    slot=existing.slot,
                    value=existing.value,
                    confidence=existing.confidence,
                    source_utterance=existing.source_utterance,
                    extracted_at=existing.extracted_at,
                    history=existing.history,
                )
                new_entry = SlotEntry(
                    slot=ext.slot,
                    value=ext.value,
                    confidence=ext.confidence,
                    source_utterance=source_utterance,
                    history=[archived],
                )
                self._slots[ext.slot] = new_entry
                logger.debug(
                    "ClinicalMemory: updated slot %s %r→%r (conf %.2f→%.2f)",
                    ext.slot.value,
                    existing.value, ext.value,
                    existing.confidence, ext.confidence,
                )
            else:
                # Lower or equal confidence — keep existing, log and discard.
                logger.debug(
                    "ClinicalMemory: kept existing slot %s = %r (existing conf=%.2f "
                    ">= new conf=%.2f); discarding new value %r.",
                    ext.slot.value,
                    existing.value,
                    existing.confidence,
                    ext.confidence,
                    ext.value,
                )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_current_snapshot(self) -> ClinicalSnapshot:
        """Return an immutable view of the current memory state."""
        return ClinicalSnapshot(slots=dict(self._slots))

    def get_slot(self, slot: ClinicalSlot) -> Optional[SlotEntry]:
        """Return the current best entry for *slot*, or ``None``."""
        return self._slots.get(slot)

    def __repr__(self) -> str:
        return (
            f"ClinicalMemory(slots={[s.value for s in self._slots]})"
        )
