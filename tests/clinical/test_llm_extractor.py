import json
from contracts.dialogue import ClinicalSlot
from ayusetu.ai.clinical.extraction.llm_extractor import LLMClinicalExtractor


class _FakeProvider:
    """Deterministic stand-in for LLMProvider, no network calls."""

    def __init__(self, response: str):
        self.response = response
        self.last_call = None

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.last_call = (system_prompt, user_prompt)
        return self.response


def test_valid_response_is_parsed_into_contract():
    payload = {
        "extractions": [
            {
                "slot": "chief_complaint",
                "value": "headache",
                "confidence": 0.9,
                "evidence": "headache",
            }
        ]
    }
    provider = _FakeProvider(json.dumps(payload))
    extractor = LLMClinicalExtractor(provider=provider)

    result = extractor.extract("I have a headache")

    assert len(result.extractions) == 1
    assert result.extractions[0].slot == ClinicalSlot.CHIEF_COMPLAINT
    assert result.extractions[0].value == "headache"


def test_response_wrapped_in_markdown_fence_is_parsed():
    payload = {"extractions": [{"slot": "duration", "value": "2 days", "confidence": 0.8, "evidence": "2 days"}]}
    provider = _FakeProvider("```json\n" + json.dumps(payload) + "\n```")
    extractor = LLMClinicalExtractor(provider=provider)

    result = extractor.extract("headache for 2 days")
    assert result.extractions[0].value == "2 days"


def test_unparseable_response_returns_empty_result_not_error():
    provider = _FakeProvider("I'm not sure, let me think about this...")
    extractor = LLMClinicalExtractor(provider=provider)
    result = extractor.extract("some text")
    assert result.extractions == []


def test_invalid_slot_name_is_dropped():
    payload = {"extractions": [{"slot": "not_a_real_slot", "value": "x", "confidence": 0.9, "evidence": "x"}]}
    provider = _FakeProvider(json.dumps(payload))
    extractor = LLMClinicalExtractor(provider=provider)
    result = extractor.extract("x")
    assert result.extractions == []


def test_hallucinated_evidence_not_in_source_is_penalised():
    payload = {
        "extractions": [
            {
                "slot": "chief_complaint",
                "value": "chest pain",
                "confidence": 0.95,
                "evidence": "chest pain",
            }
        ]
    }
    provider = _FakeProvider(json.dumps(payload))
    extractor = LLMClinicalExtractor(provider=provider)

    # Source text does NOT contain "chest pain" -> evidence claim is false.
    result = extractor.extract("I have a stomach ache")

    assert result.extractions[0].confidence <= 0.5


def test_out_of_range_confidence_is_clamped():
    payload = {
        "extractions": [
            {"slot": "chief_complaint", "value": "headache", "confidence": 1.7, "evidence": "headache"}
        ]
    }
    provider = _FakeProvider(json.dumps(payload))
    extractor = LLMClinicalExtractor(provider=provider)
    result = extractor.extract("headache")
    assert result.extractions[0].confidence <= 1.0


def test_empty_text_short_circuits_without_calling_provider():
    provider = _FakeProvider("{}")
    extractor = LLMClinicalExtractor(provider=provider)
    result = extractor.extract("")
    assert result.extractions == []
    assert provider.last_call is None
