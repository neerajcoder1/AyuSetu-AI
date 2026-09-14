from contracts.dialogue import ClinicalSlot

# The deterministic sequence of the clinical interview
INTERVIEW_SEQUENCE = [
    ClinicalSlot.CHIEF_COMPLAINT,
    ClinicalSlot.LOCATION,
    ClinicalSlot.ONSET,
    ClinicalSlot.DURATION,
    ClinicalSlot.SEVERITY,
    ClinicalSlot.ASSOCIATED_SYMPTOMS,
    ClinicalSlot.PAST_MEDICAL_HISTORY,
    ClinicalSlot.MEDICATIONS,
    ClinicalSlot.ALLERGIES,
    ClinicalSlot.AGGRAVATING_RELIEVING,
    ClinicalSlot.LIFESTYLE,
    ClinicalSlot.FAMILY_HISTORY,
]

# Standardized intents for each slot
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

FALLBACK_QUESTIONS = {
    ClinicalSlot.CHIEF_COMPLAINT: "आपको क्या समस्या हो रही है?",
    ClinicalSlot.ONSET: "यह समस्या कब शुरू हुई?",
    ClinicalSlot.DURATION: "यह समस्या कितने समय से है?",
    ClinicalSlot.LOCATION: "तकलीफ़ शरीर के किस हिस्से में है?",
    ClinicalSlot.SEVERITY: "यह समस्या कितनी गंभीर है?",
    ClinicalSlot.ASSOCIATED_SYMPTOMS: "क्या इसके साथ कोई और लक्षण हैं?",
    ClinicalSlot.AGGRAVATING_RELIEVING: "क्या किसी चीज़ से यह समस्या बढ़ती या कम होती है?",
    ClinicalSlot.PAST_MEDICAL_HISTORY: "क्या आपको पहले से कोई बीमारी है?",
    ClinicalSlot.MEDICATIONS: "क्या आप कोई दवा ले रहे हैं?",
    ClinicalSlot.ALLERGIES: "क्या आपको किसी चीज़ से एलर्जी है?",
    ClinicalSlot.FAMILY_HISTORY: "क्या आपके परिवार में किसी को ऐसी बीमारी है?",
    ClinicalSlot.LIFESTYLE: "आपकी जीवनशैली या खान-पान कैसा है?",
}
