from datetime import date

from contracts.dialogue import ClinicalSlot
from ayusetu.ai.clinical.document_ai.contracts import EntityType, ExtractedEntity
from ayusetu.ai.clinical.memory.contracts import EncounterSnapshot, TimelineEventType
from ayusetu.ai.clinical.memory.timeline import (
    build_patient_timeline,
    build_timeline_from_encounter,
    filter_timeline,
)


def _document_entity(entity_type=EntityType.LAB_RESULT, doc_date=None):
    return ExtractedEntity(
        entity_type=entity_type,
        raw_text="Hemoglobin: 9.5 g/dL",
        normalised={"analyte": "hemoglobin", "value": 9.5},
        confidence=0.9,
        page_no=1,
        doc_date=doc_date,
    )


def test_encounter_snapshot_produces_encounter_event():
    snapshot = EncounterSnapshot(encounter_id="enc-1", date=date(2026, 1, 1))
    events = build_timeline_from_encounter(snapshot)
    assert any(e.event_type == TimelineEventType.ENCOUNTER for e in events)


def test_collected_slot_becomes_timeline_event_with_provenance():
    snapshot = EncounterSnapshot(
        encounter_id="enc-1",
        date=date(2026, 1, 1),
        collected_info={ClinicalSlot.CHIEF_COMPLAINT: "chest pain"},
    )
    events = build_timeline_from_encounter(snapshot)
    cc_events = [e for e in events if e.event_type == TimelineEventType.CHIEF_COMPLAINT]
    assert len(cc_events) == 1
    assert cc_events[0].detail == "chest pain"
    assert cc_events[0].source_ref == "chief_complaint"


def test_missing_slot_recorded_as_not_elicited_never_a_negative():
    snapshot = EncounterSnapshot(
        encounter_id="enc-1",
        date=date(2026, 1, 1),
        missing_slots=[ClinicalSlot.ALLERGIES],
    )
    events = build_timeline_from_encounter(snapshot)
    allergy_events = [e for e in events if e.event_type == TimelineEventType.ALLERGY]
    assert len(allergy_events) == 1
    assert allergy_events[0].elicited is False
    assert allergy_events[0].detail == "not elicited"


def test_document_entity_becomes_timeline_event():
    snapshot = EncounterSnapshot(
        encounter_id="enc-1",
        date=date(2026, 1, 1),
        document_entities=[_document_entity()],
    )
    events = build_timeline_from_encounter(snapshot)
    lab_events = [e for e in events if e.event_type == TimelineEventType.LAB_RESULT]
    assert len(lab_events) == 1
    assert lab_events[0].source.value == "document"


def test_red_flag_recorded_on_timeline():
    snapshot = EncounterSnapshot(encounter_id="enc-1", date=date(2026, 1, 1), red_flag_titles=["Possible ACS"])
    events = build_timeline_from_encounter(snapshot)
    assert any(e.event_type == TimelineEventType.RED_FLAG and e.detail == "Possible ACS" for e in events)


def test_patient_timeline_merges_and_sorts_multiple_encounters():
    older = EncounterSnapshot(encounter_id="enc-1", date=date(2025, 1, 1))
    newer = EncounterSnapshot(encounter_id="enc-2", date=date(2026, 1, 1))

    timeline = build_patient_timeline([newer, older])
    encounter_events = filter_timeline(timeline, event_type=TimelineEventType.ENCOUNTER)
    assert [e.encounter_id for e in encounter_events] == ["enc-1", "enc-2"]


def test_undated_events_sort_last():
    dated = EncounterSnapshot(encounter_id="enc-1", date=date(2025, 1, 1))
    undated = EncounterSnapshot(encounter_id="enc-2", date=None)

    timeline = build_patient_timeline([dated, undated])
    encounter_events = filter_timeline(timeline, event_type=TimelineEventType.ENCOUNTER)
    assert encounter_events[-1].encounter_id == "enc-2"


def test_filter_timeline_by_encounter():
    snapshot1 = EncounterSnapshot(encounter_id="enc-1", date=date(2025, 1, 1))
    snapshot2 = EncounterSnapshot(encounter_id="enc-2", date=date(2026, 1, 1))
    timeline = build_patient_timeline([snapshot1, snapshot2])
    filtered = filter_timeline(timeline, encounter_id="enc-1")
    assert all(e.encounter_id == "enc-1" for e in filtered)
