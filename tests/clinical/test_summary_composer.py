from contracts.dialogue import ClinicalSlot
from ayusetu.ai.clinical.red_flags.contracts import RedFlagEvent, Tier
from ayusetu.ai.clinical.summary.composer import SummaryGenerator
from ayusetu.ai.clinical.summary.contracts import SummaryStatus


def _red_flag_event():
    return RedFlagEvent(
        encounter_id="enc-1",
        rule_id="RF-CARD-01",
        tier=Tier.TIER_1,
        category="cardiac",
        title="Possible acute coronary syndrome",
        trigger_text="chest pain",
        detection_layer="rule",
    )


def test_generate_produces_preliminary_summary():
    generator = SummaryGenerator()
    collected_info = {
        ClinicalSlot.CHIEF_COMPLAINT: "chest pain",
        ClinicalSlot.DURATION: "2 days",
    }
    missing_slots = [ClinicalSlot.ALLERGIES]

    summary = generator.generate("enc-1", collected_info, missing_slots)

    assert summary.status == SummaryStatus.PRELIMINARY
    assert summary.chief_complaint == "chest pain"
    assert any("2 days" in c.text for c in summary.hpi_narrative)


def test_missing_slot_shows_as_not_elicited_in_structured_history():
    generator = SummaryGenerator()
    collected_info = {ClinicalSlot.CHIEF_COMPLAINT: "fever"}
    missing_slots = [ClinicalSlot.ALLERGIES]

    summary = generator.generate("enc-1", collected_info, missing_slots)

    assert summary.structured_history["allergies"].elicited is False
    assert summary.structured_history["allergies"].display_value == "not elicited"


def test_red_flag_events_become_alerts():
    generator = SummaryGenerator()
    summary = generator.generate(
        "enc-1", {ClinicalSlot.CHIEF_COMPLAINT: "chest pain"}, [], red_flag_events=[_red_flag_event()]
    )
    assert len(summary.alerts) == 1
    assert summary.alerts[0].tier == 1
    assert summary.alerts[0].title == "Possible acute coronary syndrome"


def test_suggested_coding_only_for_resolvable_terms():
    generator = SummaryGenerator()
    summary = generator.generate("enc-1", {ClinicalSlot.CHIEF_COMPLAINT: "some unresolvable phrase"}, [])
    assert summary.suggested_coding == []


def test_suggested_coding_present_for_known_vocabulary_term():
    generator = SummaryGenerator()
    summary = generator.generate("enc-1", {ClinicalSlot.CHIEF_COMPLAINT: "hypertension"}, [])
    assert len(summary.suggested_coding) == 1
    assert summary.suggested_coding[0].system == "ICD-11"
