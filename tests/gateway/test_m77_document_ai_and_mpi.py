"""
Unit and Integration Tests for Milestone M7.7 — Document AI and MPI Integration
================================================================================
Validates:
1. Document upload and quality scoring ("reject before accept") per PRD §11.1
2. OCR provider execution and structured entity extraction per PRD §11.2
3. Confidence propagation and needs_review discipline (<0.80)
4. Document retrieval and deterministic repeated lookups
5. Master Patient Index (MPI) exact, partial, no-match demographic searches per PRD §4 & §22.5
6. Zero-diff boundary integrity on protected clinical/auth/consent/audit modules
"""

import os
import uuid
import pytest
from fastapi.testclient import TestClient

from ayusetu.gateway.app import gateway_app
from ayusetu.common.session_cache import SessionCache
from ayusetu.clinical.document_service import document_service
from ayusetu.clinical.mpi_service import mpi_service


@pytest.fixture(autouse=True)
def reset_document_store():
    document_service.clear()
    yield
    document_service.clear()


@pytest.fixture
def client():
    return TestClient(gateway_app)



@pytest.fixture
def cache():
    return SessionCache()


# ---------------------------------------------------------------------------
# 1. Successful Document Upload & Entity Extraction
# ---------------------------------------------------------------------------
def test_successful_document_upload_and_extraction(client, cache):
    enc_id = uuid.uuid4()
    sess = cache.create_session(encounter_id=enc_id)
    sess_id = sess["session_id"]

    prescription_text = "Tab. Metformin 500mg 1-0-1 x 30 days\nBP: 120/80 mmHg\nAllergy to Penicillin - rash"
    resp = client.post(
        f"/api/v1/sessions/{sess_id}/documents",
        json={"raw_text": prescription_text, "page_no": 1},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "document_id" in data
    assert data["session_id"] == sess_id
    assert data["quality_score"] >= 0.80
    assert data["ocr_status"] == "completed"
    assert data["entities_count"] >= 3


# ---------------------------------------------------------------------------
# 2. Session Not Found Handling (401 / 404)
# ---------------------------------------------------------------------------
def test_document_upload_session_not_found(client):
    fake_sess_id = str(uuid.uuid4())
    resp = client.post(
        f"/api/v1/sessions/{fake_sess_id}/documents",
        json={"raw_text": "Tab. Paracetamol 500mg OD"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3. Capture Quality Rejection ("Reject Before Accept" PRD §11.1)
# ---------------------------------------------------------------------------
def test_capture_quality_blur_rejection(client, cache):
    enc_id = uuid.uuid4()
    sess = cache.create_session(encounter_id=enc_id)
    sess_id = sess["session_id"]

    # Uniform grey grid (no edges -> low blur score < 0.35)
    blurry_grid = [[128] * 64 for _ in range(64)]
    resp = client.post(
        f"/api/v1/sessions/{sess_id}/documents",
        json={"grid": blurry_grid, "raw_text": "Unreadable blurry prescription"},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "DOC_QUALITY_REJECTED"
    assert "blurry" in data["error"]["message"].lower()


# ---------------------------------------------------------------------------
# 4. OCR Execution and Text Preservation
# ---------------------------------------------------------------------------
def test_ocr_text_preservation(client, cache):
    enc_id = uuid.uuid4()
    sess = cache.create_session(encounter_id=enc_id)
    sess_id = sess["session_id"]

    lab_text = "Hemoglobin: 13.5 g/dL (12.0-15.5)\nFBS 95 mg/dL (70-100)"
    resp = client.post(
        f"/api/v1/sessions/{sess_id}/documents",
        json={"raw_text": lab_text, "page_no": 1},
    )
    assert resp.status_code == 202
    doc_id = resp.json()["document_id"]

    get_resp = client.get(f"/api/v1/sessions/{sess_id}/documents/{doc_id}")
    assert get_resp.status_code == 200
    doc_data = get_resp.json()
    assert len(doc_data["ocr"]) > 0
    assert "Hemoglobin" in doc_data["ocr"][0]["raw_text"]


# ---------------------------------------------------------------------------
# 5. Structured Entity Extraction (Meds, Vitals, Labs, Allergies, Diagnoses)
# ---------------------------------------------------------------------------
def test_structured_entity_extraction_types(client, cache):
    enc_id = uuid.uuid4()
    sess = cache.create_session(encounter_id=enc_id)
    sess_id = sess["session_id"]

    composite_text = (
        "Tab. Amlodipine 5mg OD\n"
        "Pulse: 72/min Temp: 98.6 F\n"
        "Serum Creatinine: 1.1 mg/dL (0.6-1.2)\n"
        "Allergy: Sulfa - anaphylaxis\n"
        "Dx: Essential Hypertension (I10)"
    )
    upload_resp = client.post(
        f"/api/v1/sessions/{sess_id}/documents",
        json={"raw_text": composite_text},
    )
    doc_id = upload_resp.json()["document_id"]

    get_resp = client.get(f"/api/v1/sessions/{sess_id}/documents/{doc_id}")
    assert get_resp.status_code == 200
    entities = get_resp.json()["entities"]

    entity_types = {e["entity_type"] for e in entities}
    assert "medication" in entity_types
    assert "vital_sign" in entity_types
    assert "lab_result" in entity_types
    assert "allergy" in entity_types
    assert "diagnosis" in entity_types



# ---------------------------------------------------------------------------
# 6 & 7. Confidence Propagation & needs_review Behavior Below 0.80
# ---------------------------------------------------------------------------
def test_confidence_and_needs_review_discipline(client, cache):
    enc_id = uuid.uuid4()
    sess = cache.create_session(encounter_id=enc_id)
    sess_id = sess["session_id"]

    # OCR text with ambiguous entity
    text = "Tab. Metformin 500mg 1-0-1\nSuspected Mild Gastritis"
    upload_resp = client.post(
        f"/api/v1/sessions/{sess_id}/documents",
        json={"raw_text": text},
    )
    doc_id = upload_resp.json()["document_id"]

    get_resp = client.get(f"/api/v1/sessions/{sess_id}/documents/{doc_id}")
    entities = get_resp.json()["entities"]

    for ent in entities:
        assert "confidence" in ent
        assert 0.0 <= ent["confidence"] <= 1.0
        if ent["confidence"] < 0.80:
            assert ent["needs_review"] is True
        else:
            assert ent["needs_review"] is False


# ---------------------------------------------------------------------------
# 8 & 9. Document Retrieval & Deterministic Repeated Retrieval
# ---------------------------------------------------------------------------
def test_document_retrieval_and_idempotency(client, cache):
    enc_id = uuid.uuid4()
    sess = cache.create_session(encounter_id=enc_id)
    sess_id = sess["session_id"]

    text = "Tab. Pantocid 40mg OD"
    upload_resp = client.post(f"/api/v1/sessions/{sess_id}/documents", json={"raw_text": text})
    doc_id = upload_resp.json()["document_id"]

    resp1 = client.get(f"/api/v1/sessions/{sess_id}/documents/{doc_id}")
    resp2 = client.get(f"/api/v1/sessions/{sess_id}/documents/{doc_id}")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()

    # Missing document ID -> 404
    missing_resp = client.get(f"/api/v1/sessions/{sess_id}/documents/{uuid.uuid4()}")
    assert missing_resp.status_code == 404


# ---------------------------------------------------------------------------
# 10. MPI Exact Demographic Match
# ---------------------------------------------------------------------------
def test_mpi_exact_match(client):
    resp = client.get(
        "/api/v1/mpi/candidates",
        params={"name": "Kamala Devi", "dob": "1963-05-12", "mobile": "+919876543210"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    top_candidate = data["candidates"][0]
    assert "Kamala Devi" in top_candidate["name"]
    assert top_candidate["match_confidence"] >= 0.90


# ---------------------------------------------------------------------------
# 11. MPI Partial / Probabilistic Match
# ---------------------------------------------------------------------------
def test_mpi_partial_probabilistic_match(client):
    # Search with only name token or year
    resp = client.get(
        "/api/v1/mpi/candidates",
        params={"name": "Rakesh", "dob": "1998-01-01"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    matched_names = [c["name"] for c in data["candidates"]]
    assert any("Rakesh" in n for n in matched_names)


# ---------------------------------------------------------------------------
# 12. MPI No Match Safe Empty Return (No Fabrication)
# ---------------------------------------------------------------------------
def test_mpi_no_match_returns_empty_list(client):
    resp = client.get(
        "/api/v1/mpi/candidates",
        params={"name": "Nonexistent Person XYZ 999", "dob": "1910-01-01", "mobile": "+910000000000"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["candidates"] == []


# ---------------------------------------------------------------------------
# 13. MPI Malformed / Empty Input Handling
# ---------------------------------------------------------------------------
def test_mpi_empty_input_handling(client):
    resp = client.get("/api/v1/mpi/candidates")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["candidates"] == []


# ---------------------------------------------------------------------------
# 14. RBAC & Security Enforcement on Document / MPI Endpoints
# ---------------------------------------------------------------------------
def test_rbac_security_on_endpoints(client, cache):
    # Invalid session token is rejected
    resp = client.get(
        f"/api/v1/sessions/{uuid.uuid4()}/documents/fake-doc",
        headers={"Authorization": "Bearer invalid-token-xyz"},
    )
    assert resp.status_code in (401, 404)


# ---------------------------------------------------------------------------
# 15. Protected Boundary Zero-Diff Verification
# ---------------------------------------------------------------------------
def test_protected_boundary_zero_diff():
    import subprocess
    cmd = [
        "git", "diff", "--",
        "src/ayusetu/api/fastapi_voice.py",
        "src/ayusetu/api/main.py",
        "src/ayusetu/gateway/auth/",
        "src/ayusetu/consent/",
        "src/ayusetu/audit/",
        "src/ayusetu/clinical/models.py",
        "src/ayusetu/clinical/repository.py",
        "src/ayusetu/clinical/service.py",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0
    assert res.stdout.strip() == "", f"Protected boundaries modified: {res.stdout}"
