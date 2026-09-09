"""
Consent PostgreSQL Persistence & Crash-Recovery Tests
=====================================================
Validates durable database storage of DPDP consent records, process-restart
recovery of active consent, immutable version history, fail-closed gating,
and 4-purpose independence per PRD v2.0 §21.7 & §21.8.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ayusetu.common.database import Base
from ayusetu.common.models import ConsentRecord, Patient, Encounter
from ayusetu.consent.models import (
    Purposes,
    ConsentGrantRequest,
    ConsentWithdrawRequest,
    OfflineConsentPayload,
    ConsentStatus,
)
from ayusetu.consent.repository import ConsentRepository
from ayusetu.consent.service import ConsentService


@pytest.fixture
def isolated_consent_db_factory(tmp_path):
    """Create an isolated file-backed SQLite database to simulate clean process restarts."""
    db_file = tmp_path / "test_consent_durable.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine, tables=[Patient.__table__, Encounter.__table__, ConsentRecord.__table__])
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False, class_=Session)
    return factory


def test_consent_creation_persists_to_database(isolated_consent_db_factory):
    """Verify granting consent creates a durable row directly in PostgreSQL/database."""
    repo = ConsentRepository(session_factory=isolated_consent_db_factory)
    service = ConsentService(repository=repo)

    enc_id = "018f0000-0000-7000-8000-000000000010"
    pat_id = "018f0000-0000-7000-8000-000000000001"

    record = service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True, abdm=True, qi=False, research=False),
            language="hi",
            notice_version="dpdp-v1.0",
        )
    )

    assert record.version == 1
    assert record.status == ConsentStatus.ACTIVE
    assert record.purposes["clinical"] is True
    assert record.purposes["abdm"] is True
    assert record.purposes["qi"] is False

    # Direct DB inspection
    with isolated_consent_db_factory() as db:
        row = db.query(ConsentRecord).filter(ConsentRecord.encounter_id == enc_id).first()
        assert row is not None
        assert str(row.id) == record.id
        assert str(row.patient_id) == pat_id
        assert str(row.encounter_id) == enc_id
        assert row.purposes["clinical"] is True
        assert row.purposes["abdm"] is True


def test_consent_survives_service_restart(isolated_consent_db_factory):
    """
    Simulate process restart:
    1. Grant consent using Service Instance 1
    2. Destroy Instance 1
    3. Initialize fresh Service Instance 2 bound to same database
    4. Assert Instance 2 recovers active consent and clinical gating
    """
    repo_1 = ConsentRepository(session_factory=isolated_consent_db_factory)
    service_1 = ConsentService(repository=repo_1)

    enc_id = "018f0000-0000-7000-8000-000000000020"
    pat_id = "018f0000-0000-7000-8000-000000000002"

    rec1 = service_1.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True, abdm=False, qi=True, research=False),
            language="en",
            notice_version="dpdp-v1.0",
        )
    )
    assert service_1.check_clinical_consent(enc_id) is True
    assert service_1.check_purpose_consent(enc_id, "qi") is True

    del service_1
    del repo_1

    # Instance 2 (Simulates clean server reboot)
    repo_2 = ConsentRepository(session_factory=isolated_consent_db_factory)
    service_2 = ConsentService(repository=repo_2)

    active = service_2.get_active_consent(enc_id)
    assert active is not None
    assert active.id == rec1.id
    assert active.version == 1
    assert active.status == ConsentStatus.ACTIVE
    assert service_2.check_clinical_consent(enc_id) is True
    assert service_2.check_purpose_consent(enc_id, "qi") is True
    assert service_2.check_purpose_consent(enc_id, "abdm") is False


def test_consent_withdrawal_creates_immutable_new_version(isolated_consent_db_factory):
    """
    Verify consent withdrawal appends a new immutable version without mutating earlier versions in DB:
    - Version 1: clinical=True, abdm=True, research=True
    - Withdraw research
    - Version 2: clinical=True, abdm=True, research=False
    - Verify both version rows exist independently in the database
    """
    repo = ConsentRepository(session_factory=isolated_consent_db_factory)
    service = ConsentService(repository=repo)

    enc_id = "018f0000-0000-7000-8000-000000000030"
    pat_id = "018f0000-0000-7000-8000-000000000003"

    # 1. Grant Version 1
    rec1 = service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True, abdm=True, qi=False, research=True),
        )
    )
    assert rec1.version == 1

    # 2. Withdraw Research (Creates Version 2)
    rec2 = service.withdraw_consent(
        ConsentWithdrawRequest(
            encounter_id=enc_id,
            purposes_to_withdraw=["research"],
            reason="Patient withdrew research consent",
        )
    )
    assert rec2.version == 2
    assert rec2.status == ConsentStatus.PARTIALLY_WITHDRAWN
    assert rec2.purposes["clinical"] is True
    assert rec2.purposes["research"] is False
    assert rec2.withdrawn_at is not None

    # 3. Direct DB Inspection: Verify Version 1 row in DB remains UNTOUCHED
    with isolated_consent_db_factory() as db:
        rows = db.query(ConsentRecord).filter(ConsentRecord.encounter_id == enc_id).order_by(ConsentRecord.granted_at.asc()).all()
        assert len(rows) == 2

        # Row 1 (Version 1) still has research=True and withdrawn_at=None
        row1 = rows[0]
        assert str(row1.id) == rec1.id
        assert row1.purposes["research"] is True
        assert row1.withdrawn_at is None

        # Row 2 (Version 2) has research=False and withdrawn_at set
        row2 = rows[1]
        assert str(row2.id) == rec2.id
        assert row2.purposes["research"] is False
        assert row2.withdrawn_at is not None


def test_multi_instance_restart_lifecycle(isolated_consent_db_factory):
    """
    Simulate full multi-generation restart:
    Instance A: Grant Version 1
    Instance B: Restart, read V1, withdraw ABDM -> Save Version 2
    Instance C: Restart, read V2, withdraw all -> Save Version 3
    Instance D: Restart, verify clinical intake is blocked (fail closed)
    """
    enc_id = "018f0000-0000-7000-8000-000000000040"
    pat_id = "018f0000-0000-7000-8000-000000000004"

    # Instance A
    service_a = ConsentService(repository=ConsentRepository(session_factory=isolated_consent_db_factory))
    service_a.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True, abdm=True, qi=True, research=True),
        )
    )

    # Instance B
    service_b = ConsentService(repository=ConsentRepository(session_factory=isolated_consent_db_factory))
    rec_b = service_b.withdraw_consent(
        ConsentWithdrawRequest(encounter_id=enc_id, purposes_to_withdraw=["abdm"])
    )
    assert rec_b.version == 2
    assert service_b.check_purpose_consent(enc_id, "abdm") is False
    assert service_b.check_clinical_consent(enc_id) is True

    # Instance C
    service_c = ConsentService(repository=ConsentRepository(session_factory=isolated_consent_db_factory))
    rec_c = service_c.withdraw_consent(
        ConsentWithdrawRequest(encounter_id=enc_id, purposes_to_withdraw=["all"])
    )
    assert rec_c.version == 3
    assert rec_c.status == ConsentStatus.WITHDRAWN

    # Instance D
    service_d = ConsentService(repository=ConsentRepository(session_factory=isolated_consent_db_factory))
    assert service_d.check_clinical_consent(enc_id) is False
    assert service_d.check_purpose_consent(enc_id, "qi") is False
    history = service_d.get_consent_history(enc_id)
    assert len(history) == 3


def test_multi_version_lifecycle_ordering(isolated_consent_db_factory):
    """
    PART 1: Verify deterministic multi-version ordering:
    V1: Grant (clinical=True, abdm=True, qi=False, research=True)
    V2: Optional-purpose withdrawal (withdraw research)
    V3: Optional-purpose update (withdraw abdm)
    V4: Clinical withdrawal (withdraw clinical)

    Asserts:
    - V1 < V2 < V3 < V4 in both version sequence and UUIDv7 chronological ordering
    - Process restart returns V4 as authoritative latest state
    - Complete history [V1, V2, V3, V4] is reconstructed with exact versions
    """
    repo = ConsentRepository(session_factory=isolated_consent_db_factory)
    service = ConsentService(repository=repo)

    enc_id = "018f0000-0000-7000-8000-000000000050"
    pat_id = "018f0000-0000-7000-8000-000000000005"

    # V1: Grant
    v1 = service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True, abdm=True, qi=False, research=True),
            language="en",
            notice_version="dpdp-v1.0",
        )
    )
    assert v1.version == 1
    assert v1.status == ConsentStatus.ACTIVE

    # V2: Optional-purpose withdrawal (research)
    v2 = service.withdraw_consent(
        ConsentWithdrawRequest(
            encounter_id=enc_id,
            purposes_to_withdraw=["research"],
            reason="Patient opted out of research",
        )
    )
    assert v2.version == 2
    assert v2.status == ConsentStatus.PARTIALLY_WITHDRAWN
    assert v2.purposes["research"] is False
    assert v2.purposes["abdm"] is True
    assert v2.purposes["clinical"] is True

    # V3: Optional-purpose withdrawal (abdm)
    v3 = service.withdraw_consent(
        ConsentWithdrawRequest(
            encounter_id=enc_id,
            purposes_to_withdraw=["abdm"],
            reason="Patient opted out of ABDM linkage",
        )
    )
    assert v3.version == 3
    assert v3.status == ConsentStatus.PARTIALLY_WITHDRAWN
    assert v3.purposes["abdm"] is False
    assert v3.purposes["clinical"] is True

    # V4: Clinical withdrawal
    v4 = service.withdraw_consent(
        ConsentWithdrawRequest(
            encounter_id=enc_id,
            purposes_to_withdraw=["clinical"],
            reason="Patient withdrew clinical intake consent",
        )
    )
    assert v4.version == 4
    assert v4.status == ConsentStatus.WITHDRAWN
    assert v4.purposes["clinical"] is False

    # Assert strict version monotonicity
    assert v1.version < v2.version < v3.version < v4.version
    assert v1.id < v2.id < v3.id < v4.id

    # Destroy in-memory instances and simulate process restart
    del service
    del repo

    # Service Restart: Recover state from PostgreSQL/database
    repo_restarted = ConsentRepository(session_factory=isolated_consent_db_factory)
    service_restarted = ConsentService(repository=repo_restarted)

    # 1. Authoritative latest state must be V4
    latest = service_restarted.get_active_consent(enc_id)
    assert latest is not None
    assert latest.id == v4.id
    assert latest.version == 4
    assert latest.status == ConsentStatus.WITHDRAWN
    assert latest.purposes["clinical"] is False
    assert latest.purposes["abdm"] is False
    assert latest.purposes["research"] is False

    # 2. Clinical and purpose gating must reflect V4
    assert service_restarted.check_clinical_consent(enc_id) is False
    assert service_restarted.check_purpose_consent(enc_id, "clinical") is False
    assert service_restarted.check_purpose_consent(enc_id, "abdm") is False
    assert service_restarted.check_purpose_consent(enc_id, "research") is False
    assert service_restarted.is_external_sharing_permitted(enc_id) is False

    # 3. Full history reconstruction must contain [V1, V2, V3, V4]
    history = service_restarted.get_consent_history(enc_id)
    assert len(history) == 4
    assert [h.version for h in history] == [1, 2, 3, 4]
    assert [h.id for h in history] == [v1.id, v2.id, v3.id, v4.id]
    assert history[0].purposes["research"] is True
    assert history[1].purposes["research"] is False
    assert history[2].purposes["abdm"] is False
    assert history[3].purposes["clinical"] is False


def test_concurrent_consent_updates_serialization(isolated_consent_db_factory):
    """
    PART 2: Real database concurrency test targeting the SAME encounter.
    Executes concurrent threads that perform simultaneous consent updates against the database.
    Proves:
    - Concurrent requests execute simultaneously
    - Database transactions serialize writes
    - No lost updates occur
    - No duplicate logical version is created
    - History remains valid and strictly ordered
    - Latest-version recovery is deterministic
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    repo = ConsentRepository(session_factory=isolated_consent_db_factory)
    service = ConsentService(repository=repo)

    enc_id = "018f0000-0000-7000-8000-000000000060"
    pat_id = "018f0000-0000-7000-8000-000000000006"

    # Initial V1 grant
    v1 = service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True, abdm=True, qi=True, research=True),
            language="en",
            notice_version="dpdp-v1.0",
        )
    )
    assert v1.version == 1

    # Concurrently perform 4 updates targeting the same encounter
    purposes_to_withdraw = [
        ["research"],
        ["qi"],
        ["abdm"],
        ["clinical"],
    ]

    results = []
    errors = []

    def perform_withdrawal(purposes, idx):
        worker_repo = ConsentRepository(session_factory=isolated_consent_db_factory)
        worker_service = ConsentService(repository=worker_repo)
        return worker_service.withdraw_consent(
            ConsentWithdrawRequest(
                encounter_id=enc_id,
                purposes_to_withdraw=purposes,
                reason=f"Concurrent withdrawal worker {idx}",
            )
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(perform_withdrawal, p, i): i
            for i, p in enumerate(purposes_to_withdraw)
        }
        for future in as_completed(futures):
            try:
                res = future.result()
                results.append(res)
            except Exception as exc:
                errors.append(exc)

    assert len(errors) == 0, f"Unexpected concurrency errors: {errors}"
    assert len(results) == 4

    # Verify all version numbers are unique and strictly 2, 3, 4, 5
    returned_versions = sorted([r.version for r in results])
    assert returned_versions == [2, 3, 4, 5], f"Expected versions [2, 3, 4, 5], got {returned_versions}"

    # Verify history in database has exactly 5 records
    history = service.get_consent_history(enc_id)
    assert len(history) == 5
    assert [h.version for h in history] == [1, 2, 3, 4, 5]

    # Verify UUIDv7 IDs are strictly monotonic
    for i in range(len(history) - 1):
        assert history[i].id < history[i + 1].id

    # Verify latest active state
    latest = service.get_active_consent(enc_id)
    assert latest is not None
    assert latest.version == 5
    assert latest.id == history[-1].id


