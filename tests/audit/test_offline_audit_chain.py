"""
Offline Station Audit Chain & Splicing Tests
============================================
Tests offline station logging, reconnect verification, global splicing,
and quarantine isolation of tampered or unanchored offline batches.
"""

import pytest
from ayusetu.audit.models import AuditAction, OfflineAuditEventDTO, OfflineAuditSyncBatch
from ayusetu.audit.offline_chain import OfflineStationAuditChain
from ayusetu.audit.service import audit_service
from ayusetu.gateway.errors import AyuSetuGatewayError


def test_offline_station_chain_generation():
    """Verify local offline chain records events with local_seq and hash chaining."""
    seed_hash = "a" * 64
    station = OfflineStationAuditChain(device_id="station-opd-01", seed_head_hash=seed_hash)

    ev1 = station.record_offline_event(
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="attendant",
        action="CREATE",
        resource_type="Patient",
        resource_id="018f0000-0000-7000-8000-000000000010",
    )
    assert ev1.local_seq == 1
    assert ev1.prev_hash == seed_hash

    ev2 = station.record_offline_event(
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="attendant",
        action="CREATE",
        resource_type="Encounter",
        resource_id="018f0000-0000-7000-8000-000000000020",
    )
    assert ev2.local_seq == 2
    assert ev2.prev_hash == ev1.entry_hash

    batch = station.get_sync_batch()
    assert batch.device_id == "station-opd-01"
    assert len(batch.events) == 2


def test_offline_batch_successful_sync_and_splicing():
    """Verify valid offline batch is verified, spliced into global chain, and advances server head."""
    # 1. Record an event on server to establish known server head
    ev_server = audit_service.record_event(
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="admin",
        action=AuditAction.CREATE,
        resource_type="System",
        resource_id="018f0000-0000-7000-8000-000000000000",
    )
    known_seed_hash = ev_server.entry_hash

    # 2. Offline station records 3 events seeded with known_seed_hash
    station = OfflineStationAuditChain(device_id="station-opd-02", seed_head_hash=known_seed_hash)
    for i in range(3):
        station.record_offline_event(
            actor_id="018f0000-0000-7000-8000-000000000002",
            actor_role="nurse",
            action="CREATE",
            resource_type="VitalSign",
            resource_id=f"018f0000-0000-7000-8000-0000000000{i:02d}",
        )

    batch = station.get_sync_batch()

    # 3. Server syncs batch
    response = audit_service.sync_offline_batch(batch)
    assert response.status == "SYNCED"
    assert response.synced_count == 3
    assert response.new_head.seq == 4  # 1 server event + 3 offline events

    # 4. Verify full chain validity
    verification = audit_service.verify_global_chain()
    assert verification.valid is True
    assert verification.checked_events == 4


def test_offline_batch_unknown_seed_head_rejected_and_quarantined():
    """Verify offline batch with unknown seed head is rejected with 422 and quarantined."""
    fake_seed_hash = "f" * 64
    station = OfflineStationAuditChain(device_id="station-rogue-01", seed_head_hash=fake_seed_hash)
    station.record_offline_event(
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="attendant",
        action="CREATE",
        resource_type="Patient",
        resource_id="018f0000-0000-7000-8000-000000000010",
    )

    batch = station.get_sync_batch()

    with pytest.raises(AyuSetuGatewayError) as exc_info:
        audit_service.sync_offline_batch(batch)

    assert exc_info.value.status_code == 422
    assert "quarantined" in str(exc_info.value.message).lower()

    # Verify quarantine store has record
    quarantined = audit_service.get_quarantined_records()
    assert len(quarantined) >= 1
    assert any(q.device_id == "station-rogue-01" for q in quarantined)


def test_offline_batch_tampered_payload_rejected_and_quarantined():
    """Verify offline batch with tampered event payload is rejected and quarantined."""
    # Server head
    ev_server = audit_service.record_event(
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="admin",
        action=AuditAction.CREATE,
        resource_type="System",
        resource_id="018f0000-0000-7000-8000-000000000000",
    )
    known_seed_hash = ev_server.entry_hash

    station = OfflineStationAuditChain(device_id="station-tampered-01", seed_head_hash=known_seed_hash)
    station.record_offline_event(
        actor_id="018f0000-0000-7000-8000-000000000002",
        actor_role="nurse",
        action="CREATE",
        resource_type="VitalSign",
        resource_id="018f0000-0000-7000-8000-000000000010",
    )
    batch = station.get_sync_batch()

    # Tamper with action on event 0 without updating entry_hash
    tampered_event = OfflineAuditEventDTO(
        local_seq=batch.events[0].local_seq,
        ts=batch.events[0].ts,
        actor_id=batch.events[0].actor_id,
        actor_role=batch.events[0].actor_role,
        action="DELETE",  # Tampered action
        resource_type=batch.events[0].resource_type,
        resource_id=batch.events[0].resource_id,
        outcome=batch.events[0].outcome,
        reason=batch.events[0].reason,
        src_device=batch.events[0].src_device,
        payload_hash=batch.events[0].payload_hash,
        prev_hash=batch.events[0].prev_hash,
        entry_hash=batch.events[0].entry_hash,  # Mismatched hash
    )
    tampered_batch = OfflineAuditSyncBatch(
        device_id=batch.device_id,
        seed_head_hash=batch.seed_head_hash,
        events=[tampered_event],
    )

    with pytest.raises(AyuSetuGatewayError) as exc_info:
        audit_service.sync_offline_batch(tampered_batch)

    assert exc_info.value.status_code == 422

    # Verify tampered offline events were NOT spliced into the global chain
    assert len(audit_service.query_events(action="DELETE")) == 0
    quarantined = audit_service.get_quarantined_records()
    assert any(q.device_id == "station-tampered-01" for q in quarantined)

    # Verify global chain integrity remains pristine
    assert audit_service.verify_global_chain().valid is True


def test_offline_batch_cross_device_impersonation_rejected_and_quarantined():
    """Verify that submitting a batch claiming another device ID when authenticated as device A is rejected and quarantined."""
    # Server head
    ev_server = audit_service.record_event(
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="admin",
        action=AuditAction.CREATE,
        resource_type="System",
        resource_id="018f0000-0000-7000-8000-000000000000",
    )
    known_seed_hash = ev_server.entry_hash

    # Device creates batch claiming station-victim-01
    station = OfflineStationAuditChain(device_id="station-victim-01", seed_head_hash=known_seed_hash)
    station.record_offline_event(
        actor_id="018f0000-0000-7000-8000-000000000002",
        actor_role="nurse",
        action="CREATE",
        resource_type="VitalSign",
        resource_id="018f0000-0000-7000-8000-000000000010",
    )
    batch = station.get_sync_batch()

    # Attempt to sync with trusted device context 'station-attacker-99'
    with pytest.raises(AyuSetuGatewayError) as exc_info:
        audit_service.sync_offline_batch(batch, trusted_device_id="station-attacker-99")

    assert exc_info.value.status_code == 403
    assert "identity mismatch" in str(exc_info.value.message).lower()

    # Verify quarantine recorded
    quarantined = audit_service.get_quarantined_records()
    assert any(q.failure_code == "DEVICE_IMPERSONATION_ATTEMPT" for q in quarantined)

