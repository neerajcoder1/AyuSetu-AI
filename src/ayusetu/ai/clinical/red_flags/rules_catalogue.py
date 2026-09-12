"""
Tier 1 rule catalogue (PRD §12.2), expressed as versioned data.

This module is the STARTER/DEMO equivalent of `packages/clinical-content`
(§22.7) — in a real deployment these rules live outside the codebase,
versioned and approved by the Clinical Advisory Board, loaded at runtime so
"adding a red flag must never require a code deployment" (§16.3). Keeping
them as a plain Python list of dicts here (rather than e.g. an ORM model)
means promoting them to a JSON/YAML file behind a content API later is a
loader change, not a rule-authoring change.

Detection prefers `contains` over the PRD example's `in` operator for slot
matching: our current ClinicalSlot values are short free-text strings
("in my chest", not an enumerated "chest"), so substring containment is the
robust match; `in` remains available in the DSL for callers with a
constrained value set. Every rule also matches against the full utterance
text (`slot: "utterance"`) since several PRD triggers ("facial droop",
"rigid abdomen") are finer-grained than anything our current dialogue slots
capture — RedFlagEngine unions this with the classifier layer, which is
where paraphrases the catalogue's exact wording misses get caught.
"""

from typing import Any, Dict, List

_APPROVED_BY = "CAB-2026-03"
_APPROVED_AT = "2026-03-14"


def _keyword_rule(rule_id: str, category: str, title: str, keywords: List[str], version: int = 1) -> Dict[str, Any]:
    return {
        "id": rule_id,
        "tier": 1,
        "version": version,
        "title": title,
        "category": category,
        "when": {"any": [{"slot": "utterance", "contains": kw} for kw in keywords]},
        "action": {
            "escalate": "triage_desk",
            "queue_priority": "immediate",
            "patient_message_key": "calm_wait",
        },
        "approved_by": _APPROVED_BY,
        "approved_at": _APPROVED_AT,
    }


TIER1_RULES_RAW: List[Dict[str, Any]] = [
    {
        "id": "RF-CARD-01",
        "tier": 1,
        "version": 3,
        "title": "Possible acute coronary syndrome",
        "category": "cardiac",
        "when": {
            "any": [
                {
                    "all": [
                        {"slot": "location", "contains": "chest"},
                        {
                            "any": [
                                {"slot": "associated_symptoms", "contains": "dyspnoea"},
                                {"slot": "associated_symptoms", "contains": "breathless"},
                                {"slot": "associated_symptoms", "contains": "sweating"},
                                {"slot": "associated_symptoms", "contains": "radiation"},
                            ]
                        },
                    ]
                },
                {"slot": "utterance", "contains": "chest pain"},
                {"slot": "utterance", "contains": "chest pressure"},
            ]
        },
        "action": {"escalate": "triage_desk", "queue_priority": "immediate", "patient_message_key": "calm_wait"},
        "approved_by": _APPROVED_BY,
        "approved_at": _APPROVED_AT,
    },
    _keyword_rule(
        "RF-NEURO-01",
        "neurological",
        "Possible acute stroke / neurological emergency",
        [
            "sudden weakness",
            "one side",
            "facial droop",
            "face drooping",
            "slurred speech",
            "can't speak",
            "worst headache",
            "worst-ever headache",
            "new seizure",
            "convulsion",
        ],
    ),
    _keyword_rule(
        "RF-RESP-01",
        "respiratory",
        "Severe respiratory distress",
        [
            "breathless at rest",
            "can't breathe",
            "cannot breathe",
            "can't complete a sentence",
            "cannot finish a sentence",
            "turning blue",
            "cyanosis",
        ],
    ),
    _keyword_rule(
        "RF-BLEED-01",
        "bleeding",
        "Uncontrolled or severe bleeding",
        [
            "vomiting blood",
            "haematemesis",
            "hematemesis",
            "black stool",
            "melaena",
            "melena",
            "heavy vaginal bleeding",
            "uncontrolled bleeding",
            "bleeding a lot",
        ],
    ),
    _keyword_rule(
        "RF-OBS-01",
        "obstetric",
        "Obstetric emergency",
        [
            "pregnant",
            "pregnancy",
        ],
    ),
    _keyword_rule(
        "RF-SEPSIS-01",
        "sepsis",
        "Possible sepsis",
        [
            "high fever",
            "confusion",
            "not urinating",
            "no urine",
            "rigors",
            "shaking chills",
        ],
    ),
    _keyword_rule(
        "RF-ABD-01",
        "abdominal",
        "Acute abdomen",
        [
            "severe abdominal pain",
            "sudden abdominal pain",
            "rigid abdomen",
            "hard stomach",
            "no bowel movement",
            "vomiting and no motion",
        ],
    ),
    _keyword_rule(
        "RF-PAED-01",
        "paediatric",
        "Paediatric emergency",
        [
            "refusing feeds",
            "not feeding",
            "baby is lethargic",
            "infant seizure",
            "fast breathing",
            "breathing very fast",
        ],
    ),
    _keyword_rule(
        "RF-PSYCH-01",
        "psychiatric",
        "Self-harm disclosure",
        [
            "kill myself",
            "end my life",
            "suicide",
            "want to die",
            "self harm",
            "self-harm",
            "hurt myself",
            "not worth living",
        ],
    ),
    _keyword_rule(
        "RF-METAB-01",
        "metabolic",
        "Metabolic emergency in a known diabetic",
        [
            "drowsy",
            "confused",
            "very high sugar",
            "very low sugar",
            "blood sugar 400",
            "blood sugar 40",
        ],
    ),
    _keyword_rule(
        "RF-TRAUMA-01",
        "trauma",
        "Head injury with warning signs",
        [
            "hit my head",
            "head injury",
            "fell and hit head",
            "lost consciousness",
            "blacked out",
        ],
    ),
]
