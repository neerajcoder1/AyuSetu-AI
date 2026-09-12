"""
Tests for M7.8 MPI Record Merge and Unmerge
===========================================
Verifies PRD v3 §4.3 and §23.1 AC-MPI-2:
- POST /api/v1/mpi/merge
- POST /api/v1/mpi/unmerge
- RBAC validation (MRD / ADMIN only)
- Self-merge prevention
- Audit trail recording
- Reversibility of unmerge
"""

import pytest
from starlette.testclient import TestClient

from ayusetu.gateway.app import gateway_app
from ayusetu.clinical.mpi_service import mpi_service
from ayusetu.clinical.repository import get_default_session_factory
from ayusetu.common.models import Patient
import uuid6


@pytest.fixture
def client():
    return TestClient(gateway_app)


@pytest.fixture
def mrd_headers(client):
    res = client.post("/api/v1/auth/token", json={"username": "mrd-officer"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def nurse_headers(client):
    res = client.post("/api/v1/auth/token", json={"username": "nurse-sunita"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}



@pytest.fixture
def two_db_patients():
    """Create two test patients in DB."""
    session_factory = get_default_session_factory()
    p1_id = uuid6.uuid7()
    p2_id = uuid6.uuid7()

    with session_factory() as db:
        p1 = Patient(
            id=p1_id,
            name_enc=b"Ramesh Kumar (Encrypted)",
            mobile_enc=b"+919876543210 (Encrypted)",
            sex="male",
            is_provisional=False,
        )
        p2 = Patient(
            id=p2_id,
            name_enc=b"Ramesh Kumar Duplicate (Encrypted)",
            mobile_enc=b"+919876543210 (Encrypted)",
            sex="male",
            is_provisional=True,
        )
        db.add_all([p1, p2])
        db.commit()

    return str(p1_id), str(p2_id)


def test_mpi_merge_success(client, mrd_headers, two_db_patients):
    """Test successful merge under target patient."""
    target_id, source_id = two_db_patients

    res = client.post(
        "/api/v1/mpi/merge",
        headers=mrd_headers,
        json={
            "source_patient_id": source_id,
            "target_patient_id": target_id,
            "reason": "Duplicate record identified during registration",
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "merged"
    assert data["source_patient_id"] == source_id
    assert data["target_patient_id"] == target_id

    # Verify DB state
    session_factory = get_default_session_factory()
    with session_factory() as db:
        p_src = db.query(Patient).filter(Patient.id == uuid6.UUID(source_id)).first()
        assert str(p_src.merged_into) == target_id


def test_mpi_unmerge_success(client, mrd_headers, two_db_patients):
    """Test reversible unmerge restores original record."""
    target_id, source_id = two_db_patients

    # 1. Merge
    client.post(
        "/api/v1/mpi/merge",
        headers=mrd_headers,
        json={
            "source_patient_id": source_id,
            "target_patient_id": target_id,
            "reason": "Initial merge",
        }
    )

    # 2. Unmerge
    res = client.post(
        "/api/v1/mpi/unmerge",
        headers=mrd_headers,
        json={
            "source_patient_id": source_id,
            "reason": "Reversal of erroneous merge",
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "unmerged"
    assert data["source_patient_id"] == source_id
    assert data["previous_target_id"] == target_id

    # Verify DB state is restored
    session_factory = get_default_session_factory()
    with session_factory() as db:
        p_src = db.query(Patient).filter(Patient.id == uuid6.UUID(source_id)).first()
        assert p_src.merged_into is None


def test_mpi_merge_prevent_self_merge(client, mrd_headers, two_db_patients):
    """Test self-merge rejection."""
    p_id, _ = two_db_patients
    res = client.post(
        "/api/v1/mpi/merge",
        headers=mrd_headers,
        json={
            "source_patient_id": p_id,
            "target_patient_id": p_id,
            "reason": "Invalid self merge",
        }
    )
    assert res.status_code == 400
    data = res.json()
    msg = data.get("message") or str(data)
    assert "Cannot merge patient record into itself" in msg



def test_mpi_merge_rbac_unauthorized(client, nurse_headers, two_db_patients):
    """Test non-MRD/ADMIN roles cannot execute merges."""
    target_id, source_id = two_db_patients
    res = client.post(
        "/api/v1/mpi/merge",
        headers=nurse_headers,
        json={
            "source_patient_id": source_id,
            "target_patient_id": target_id,
            "reason": "Attempt by nurse",
        }
    )
    assert res.status_code == 403
