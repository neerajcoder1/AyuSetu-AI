"""
Batch/aggregate extraction over a full dialogue transcript.

DialogueEngine/DialoguePlanner already do turn-by-turn extraction live during
the interview (contracts/dialogue.py DialogueState.collected_info). This
pipeline is for the cases that need a second pass over the whole transcript:

  - Reprocessing a stored encounter with an upgraded extractor.
  - A post-hoc QA/consistency pass before summary generation (Module C).
  - Recovering slots the live turn-by-turn pass missed because a fact was
    mentioned in an earlier or later, unrelated turn.

Aggregation rule: for a given slot, keep the extraction with the highest
confidence; ties keep the most recent (patients correct themselves, and the
dialogue planner already treats later same-slot values as corrections, see
ayusetu.ai.conversation.planner.DialoguePlanner).
"""

from typing import Iterable, List, Optional

from contracts.asr_output import ASROutput
from contracts.dialogue import ClinicalSlot, DialogueState, DialogueTurn
from contracts.extraction import ExtractedSlot, ExtractionResult
from ayusetu.ai.conversation.extractor import ClinicalExtractor


class ClinicalExtractionPipeline:
    """Runs a ClinicalExtractor over every patient turn and aggregates results."""

    def __init__(self, extractor: ClinicalExtractor, min_asr_confidence: float = 0.6):
        self.extractor = extractor
        self.min_asr_confidence = min_asr_confidence

    def extract_from_turns(self, turns: Iterable[DialogueTurn]) -> ExtractionResult:
        best: dict[ClinicalSlot, ExtractedSlot] = {}

        for turn in turns:
            if turn.speaker != "patient":
                continue
            if turn.confidence is not None and turn.confidence < self.min_asr_confidence:
                continue

            result = self.extractor.extract(turn.text)
            for ext in result.extractions:
                current = best.get(ext.slot)
                if current is None or ext.confidence >= current.confidence:
                    best[ext.slot] = ext

        return ExtractionResult(extractions=list(best.values()))

    def extract_from_state(self, state: DialogueState) -> ExtractionResult:
        """Convenience wrapper for reprocessing a stored DialogueState."""
        return self.extract_from_turns(state.history)

    def extract_from_asr_stream(self, utterances: Iterable[ASROutput]) -> ExtractionResult:
        """Convenience wrapper for reprocessing a raw list of ASR outputs."""
        turns = [
            DialogueTurn(speaker="patient", text=u.text, language=u.language, confidence=u.confidence)
            for u in utterances
        ]
        return self.extract_from_turns(turns)
