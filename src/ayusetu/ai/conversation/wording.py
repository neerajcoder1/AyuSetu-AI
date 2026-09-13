from typing import Optional
from ayusetu.ai.conversation.llm_provider import LLMProvider
from contracts.dialogue import PlannerAction

class WordingLLM:
    """
    The Wording Layer.
    Only responsible for converting a planned question intent into natural, patient-friendly phrasing.
    """
    def __init__(self, provider: LLMProvider):
        self.provider = provider
        
    def generate_wording(self, action: PlannerAction, language: str, historical_context: Optional[str] = None) -> str:
        if action.is_complete:
            intent = "Thank the patient and politely conclude the interview."
            slot_name = "N/A"
        elif action.needs_clarification:
            intent = "Politely ask the patient to repeat or clarify because you could not understand them clearly."
            slot_name = "N/A"
        else:
            intent = action.question_intent
            slot_name = action.next_slot.value if action.next_slot else "N/A"
        
        sys_prompt = (
            "You are the clinical wording layer of AyuSetu AI.\n"
            "Your ONLY job is to convert the given question intent into natural, "
            "empathetic, and patient-friendly phrasing in the requested language.\n\n"
            "RULES:\n"
            "1. DO NOT ask anything outside the intent.\n"
            "2. DO NOT provide medical advice or diagnosis.\n"
            "3. DO NOT output JSON or extra conversational filler, just the exact question.\n"
            "4. Match the tone of a professional, caring doctor.\n"
            "5. Historical context is for background context only; do NOT overwrite or invent current clinical findings.\n"
        )
        
        user_prompt = (
            f"Slot: {slot_name}\n"
            f"Question Intent: {intent}\n"
            f"Requested Language: {language}\n"
        )
        if historical_context:
            user_prompt += f"Patient History Context (Background Reference Only):\n{historical_context}\n"
        user_prompt += "Output the question wording directly:"
        
        return self.provider.generate(sys_prompt, user_prompt)

