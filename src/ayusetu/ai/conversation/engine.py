from typing import Optional
from contracts.asr_output import ASROutput
from contracts.extraction import ExtractionResult, ExtractedSlot
from contracts.dialogue import DialogueState, DialogueTurn, ClinicalSlot
from ayusetu.ai.conversation.planner import DialoguePlanner
from ayusetu.ai.conversation.extractor import ClinicalExtractor, DeterministicRuleExtractor
from ayusetu.ai.conversation.wording import WordingLLM
from ayusetu.ai.conversation.llm_provider import OpenAICompatibleProvider
from ayusetu.ai.clinical.memory import ClinicalMemory
from ayusetu.ai.clinical.hindsight import HindsightMemoryManager
import logging

logger = logging.getLogger(__name__)


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

    Optional Long-Term Hindsight Memory
    -----------------------------------
    If ``hindsight_manager`` is supplied, historical patient encounters are
    queried in background and passed to ``wording_llm`` for context.
    ``ClinicalMemory`` remains completely untouched by Hindsight context.
    """

    def __init__(self,
                extractor: Optional[ClinicalExtractor] = None,
                llm_provider=None,
                asr_confidence_threshold: float = 0.6,
                extraction_confidence_threshold: float = 0.7,
                memory: Optional[ClinicalMemory] = None,
                hindsight_manager: Optional[HindsightMemoryManager] = None):
        # Primary extractor (could be LLM‑based). Default to deterministic rule extractor.
        self.extractor = extractor or DeterministicRuleExtractor()
        # Deterministic fallback extractor – always rule‑based.
        self.fallback_extractor = DeterministicRuleExtractor()
        provider = llm_provider or OpenAICompatibleProvider()
        self.wording_llm = WordingLLM(provider)

        self.planner = DialoguePlanner(
            asr_confidence_threshold=asr_confidence_threshold,
            extraction_confidence_threshold=extraction_confidence_threshold
        )

        # Each engine instance gets its own ClinicalMemory.
        # Passing an explicit instance is supported for testing.
        self.memory: ClinicalMemory = memory if memory is not None else ClinicalMemory()
        self.hindsight_manager = hindsight_manager

    def initialize(self, body_map_location: Optional[str] = None) -> DialogueState:
        """Returns a fresh dialogue state."""
        state = self.planner.initialize_state()
        if body_map_location:
            state.body_map_location = body_map_location
        return state

    def generate_opening(self, state: DialogueState) -> str:
        """
        Generate the first greeting, optionally using the body map context.
        """
        if state.body_map_location:
            loc = state.body_map_location.lower()
            if "head" in loc or "sir" in loc or "सिर" in loc:
                response = "आपके सिर में तकलीफ़ है। कृपया बताइए, यह समस्या कब से है?"
            elif "chest" in loc or "seene" in loc or "सीने" in loc:
                response = "आपके सीने में तकलीफ़ है। कृपया बताइए, यह समस्या कब से है?"
            elif "back" in loc or "peeth" in loc or "पीठ" in loc or "kamar" in loc or "कमर" in loc:
                response = "आपकी पीठ में तकलीफ़ है। कृपया बताइए, यह समस्या कब से है?"
            elif "abdomen" in loc or "stomach" in loc or "pet" in loc or "पेट" in loc:
                response = "आपके पेट में तकलीफ़ है। कृपया बताइए, यह समस्या कब से है?"
            else:
                # Default generic opening for body part
                response = f"आपको {state.body_map_location} में तकलीफ़ है। कृपया बताइए, यह समस्या कब से है?"
        else:
            response = "नमस्ते। कृपया बताइए, आपकी मुख्य समस्या क्या है?"

        state.history.append(DialogueTurn(
            speaker="system",
            text=response,
            language="hi"
        ))
        return response

    def step(self, asr_output: ASROutput, state: DialogueState, patient_id: Optional[str] = None) -> str:
        """
        Process a single turn of the dialogue.
        Updates state in place and returns the worded question from the AI.
        """
        # 1. Extract info (only if ASR confidence is sufficient)
        extraction_result = ExtractionResult(extractions=[])
        logger.debug(f"ASR Output: text='{asr_output.text}', confidence={asr_output.confidence}, passed_threshold={asr_output.confidence >= self.planner.asr_confidence_threshold}")
        if asr_output.confidence >= self.planner.asr_confidence_threshold:
            current_target_slot = state.missing_slots[0] if state and state.missing_slots else None
            # Primary extraction attempt
            try:
                primary_result = self.extractor.extract(asr_output.text, target_slot=current_target_slot)
            except TypeError:
                primary_result = self.extractor.extract(asr_output.text)
            except Exception:
                primary_result = ExtractionResult(extractions=[])

            logger.debug(f"Target slot: {current_target_slot}, Primary extractions: {[(e.slot.name, e.confidence) for e in primary_result.extractions]}")

            # Determine if primary extraction for the target slot is high confidence
            high_confidence = False
            if current_target_slot:
                for ext in primary_result.extractions:
                    if ext.slot == current_target_slot and ext.confidence >= self.planner.extraction_confidence_threshold:
                        high_confidence = True
                        break

            logger.debug(f"Primary high confidence for target: {high_confidence}")

            if high_confidence:
                extraction_result = primary_result
            else:
                # Fallback deterministic extraction
                try:
                    fallback_result = self.fallback_extractor.extract(asr_output.text, target_slot=current_target_slot)
                except TypeError:
                    fallback_result = self.fallback_extractor.extract(asr_output.text)
                except Exception:
                    fallback_result = ExtractionResult(extractions=[])

                logger.info(f"Fallback extractions: {[(e.slot.name, e.confidence) for e in fallback_result.extractions]}")

                # Merge according to rules: keep primary slots except low‑conf target, add fallback slots
                merged_extractions = []
                for ext in primary_result.extractions:
                    if not (current_target_slot and ext.slot == current_target_slot):
                        merged_extractions.append(ext)
                merged_extractions.extend(fallback_result.extractions)
                extraction_result = ExtractionResult(extractions=merged_extractions)
                logger.debug(f"Merged extractions: {[(e.slot.name, e.confidence) for e in extraction_result.extractions]}")

            # Body Map + Patient Voice Merging
            # If body map was selected, inject it as LOCATION if not explicitly extracted
            if state.body_map_location:
                has_location = any(e.slot == ClinicalSlot.LOCATION for e in extraction_result.extractions)
                if not has_location:
                    # check if chief complaint or other core slot was extracted
                    has_core = any(e.slot in [ClinicalSlot.CHIEF_COMPLAINT, ClinicalSlot.DURATION, ClinicalSlot.SEVERITY, ClinicalSlot.ONSET] for e in extraction_result.extractions)
                    if has_core:
                        extraction_result.extractions.append(ExtractedSlot(
                            slot=ClinicalSlot.LOCATION,
                            value=state.body_map_location,
                            confidence=0.8,
                            evidence="body_map"
                        ))

            # 1b. Update session‑scoped clinical memory with extractions.
            if extraction_result.extractions:
                self.memory.update_from_extractions(
                    extracted_slots=extraction_result.extractions,
                    source_utterance=asr_output.text,
                )

        # 2. State Machine Planner determines intent
        action = self.planner.plan_next_action(asr_output, state, extraction_result)
        logger.debug(f"Planner Action: next_slot={action.next_slot.name if action.next_slot else None}, is_complete={action.is_complete}, needs_clarification={action.needs_clarification}")

        # 3. Optional Hindsight memory retrieval (background context for wording)
        historical_context = None
        eff_patient_id = patient_id or getattr(state, "patient_id", None)
        if self.hindsight_manager and eff_patient_id:
            historical_context = self.hindsight_manager.retrieve_historical_context(
                patient_id=eff_patient_id,
                current_query=asr_output.text
            )

        # 4. Wording Layer translates intent to natural language
        target_lang = getattr(state, "preferred_language", None) or asr_output.language
        if not target_lang or target_lang == "unknown":
            target_lang = "hinglish"
        response_text = self.wording_llm.generate_wording(
            action=action,
            language=target_lang,
            historical_context=historical_context
        )

        if not response_text or not response_text.strip():
            logger.warning("Empty response received from WordingLLM. Using fallback response.")
            if action.needs_clarification and action.question_intent and not action.next_slot:
                response_text = action.question_intent
            elif action.next_slot:
                from ayusetu.ai.conversation.ontology import FALLBACK_QUESTIONS
                response_text = FALLBACK_QUESTIONS.get(action.next_slot, "कृपया थोड़ा और बताइए।")
                if action.needs_clarification and action.question_intent:
                    response_text = action.question_intent
            else:
                response_text = "क्या आप कृपया अपनी बात दोहरा सकते हैं?"

        # 5. Append AI response to history
        state.history.append(DialogueTurn(
            speaker="system",
            text=response_text,
            language=target_lang,
        ))

        return response_text

