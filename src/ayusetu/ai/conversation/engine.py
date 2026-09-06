from typing import Optional
from contracts.asr_output import ASROutput
from contracts.extraction import ExtractionResult
from contracts.dialogue import DialogueState, DialogueTurn
from ayusetu.ai.conversation.planner import DialoguePlanner
from ayusetu.ai.conversation.extractor import ClinicalExtractor, DeterministicPlaceholderExtractor
from ayusetu.ai.conversation.wording import WordingLLM
from ayusetu.ai.conversation.llm_provider import OpenAICompatibleProvider

class DialogueEngine:
    """
    Main orchestrator for Phase 2.
    Connects: ASR Output -> Extractor -> Planner -> Wording LLM
    """
    def __init__(self, 
                 extractor: Optional[ClinicalExtractor] = None, 
                 llm_provider=None, 
                 asr_confidence_threshold: float = 0.6,
                 extraction_confidence_threshold: float = 0.7):
                 
        self.extractor = extractor or DeterministicPlaceholderExtractor()
        
        provider = llm_provider or OpenAICompatibleProvider()
        self.wording_llm = WordingLLM(provider)
        
        self.planner = DialoguePlanner(
            asr_confidence_threshold=asr_confidence_threshold,
            extraction_confidence_threshold=extraction_confidence_threshold
        )
        
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
            
        # 2. State Machine Planner determines intent
        action = self.planner.plan_next_action(asr_output, state, extraction_result)
        
        # 3. Wording Layer translates intent to natural language
        target_lang = asr_output.language if asr_output.language != "unknown" else "hinglish"
        response_text = self.wording_llm.generate_wording(action, target_lang)
        
        # 4. Append AI response to history
        state.history.append(DialogueTurn(
            speaker="system",
            text=response_text,
            language=target_lang,
        ))
        
        return response_text