def test_consent_fails_closed_when_db_fails():
    """
    PART 3: Verify fail-closed behavior across all authoritative consent paths:
    - grant_consent
    - withdraw_consent
    - check_clinical_consent
    - check_purpose_consent
    - is_external_sharing_permitted
    - get_active_consent
    - get_consent_history
    - capture_offline_consent
    """
    broken_session_factory = MagicMock(side_effect=RuntimeError("PostgreSQL connection severed"))
    broken_repo = ConsentRepository(session_factory=broken_session_factory)
    broken_service = ConsentService(repository=broken_repo)

    enc_id = "018f0000-0000-7000-8000-000000000099"
    pat_id = "018f0000-0000-7000-8000-000000000009"

    # 1. Gating checks must fail closed (return False, never True)
    assert broken_service.check_clinical_consent(enc_id) is False
    assert broken_service.check_purpose_consent(enc_id, "clinical") is False
    assert broken_service.check_purpose_consent(enc_id, "abdm") is False
    assert broken_service.check_purpose_consent(enc_id, "qi") is False
    assert broken_service.check_purpose_consent(enc_id, "research") is False
    assert broken_service.is_external_sharing_permitted(enc_id) is False

    # 2. Authoritative state queries must raise on DB failure (never return fake granted state)
    with pytest.raises(RuntimeError):
        broken_service.get_active_consent(enc_id)

    with pytest.raises(RuntimeError):
        broken_service.get_consent_history(enc_id)

    # 3. Grant / Withdraw must fail closed on DB failure (transaction rolled back, no successful response)
    with pytest.raises(RuntimeError):
        broken_service.grant_consent(
            ConsentGrantRequest(
                patient_id=pat_id,
                encounter_id=enc_id,
                purposes=Purposes(clinical=True),
            )
        )

    with pytest.raises(RuntimeError):
        broken_service.withdraw_consent(
            ConsentWithdrawRequest(
                encounter_id=enc_id,
                purposes_to_withdraw=["all"],
            )
        )

    # 4. Offline capture must fail closed on DB failure
    with pytest.raises(RuntimeError):
        broken_service.capture_offline_consent(
            OfflineConsentPayload(
                patient_id=pat_id,
                encounter_id=enc_id,
                purposes=Purposes(clinical=True),
                language="hi",
                notice_version="dpdp-v1.0",
                device_id="station-01",
                captured_at=datetime.now(timezone.utc),
            )
        )
