from contracts.dialogue import ClinicalSlot

# The deterministic sequence of the clinical interview
INTERVIEW_SEQUENCE = [
    ClinicalSlot.CHIEF_COMPLAINT,
    ClinicalSlot.ONSET,
    ClinicalSlot.DURATION,
    ClinicalSlot.LOCATION,
    ClinicalSlot.SEVERITY,
    ClinicalSlot.ASSOCIATED_SYMPTOMS,
    ClinicalSlot.AGGRAVATING_RELIEVING,
    ClinicalSlot.PAST_MEDICAL_HISTORY,
    ClinicalSlot.MEDICATIONS,
    ClinicalSlot.ALLERGIES,
    ClinicalSlot.FAMILY_HISTORY,
    ClinicalSlot.LIFESTYLE,
]

# Standardized intents for each slot
# The LLM uses these to determine WHAT to ask, strictly bound by the planner.
SLOT_INTENTS = {
    ClinicalSlot.CHIEF_COMPLAINT: "Ask the patient what their main problem or symptom is.",
    ClinicalSlot.ONSET: "Ask when the symptom first started.",
    ClinicalSlot.DURATION: "Ask how long the complaint has been present.",
    ClinicalSlot.LOCATION: "Ask where exactly the pain or symptom is located.",
    ClinicalSlot.SEVERITY: "Ask how severe the symptom is (e.g., on a scale of 1-10).",
    ClinicalSlot.ASSOCIATED_SYMPTOMS: "Ask if they have any other symptoms along with the main one.",
    ClinicalSlot.AGGRAVATING_RELIEVING: "Ask what makes the symptom better or worse.",
    ClinicalSlot.PAST_MEDICAL_HISTORY: "Ask if they have any previous medical conditions.",
    ClinicalSlot.MEDICATIONS: "Ask what medicines they are currently taking.",
    ClinicalSlot.ALLERGIES: "Ask if they have any allergies.",
    ClinicalSlot.FAMILY_HISTORY: "Ask if anyone in their family has similar problems or major diseases.",
    ClinicalSlot.LIFESTYLE: "Ask about their lifestyle, diet, or sleep patterns (Ahara-Vihara).",
}
