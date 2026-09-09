"""
Test Suite: Consent & DPDP Core Service Engine
===============================================
Comprehensive unit test suite for ConsentService domain rules, 4-purpose isolation,
true immutability, withdrawal, erasure, offline invariants, guardian rules, and panic-clear.
"""

from copy import deepcopy
from datetime import datetime, timezone
import uuid6
import pytest

from ayusetu.consent.models import (
    Purposes,
    GuardianContext,
    GuardianRelationship,
    ConsentGrantRequest,
    ConsentWithdrawRequest,
    ErasureRequest,
    OfflineConsentPayload,
    ConsentStatus,
    ABDMArtifactStatus,
)
from ayusetu.consent.service import consent_service
from ayusetu.consent.guardian import GuardianVerificationAdapter
from ayusetu.consent.offline_chain import station_consent_chain
from ayusetu.consent.abdm_adapter import abdm_manager
from ayusetu.consent.event_hooks import register_event_listener, clear_event_listeners
from ayusetu.gateway.auth.models import Principal, Role
from ayusetu.gateway.errors import AyuSetuGatewayError, ErrorCode


@pytest.fixture(autouse=True)
def clean_service_state():
    consent_service.reset_state()
    clear_event_listeners()
    yield
    consent_service.reset_state()
    clear_event_listeners()


# 1. Authoritative 4-Purpose Model & Clinical Gating
def test_clinical_consent_granted_allows_intake():
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    req = ConsentGrantRequest(
        patient_id=pat_id,
        encounter_id=enc_id,
        purposes=Purposes(clinical=True, abdm=False, qi=False, research=False),
    )
    record = consent_service.grant_consent(req)
    assert record.version == 1
    assert record.status == ConsentStatus.ACTIVE
    assert consent_service.check_clinical_consent(enc_id) is True


def test_no_clinical_consent_denies_intake():
    enc_id = str(uuid6.uuid7())
    # No consent registered for this encounter
    assert consent_service.check_clinical_consent(enc_id) is False


def test_clinical_consent_withdrawn_denies_intake():
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
        )
    )
    assert consent_service.check_clinical_consent(enc_id) is True

    # Withdraw all consent
    consent_service.withdraw_consent(
        ConsentWithdrawRequest(encounter_id=enc_id, purposes_to_withdraw=["all"])
    )
    assert consent_service.check_clinical_consent(enc_id) is False


# 2. Optional Purpose Isolation & Independent Refusal
def test_refusing_abdm_does_not_block_clinical():
    enc_id = str(uuid6.uuid7())
    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            purposes=Purposes(clinical=True, abdm=False),
        )
    )
    assert consent_service.check_clinical_consent(enc_id) is True
    assert consent_service.check_purpose_consent(enc_id, "abdm") is False


def test_refusing_qi_does_not_block_clinical():
    enc_id = str(uuid6.uuid7())
    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            purposes=Purposes(clinical=True, qi=False),
        )
    )
    assert consent_service.check_clinical_consent(enc_id) is True
    assert consent_service.check_purpose_consent(enc_id, "qi") is False


def test_refusing_research_does_not_block_clinical():
    enc_id = str(uuid6.uuid7())
    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            purposes=Purposes(clinical=True, research=False),
        )
    )
    assert consent_service.check_clinical_consent(enc_id) is True
    assert consent_service.check_purpose_consent(enc_id, "research") is False


def test_optional_purposes_default_to_off():
    purposes = Purposes(clinical=True)
    assert purposes.abdm is False
    assert purposes.qi is False
    assert purposes.research is False


def test_optional_consent_not_inferred_from_clinical():
    enc_id = str(uuid6.uuid7())
    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
        )
    )
    assert consent_service.check_clinical_consent(enc_id) is True
    assert consent_service.check_purpose_consent(enc_id, "abdm") is False
    assert consent_service.check_purpose_consent(enc_id, "qi") is False
    assert consent_service.check_purpose_consent(enc_id, "research") is False


# 3. Purpose-Level Withdrawal & True Immutability
def test_withdraw_individual_purpose_preserves_clinical():
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    # Grant all 4 purposes
    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True, abdm=True, qi=True, research=True),
        )
    )

    # Withdraw only research
    w_rec = consent_service.withdraw_consent(
        ConsentWithdrawRequest(encounter_id=enc_id, purposes_to_withdraw=["research"])
    )
    assert w_rec.version == 2
    assert w_rec.status == ConsentStatus.PARTIALLY_WITHDRAWN
    assert w_rec.purposes["clinical"] is True
    assert w_rec.purposes["abdm"] is True
    assert w_rec.purposes["research"] is False

    # Clinical remains valid
    assert consent_service.check_clinical_consent(enc_id) is True
    assert consent_service.check_purpose_consent(enc_id, "research") is False


