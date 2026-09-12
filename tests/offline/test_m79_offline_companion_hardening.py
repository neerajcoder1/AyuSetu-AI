"""
AyuSetu M7.9 — Offline Operation & Companion Hardening Acceptance Tests
========================================================================
Authoritative tests verifying PRD v3 §15.2, §16.2, §23.4, §23.5, and §23.6.
"""

import pytest
import uuid6
from fastapi.testclient import TestClient

from ayusetu.common.session_cache import SessionCache
from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.auth.event_hooks import register_security_event_listener, SecurityEvent
from ayusetu.gateway.errors import AyuSetuGatewayError
from ayusetu.security.offline_reconciliation import (
    offline_reconciler,
    OfflineConsentRecord,
    OfflineEncounterBatch,
)


@pytest.fixture
def app_client():
    return TestClient(gateway_app)


@pytest.fixture
def recorded_security_events():
    events = []
    def listener(event: SecurityEvent):
        events.append(event)
    register_security_event_listener(listener)
    return events


def test_offline_consent_hash_chained_creation():
    """
    PRD §15.2: Offline consent recorded locally with hash-chained timestamp.
    """
    offline_reconciler.clear()

    c1 = offline_reconciler.create_offline_consent(
        consent_id="offline-consent-001",
        patient_id="pat-001",
        encounter_id="enc-001",
        purposes={"clinical": True, "abdm": True},
        station_id="kiosk-station-01",
        prev_hash="GENESIS_OFFLINE_HASH",
    )
    assert c1.consent_id == "offline-consent-001"
    assert c1.prev_hash == "GENESIS_OFFLINE_HASH"
    assert len(c1.entry_hash) == 64
    assert c1.abdm_synced is False  # Must remain explicitly unsynced until live ABDM reconnection

    c2 = offline_reconciler.create_offline_consent(
        consent_id="offline-consent-002",
        patient_id="pat-002",
        encounter_id="enc-002",
        purposes={"clinical": True, "abdm": False},
        station_id="kiosk-station-01",
        prev_hash=c1.entry_hash,
    )
    assert c2.prev_hash == c1.entry_hash
    assert len(c2.entry_hash) == 64


def test_offline_batch_reconcile_success():
    """
    PRD §23.6: Offline audit & encounter batch reconciliation upon reconnect.
    """
    offline_reconciler.clear()

    c1 = offline_reconciler.create_offline_consent(
        consent_id="c-rec-1",
        patient_id="p-rec-1",
        encounter_id="e-rec-1",
        purposes={"clinical": True},
        station_id="station-north-1",
        prev_hash="GENESIS_OFFLINE_HASH",
    )

    batch = OfflineEncounterBatch(
        station_id="station-north-1",
        batch_id="batch-001",
        created_at="2026-09-12T10:00:00Z",
        consents=[c1],
        submissions=[{"encounter_id": "e-rec-1", "session_id": "sess-rec-1"}],
    )

    res = offline_reconciler.reconcile_batch(batch, authenticated_station_id="station-north-1")
    assert res["status"] == "reconciled"
    assert res["consents_replayed"] == 1
    assert res["submissions_replayed"] == 1
    assert res["abdm_verification_status"] == "OFFLINE_PROVISIONAL_PENDING_LIVE_ABDM_SYNC"


def test_offline_batch_tamper_detection_quarantines_batch(recorded_security_events):
    """
    PRD §23.6: Tampered offline consent/audit chain halts replay and quarantines.
    """
    offline_reconciler.clear()

    # Broken chain: c2 prev_hash does not match c1 entry_hash
    c1 = offline_reconciler.create_offline_consent(
        consent_id="c-tamper-1",
        patient_id="p-1",
        encounter_id="e-1",
        purposes={"clinical": True},
        station_id="station-south-1",
        prev_hash="GENESIS_OFFLINE_HASH",
    )
    c2 = OfflineConsentRecord(
        consent_id="c-tamper-2",
        patient_id="p-2",
        encounter_id="e-2",
        purposes={"clinical": True},
        timestamp="1234567890",
        station_id="station-south-1",
        prev_hash="CORRUPTED_PREV_HASH_TAMPERED",
        entry_hash="fake_hash",
        abdm_synced=False,
    )

    batch = OfflineEncounterBatch(
        station_id="station-south-1",
        batch_id="batch-tampered",
        created_at="2026-09-12T10:00:00Z",
        consents=[c1, c2],
        submissions=[],
    )

    with pytest.raises(AyuSetuGatewayError) as exc_info:
        offline_reconciler.reconcile_batch(batch, authenticated_station_id="station-south-1")
    assert exc_info.value.status_code == 403

    assert any(ev.event_type == "OFFLINE_AUDIT_QUARANTINED" for ev in recorded_security_events)


def test_offline_batch_station_spoofing_rejected(recorded_security_events):
    """
    PRD §21.3 / §23.4: Reconcile rejected if authenticated device does not match batch station ID.
    """
    offline_reconciler.clear()

    batch = OfflineEncounterBatch(
        station_id="station-victim-01",
        batch_id="batch-spoof",
        created_at="2026-09-12T10:00:00Z",
        consents=[],
        submissions=[],
    )

    with pytest.raises(AyuSetuGatewayError) as exc_info:
        offline_reconciler.reconcile_batch(batch, authenticated_station_id="station-attacker-99")
    assert exc_info.value.status_code == 403

    assert any(ev.event_type == "OFFLINE_AUDIT_QUARANTINED" for ev in recorded_security_events)


def test_offline_batch_deduplication_on_repeated_reconnect():
    """
    PRD §23.6: Deterministic reconciliation on reconnect with idempotent deduplication.
    """
    offline_reconciler.clear()

    c1 = offline_reconciler.create_offline_consent(
        consent_id="c-dedup-1",
        patient_id="p-dedup-1",
        encounter_id="e-dedup-1",
        purposes={"clinical": True},
        station_id="station-west-1",
        prev_hash="GENESIS_OFFLINE_HASH",
    )

    batch = OfflineEncounterBatch(
        station_id="station-west-1",
        batch_id="batch-dedup-01",
        created_at="2026-09-12T10:00:00Z",
        consents=[c1],
        submissions=[{"encounter_id": "e-dedup-1", "session_id": "sess-dedup-1"}],
    )

    # 1. First sync
    res1 = offline_reconciler.reconcile_batch(batch, authenticated_station_id="station-west-1")
    assert res1["consents_replayed"] == 1
    assert res1["submissions_replayed"] == 1

    # 2. Re-sync identical batch (network retry) -> 100% deduplicated, 0 duplicate records
    res2 = offline_reconciler.reconcile_batch(batch, authenticated_station_id="station-west-1")
    assert res2["consents_replayed"] == 0
    assert res2["consents_deduplicated"] == 1
    assert res2["submissions_replayed"] == 0
    assert res2["submissions_deduplicated"] == 1
