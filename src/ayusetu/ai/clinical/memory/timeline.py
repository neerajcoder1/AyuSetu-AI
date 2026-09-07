"""
Longitudinal patient timeline building.

Folds a sequence of per-encounter snapshots (dialogue-collected slots +
Document AI entities + red-flag titles) into one chronologically sorted
list of TimelineEvent, each still traceable to its originating utterance or
document region. This is the data behind the "Prior records — Timeline
widget" section of the summary (PRD §13.2).
"""

from typing import List, Optional

from ayusetu.ai.clinical.memory.contracts import (
    EncounterSnapshot,
    SourceKind,
    TimelineEvent,
    TimelineEventType,
)

# Maps a ClinicalSlot (by its .value string) collected during dialogue to the
# timeline event type it represents. Slots not listed here still show up
# generically as SYMPTOM-typed events rather than being dropped.
_SLOT_TO_EVENT_TYPE = {
    "chief_complaint": TimelineEventType.CHIEF_COMPLAINT,
    "medications": TimelineEventType.MEDICATION,
    "allergies": TimelineEventType.ALLERGY,
}

_DOCUMENT_ENTITY_TO_EVENT_TYPE = {
    "diagnosis": TimelineEventType.DIAGNOSIS,
    "medication": TimelineEventType.MEDICATION,
    "lab_result": TimelineEventType.LAB_RESULT,
    "allergy": TimelineEventType.ALLERGY,
    "vital_sign": TimelineEventType.VITAL_SIGN,
}


def build_timeline_from_encounter(snapshot: EncounterSnapshot) -> List[TimelineEvent]:
    events: List[TimelineEvent] = [
        TimelineEvent(
            encounter_id=snapshot.encounter_id,
            date=snapshot.date,
            event_type=TimelineEventType.ENCOUNTER,
            title="Encounter",
            detail=f"Encounter {snapshot.encounter_id}",
            source=SourceKind.DERIVED,
            confidence=1.0,
        )
    ]

    for slot, value in snapshot.collected_info.items():
        slot_name = slot.value if hasattr(slot, "value") else str(slot)
        event_type = _SLOT_TO_EVENT_TYPE.get(slot_name, TimelineEventType.SYMPTOM)
        events.append(
            TimelineEvent(
                encounter_id=snapshot.encounter_id,
                date=snapshot.date,
                event_type=event_type,
                title=slot_name.replace("_", " ").title(),
                detail=str(value),
                source=SourceKind.UTTERANCE,
                source_ref=slot_name,
                confidence=1.0,
            )
        )

    for slot in snapshot.missing_slots:
        slot_name = slot.value if hasattr(slot, "value") else str(slot)
        events.append(
            TimelineEvent(
                encounter_id=snapshot.encounter_id,
                date=snapshot.date,
                event_type=_SLOT_TO_EVENT_TYPE.get(slot_name, TimelineEventType.SYMPTOM),
                title=slot_name.replace("_", " ").title(),
                detail="not elicited",
                source=SourceKind.DERIVED,
                source_ref=slot_name,
                confidence=1.0,
                elicited=False,
            )
        )

    for entity in snapshot.document_entities:
        entity_type = entity.entity_type.value if hasattr(entity.entity_type, "value") else str(entity.entity_type)
        event_type = _DOCUMENT_ENTITY_TO_EVENT_TYPE.get(entity_type, TimelineEventType.SYMPTOM)
        events.append(
            TimelineEvent(
                encounter_id=snapshot.encounter_id,
                date=entity.doc_date or snapshot.date,
                event_type=event_type,
                title=entity_type.replace("_", " ").title(),
                detail=entity.raw_text,
                source=SourceKind.DOCUMENT,
                source_ref=f"page:{entity.page_no}",
                confidence=entity.confidence,
            )
        )

    for title in snapshot.red_flag_titles:
        events.append(
            TimelineEvent(
                encounter_id=snapshot.encounter_id,
                date=snapshot.date,
                event_type=TimelineEventType.RED_FLAG,
                title="Red flag",
                detail=title,
                source=SourceKind.DERIVED,
                confidence=1.0,
            )
        )

    return events


def build_patient_timeline(snapshots: List[EncounterSnapshot]) -> List[TimelineEvent]:
    """
    Merge every encounter's events into one chronological timeline.
    Events with no date sort last (undated documents/history still need to
    show up somewhere, just not interleaved incorrectly with dated ones).
    """
    all_events: List[TimelineEvent] = []
    for snapshot in snapshots:
        all_events.extend(build_timeline_from_encounter(snapshot))

    return sorted(all_events, key=lambda e: (e.date is None, e.date))


def filter_timeline(
    events: List[TimelineEvent],
    event_type: Optional[TimelineEventType] = None,
    encounter_id: Optional[str] = None,
) -> List[TimelineEvent]:
    result = events
    if event_type is not None:
        result = [e for e in result if e.event_type == event_type]
    if encounter_id is not None:
        result = [e for e in result if e.encounter_id == encounter_id]
    return result