def test_true_immutability_of_historical_consent_records():
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    # Version 1 created
    v1_created = consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True, abdm=True, research=True),
        )
    )
    v1_snapshot = deepcopy(v1_created.model_dump())

    # Version 2 created (withdrawal of research)
    v2_created = consent_service.withdraw_consent(
        ConsentWithdrawRequest(encounter_id=enc_id, purposes_to_withdraw=["research"])
    )

    history = consent_service.get_consent_history(enc_id)
    assert len(history) == 2

    # Verify Version 1 is 100% byte-for-byte / field-for-field unmodified
    assert history[0].model_dump() == v1_snapshot
    assert history[0].withdrawn_at is None
    assert history[0].status == ConsentStatus.ACTIVE
    assert history[0].purposes["research"] is True

    # Verify Version 2 reflects the new state
    assert history[1].version == 2
    assert history[1].withdrawn_at is not None
    assert history[1].status == ConsentStatus.PARTIALLY_WITHDRAWN
    assert history[1].purposes["research"] is False
    assert history[1].purposes["clinical"] is True


# 4. Guardian / Under-18 & Companion Rules (Adapter-backed)
def test_under_18_without_guardian_rejected():
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    with pytest.raises(AyuSetuGatewayError) as exc_info:
        consent_service.grant_consent(
            ConsentGrantRequest(
                patient_id=pat_id,
                encounter_id=enc_id,
                purposes=Purposes(clinical=True),
                is_minor=True,
                guardian_context=None,  # Missing guardian!
            )
        )
    assert exc_info.value.status_code == 403
    assert "Guardian consent is required" in exc_info.value.message


def test_under_18_with_unverified_guardian_rejected_even_if_client_claims_verified():
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    # Client sets is_verified: True in JSON, but adapter does not have it registered!
    with pytest.raises(AyuSetuGatewayError) as exc_info:
        consent_service.grant_consent(
            ConsentGrantRequest(
                patient_id=pat_id,
                encounter_id=enc_id,
                purposes=Purposes(clinical=True),
                is_minor=True,
                guardian_context=GuardianContext(
                    guardian_id="unregistered-guardian-99",
                    guardian_name="Ramesh Sharma",
                    relationship=GuardianRelationship.PARENT,
                    is_verified=True,  # Client lies!
                ),
            )
        )
    assert exc_info.value.status_code == 403
    assert "is not verified" in exc_info.value.message


def test_under_18_with_adapter_verified_guardian_succeeds():
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    # Register in authoritative verification adapter
    GuardianVerificationAdapter.register_verified_guardian("g-001", pat_id)

    record = consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
            is_minor=True,
            guardian_context=GuardianContext(
                guardian_id="g-001",
                guardian_name="Ramesh Sharma",
                relationship=GuardianRelationship.PARENT,
            ),
        )
    )
    assert record.guardian_id == "g-001"
    assert consent_service.check_clinical_consent(enc_id) is True


def test_companion_cannot_independently_grant_consent_for_adult():
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())
    companion_principal = Principal(actor_id="comp-001", role=Role.COMPANION, is_authenticated=True)

    with pytest.raises(AyuSetuGatewayError) as exc_info:
        consent_service.grant_consent(
            ConsentGrantRequest(
                patient_id=pat_id,
                encounter_id=enc_id,
                purposes=Purposes(clinical=True),
                is_minor=False,
            ),
            principal=companion_principal,
        )
    assert exc_info.value.status_code == 403
    assert "Companion role cannot independently grant consent" in exc_info.value.message


# 5. Offline Consent & ABDM Invariants (No Fabrication)
def test_offline_consent_recorded_locally_with_timestamp():
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    payload = OfflineConsentPayload(
        patient_id=pat_id,
        encounter_id=enc_id,
        purposes=Purposes(clinical=True, abdm=True),
        device_id="kiosk-station-offline-01",
        captured_at=datetime.now(timezone.utc),
    )
    record = consent_service.capture_offline_consent(payload)
    assert record.is_offline is True
    assert record.chain_hash is not None
    assert consent_service.check_clinical_consent(enc_id) is True


