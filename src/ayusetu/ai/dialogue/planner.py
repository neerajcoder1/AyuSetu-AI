from contracts.dialogue import DialogueState, PlannerAction, ClinicalSlot, DialogueTurn
from contracts.asr_output import ASROutput
from contracts.extraction import ExtractionResult
from ayusetu.ai.dialogue.ontology import INTERVIEW_SEQUENCE, SLOT_INTENTS

class DialoguePlanner:
    """
    Deterministic state machine for the clinical interview.
    COMPLETELY INDEPENDENT OF LLM.
    """
    def __init__(self, asr_confidence_threshold: float = 0.6, extraction_confidence_threshold: float = 0.7):
        self.asr_confidence_threshold = asr_confidence_threshold
        self.extraction_confidence_threshold = extraction_confidence_threshold
        
    def initialize_state(self) -> DialogueState:
        return DialogueState(
            collected_info={},
            missing_slots=INTERVIEW_SEQUENCE.copy(),
            history=[],
            needs_clarification=False,
            is_complete=False
        )

    def plan_next_action(self, asr_output: ASROutput, current_state: DialogueState, extraction_result: ExtractionResult) -> PlannerAction:
        """
        Updates the dialogue state and returns the next required planner action.
        """
        # 1. Update history with patient's turn
        current_state.history.append(DialogueTurn(
            speaker="patient", 
            text=asr_output.text, 
            language=asr_output.language, 
            confidence=asr_output.confidence
        ))

        # 2. Check ASR confidence (Rejection logic)
        # Low ASR confidence entirely bypasses extraction state updates
        if asr_output.confidence < self.asr_confidence_threshold:
            current_state.needs_clarification = True
            return PlannerAction(needs_clarification=True)
        else:
            current_state.needs_clarification = False

        # 3. Update state with newly extracted info
        for ext in extraction_result.extractions:
            # Check EXTRACTION confidence
            if ext.confidence >= self.extraction_confidence_threshold:
                if ext.slot in current_state.collected_info:
                    old_value = current_state.collected_info[ext.slot]
                    if old_value != ext.value:
                        # Correction: log the history, then update active value
                        from contracts.dialogue import SlotCorrection
                        current_state.corrections.append(
                            SlotCorrection(
                                slot=ext.slot,
                                previous_value=old_value,
                                updated_value=ext.value,
                                update_reason="patient_correction"
                            )
                        )
                        current_state.collected_info[ext.slot] = ext.value
                    # If old_value == ext.value, it's an identical repeat, so do nothing.
                else:
                    # First time extracting this slot
                    current_state.collected_info[ext.slot] = ext.value
                    if ext.slot in current_state.missing_slots:
                        current_state.missing_slots.remove(ext.slot)

        # 4. Determine next slot (Deterministic queue)
        if not current_state.missing_slots:
            current_state.is_complete = True
            return PlannerAction(is_complete=True)

        next_slot = current_state.missing_slots[0]
        intent = SLOT_INTENTS.get(next_slot, "Ask for this information.")
        
        return PlannerAction(
            next_slot=next_slot, 
            question_intent=intent,
            is_complete=False,
            needs_clarification=False
        )
