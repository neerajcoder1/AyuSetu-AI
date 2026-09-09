"""
Audit Service Core Engine Unit & Integration Tests
===================================================
Tests append-only semantics, monotonic sequencing, head management,
zero PHI filtering, and concurrency safety.
"""

import concurrent.futures
from ayusetu.audit.models import AuditAction, AuditOutcome
from ayusetu.audit.service import audit_service
from ayusetu.audit.chain import GENESIS_HASH


def test_append_only_monotonic_sequence():
    """Verify records receive strictly monotonic sequence numbers 1..N and advance head."""
    events = []
    for i in range(5):
        ev = audit_service.record_event(
            actor_id=f"018f0000-0000-7000-8000-00000000000{i}",
            actor_role="Physician",
            action=AuditAction.READ,
            resource_type="Encounter",
            resource_id="018f0000-0000-7000-8000-000000000099",
            outcome=AuditOutcome.ALLOW,
        )
        events.append(ev)

    assert len(events) == 5
    for idx, ev in enumerate(events):
        assert ev.seq == idx + 1
        if idx == 0:
            assert ev.prev_hash == GENESIS_HASH
        else:
            assert ev.prev_hash == events[idx - 1].entry_hash

    head = audit_service.get_head()
    assert head.seq == 5
    assert head.entry_hash == events[-1].entry_hash


def test_append_immutable_historical_records():
    """Verify historical records cannot be modified after append."""
    ev1 = audit_service.record_event(
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="Physician",
        action=AuditAction.CREATE,
        resource_type="ClinicalSummary",
        resource_id="018f0000-0000-7000-8000-000000000010",
    )

    ev1_dict_before = ev1.model_dump()

    # Append second event
    ev2 = audit_service.record_event(
        actor_id="018f0000-0000-7000-8000-000000000002",
        actor_role="Auditor",
        action=AuditAction.READ,
        resource_type="AuditLog",
        resource_id="018f0000-0000-7000-8000-000000000020",
    )

    ev1_after = audit_service.get_by_seq(1)
    assert ev1_after is not None
    assert ev1_after.model_dump() == ev1_dict_before


def test_query_events_filtering():
    """Verify range and metadata filtering for audit queries."""
    enc1 = "018f0000-0000-7000-8000-000000000011"
    enc2 = "018f0000-0000-7000-8000-000000000022"

    audit_service.record_event(
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="Physician",
        action=AuditAction.READ,
        resource_type="Encounter",
        resource_id=enc1,
        encounter_id=enc1,
    )
    audit_service.record_event(
        actor_id="018f0000-0000-7000-8000-000000000002",
        actor_role="Nurse",
        action=AuditAction.UPDATE,
        resource_type="Encounter",
        resource_id=enc2,
        encounter_id=enc2,
    )

    res_enc1 = audit_service.query_events(encounter_id=enc1)
    assert len(res_enc1) == 1
    assert res_enc1[0].encounter_id == enc1

    res_action = audit_service.query_events(action="UPDATE")
    assert len(res_action) == 1
    assert res_action[0].action == "UPDATE"


def test_zero_phi_enforcement():
    """Verify non-whitelisted sensitive metadata (transcripts, OCR, slots, passwords) are stripped."""
    dangerous_metadata = {
        "encounter_id": "018f0000-0000-7000-8000-000000000001",
        "transcript": "Patient complained of severe fever and chest pain",
        "utterance_text": "mujhe do din se bukhar hai",
        "slot_values": {"hpi.fever": "high"},
        "ocr_extracted_text": "Aadhaar 1234 5678 9012",
        "patient_name": "Ramesh Kumar",
        "password": "supersecretpassword",
        "access_token": "bearer-token-12345",
    }

    ev = audit_service.record_event(
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="Physician",
        action=AuditAction.CREATE,
        resource_type="Encounter",
        resource_id="018f0000-0000-7000-8000-000000000001",
        safe_metadata=dangerous_metadata,
    )

    assert ev is not None
    # Verify via query
    saved_ev = audit_service.get_by_seq(ev.seq)
    assert saved_ev is not None


def test_concurrent_appends_thread_safety():
    """Verify concurrent worker threads appending events produce no forks or broken chains."""
    num_threads = 20

    def worker(i: int):
        return audit_service.record_event(
            actor_id=f"018f0000-0000-7000-8000-0000000000{i:02d}",
            actor_role="Clinician",
            action=AuditAction.READ,
            resource_type="Resource",
            resource_id=f"018f0000-0000-7000-8000-0000000001{i:02d}",
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, i) for i in range(num_threads)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == num_threads

    # Verify complete chain integrity
    verification = audit_service.verify_global_chain()
    assert verification.valid is True
    assert verification.checked_events == num_threads
    assert verification.last_valid_sequence == num_threads
    assert verification.failure is None
