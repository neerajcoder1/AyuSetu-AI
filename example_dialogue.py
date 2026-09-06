from contracts.asr_output import ASROutput
from neeraj.dialogue.engine import DialogueEngine
from neeraj.dialogue.llm_provider import OpenAICompatibleProvider

# Using the real provider but with a dummy key for a safe trace without hitting an API
# We can inject a system env variable if we want real calls, but the mock is fine to demonstrate data flow
class DummyFlowProvider(OpenAICompatibleProvider):
    def generate(self, sys, user):
        return f"[Wording LLM output based on: {user.splitlines()[1]}]"

def run_example():
    engine = DialogueEngine(llm_provider=DummyFlowProvider())
    state = engine.initialize()
    
    print("=== START OF INTERVIEW ===")
    print(f"Next Planner Goal: {state.missing_slots[0].value}\n")
    
    # Turn 1
    print("🗣️ Patient: 'मुझे दो दिन से पेट में दर्द है' (hi, conf: 0.95)")
    asr1 = ASROutput(text="मुझे दो दिन से पेट में दर्द है", language="hi", confidence=0.95)
    response1 = engine.step(asr1, state)
    print(f"🤖 AI: {response1}")
    print(f"   [State Update] Extracted: {state.collected_info}")
    print(f"   [Planner Update] Next required slot: {state.missing_slots[0].value}\n")
    
    # Turn 2: Low confidence simulate
    print("🗣️ Patient: '*mumbles*' (hi, conf: 0.40)")
    asr2 = ASROutput(text="...mumble...", language="hi", confidence=0.40)
    response2 = engine.step(asr2, state)
    print(f"🤖 AI: {response2}")
    print(f"   [State Update] Needs Clarification: {state.needs_clarification}")
    print(f"   [Planner Update] Next required slot: {state.missing_slots[0].value}\n")

if __name__ == "__main__":
    run_example()