def test_offline_consent_does_not_create_abdm_artefact():
    enc_id = str(uuid6.uuid7())
    payload = OfflineConsentPayload(
        patient_id=str(uuid6.uuid7()),
        encounter_id=enc_id,
        purposes=Purposes(clinical=True, abdm=True),
        device_id="kiosk-station-offline-01",
    )
    record = consent_service.capture_offline_consent(payload)
    assert record.abdm_artefact_id is None

    abdm_stat = abdm_manager.get_status(enc_id)
    assert abdm_stat.status == ABDMArtifactStatus.PENDING
    assert abdm_stat.artefact_id is None
    assert abdm_stat.is_external_sharing_permitted is False


def test_offline_sync_does_not_fabricate_artefact_and_keeps_pending():
    enc_id = str(uuid6.uuid7())
    payload = OfflineConsentPayload(
        patient_id=str(uuid6.uuid7()),
        encounter_id=enc_id,
        purposes=Purposes(clinical=True, abdm=True),
        device_id="kiosk-station-offline-01",
    )
    consent_service.capture_offline_consent(payload)
    assert consent_service.is_external_sharing_permitted(enc_id) is False

    # Sync offline logs upon reconnection
    sync_resp = consent_service.sync_offline_consent()
    assert sync_resp.synced_count == 1
    assert sync_resp.chain_verified is True
    assert sync_resp.pending_abdm_requests == 1

    # CRITICAL: ABDM status must remain PENDING after sync (NO fabrication!)
    status_after_sync = abdm_manager.get_status(enc_id)
    assert status_after_sync.status == ABDMArtifactStatus.PENDING
    assert status_after_sync.artefact_id is None
    assert consent_service.is_external_sharing_permitted(enc_id) is False

    # Only when authoritative CM callback is received does it transition to AVAILABLE
    abdm_manager.handle_authoritative_artefact_callback(enc_id, "abdm-art-auth-99999")
    status_after_cb = abdm_manager.get_status(enc_id)
    assert status_after_cb.status == ABDMArtifactStatus.AVAILABLE
    assert status_after_cb.artefact_id == "abdm-art-auth-99999"
    assert consent_service.is_external_sharing_permitted(enc_id) is True

    # Withdrawing ABDM consent disables external sharing again
    consent_service.withdraw_consent(
        ConsentWithdrawRequest(encounter_id=enc_id, purposes_to_withdraw=["abdm"])
    )
    assert consent_service.is_external_sharing_permitted(enc_id) is False


# 6. Erasure Handling & Idempotency
def test_erasure_request_idempotent():
    pat_id = str(uuid6.uuid7())
    enc_id = str(uuid6.uuid7())

    req1 = consent_service.request_erasure(
        ErasureRequest(patient_id=pat_id, encounter_id=enc_id)
    )
    assert req1.status.value == "propagated"

    req2 = consent_service.request_erasure(
        ErasureRequest(patient_id=pat_id, encounter_id=enc_id)
    )
    assert req2.request_id == req1.request_id


# 7. Panic Clear Integration
def test_panic_clear_does_not_falsely_erase_historical_consent():
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
        )
    )

    session_id = "sess-kiosk-test-123"
    consent_service.handle_session_panic_clear(session_id, enc_id)

    assert consent_service.get_active_consent(enc_id) is not None
    assert consent_service.check_clinical_consent(enc_id) is True


# 8. Zero-PHI Audit Events
def test_audit_hooks_fire_with_zero_phi():
    events_captured = []
    register_event_listener(lambda e: events_captured.append(e))

    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True, abdm=True),
        )
    )
    consent_service.withdraw_consent(
        ConsentWithdrawRequest(encounter_id=enc_id, purposes_to_withdraw=["abdm"])
    )
    consent_service.request_erasure(
        ErasureRequest(patient_id=pat_id, encounter_id=enc_id)
    )

    assert len(events_captured) >= 3
    event_types = [e["event_type"] for e in events_captured]
    assert "CONSENT_GRANTED" in event_types
    assert "CONSENT_WITHDRAWN" in event_types
    assert "ERASURE_REQUESTED" in event_types

    for e in events_captured:
        assert "transcript" not in e
        assert "audio" not in e
        assert "name" not in e
        assert "mobile" not in e
        assert "slots" not in e
