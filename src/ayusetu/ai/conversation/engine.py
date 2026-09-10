from typing import Optional
from contracts.asr_output import ASROutput
from contracts.extraction import ExtractionResult
from contracts.dialogue import DialogueState, DialogueTurn
from ayusetu.ai.conversation.planner import DialoguePlanner
from ayusetu.ai.conversation.extractor import ClinicalExtractor, DeterministicRuleExtractor
from ayusetu.ai.conversation.wording import WordingLLM
from ayusetu.ai.conversation.llm_provider import OpenAICompatibleProvider
from ayusetu.ai.clinical.memory import ClinicalMemory


class DialogueEngine:
    """
    Main orchestrator for Phase 2.
    Connects: ASR Output -> Extractor -> Planner -> Wording LLM

    Session-scoped ClinicalMemory
    ------------------------------
    Each ``DialogueEngine`` instance now owns exactly one ``ClinicalMemory``
    that accumulates extracted clinical slots across all turns in the session.
    The memory is a side-channel for downstream components (red-flag detection,
    summary generation, FHIR export).  It does NOT influence the planner or
    the interview flow.

    To keep each session strictly isolated, the caller (``VoicePipeline`` /
    ``SessionManager``) creates a fresh ``DialogueEngine`` per session, OR
    passes a session-specific ``ClinicalMemory`` instance via the constructor.
    By default (``memory=None``) a new ``ClinicalMemory`` is instantiated,
    guaranteeing isolation.
    """

    def __init__(self,
                 extractor: Optional[ClinicalExtractor] = None,
                 llm_provider=None,
                 asr_confidence_threshold: float = 0.6,
                 extraction_confidence_threshold: float = 0.7,
                 memory: Optional[ClinicalMemory] = None):

        self.extractor = extractor or DeterministicRuleExtractor()

        provider = llm_provider or OpenAICompatibleProvider()
        self.wording_llm = WordingLLM(provider)

        self.planner = DialoguePlanner(
            asr_confidence_threshold=asr_confidence_threshold,
            extraction_confidence_threshold=extraction_confidence_threshold
        )

        # Each engine instance gets its own ClinicalMemory.
        # Passing an explicit instance is supported for testing.
        self.memory: ClinicalMemory = memory if memory is not None else ClinicalMemory()

    def initialize(self) -> DialogueState:
        """Returns a fresh dialogue state."""
        return self.planner.initialize_state()

    def step(self, asr_output: ASROutput, state: DialogueState) -> str:
        """
        Process a single turn of the dialogue.
        Updates state in place and returns the worded question from the AI.
        """
        # 1. Extract info (only if ASR confidence is sufficient)
        extraction_result = ExtractionResult(extractions=[])
        if asr_output.confidence >= self.planner.asr_confidence_threshold:
            extraction_result = self.extractor.extract(asr_output.text)

            # 1b. Update session-scoped clinical memory with extractions.
            #     Only slots that meet the extraction confidence threshold
            #     are meaningful, but we store all of them in memory
            #     (including low-confidence ones) so downstream components
            #     can make their own decisions.  The memory's own update
            #     logic ensures lower-confidence values never overwrite
            #     higher-confidence ones.
            if extraction_result.extractions:
                self.memory.update_from_extractions(
                    extracted_slots=extraction_result.extractions,
                    source_utterance=asr_output.text,
                )

        # 2. State Machine Planner determines intent
        action = self.planner.plan_next_action(asr_output, state, extraction_result)

        # 3. Wording Layer translates intent to natural language
        target_lang = getattr(state, "preferred_language", None) or asr_output.language
        if not target_lang or target_lang == "unknown":
            target_lang = "hinglish"
        response_text = self.wording_llm.generate_wording(action, target_lang)

        # 4. Append AI response to history
        state.history.append(DialogueTurn(
            speaker="system",
            text=response_text,
            language=target_lang,
        ))

        return response_text
