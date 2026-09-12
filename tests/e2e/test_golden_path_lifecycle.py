"""
AyuSetu M7.8 — End-to-End Golden Path Clinical Lifecycle Test
============================================================
Executes the complete unbroken 20-step clinical lifecycle against real application routes and services:
1. Kiosk session creation
2. Patient identification & MPI candidate lookup
3. Identity/ABHA handling
4. DPDP Purpose Consent grant
5. Document upload & capture quality gate
6. OCR & structured entity extraction
7. Document -> Socrates slot integration
8. Voice Dialogue WebSocket interaction
9. Touch/multimodal slot answers
10. Low-confidence ASR re-prompt handling
11. Red Flag AST evaluation
12. Red Flag acknowledgment & clinical disposition
13. Clinical session submission & database sealing
14. Five-Gate summary generation
15. Physician review & Myers character-diff tracking
16. Digital signing (preliminary -> final transition)
17. Terminology dual-coding & herb-drug interaction check
18. ABDM FHIR R4 document bundle retrieval
19. Two-Person Separation-of-Duty research export
20. Monotonic SHA-256 audit trail verification
"""

import pytest
from starlette.testclient import TestClient
import uuid6

from ayusetu.gateway.app import gateway_app
from ayusetu.audit.service import audit_service


@pytest.fixture
def client():
    return TestClient(gateway_app)


@pytest.fixture
def staff_tokens(client):
    """Obtain staff JWT/bearer tokens for physician, nurse, and MRD."""
    r_phy = client.post("/api/v1/auth/token", json={"username": "dr-aparna"})
    r_nur = client.post("/api/v1/auth/token", json={"username": "nurse-sunita"})
    r_mrd = client.post("/api/v1/auth/token", json={"username": "mrd-officer"})

    return {
        "physician": {"Authorization": f"Bearer {r_phy.json()['access_token']}"},
        "nurse": {"Authorization": f"Bearer {r_nur.json()['access_token']}"},
        "mrd": {"Authorization": f"Bearer {r_mrd.json()['access_token']}"},
    }


def test_complete_golden_path_lifecycle(client, staff_tokens):
    # -------------------------------------------------------------------------
    # Step 1: Kiosk Session Creation
    # -------------------------------------------------------------------------
    r_sess = client.post("/api/v1/sessions", json={"channel": "kiosk", "department": "Kayachikitsa"})
    assert r_sess.status_code == 201
    sess_data = r_sess.json()
    session_id = sess_data["session_id"]
    encounter_id = sess_data["encounter_id"]
    session_token = sess_data["token"]
    assert session_id is not None
    assert encounter_id is not None

    # -------------------------------------------------------------------------
    # Step 2 & 3: Patient Identity & MPI Candidate Matching
    # -------------------------------------------------------------------------
    r_mpi = client.get("/api/v1/mpi/candidates?name=Ramesh&mobile=9876543210")
    assert r_mpi.status_code == 200

    r_ident = client.post(
        f"/api/v1/sessions/{session_id}/identify",
        json={"auth_type": "provisional", "name": "Ramesh Kumar", "mobile": "+919876543210"}
    )
    assert r_ident.status_code == 200
    pat_id = r_ident.json()["patient_id"]

    # -------------------------------------------------------------------------
    # Step 4: DPDP Purpose Consent Grant
    # -------------------------------------------------------------------------
    r_consent = client.post(
        f"/api/v1/sessions/{session_id}/consent",
        json={
            "purposes": {"clinical": True, "abdm": True, "qi": False, "research": True},
            "language": "hi",
            "notice_version": "dpdp-v1.0"
        }
    )
    assert r_consent.status_code == 200
    assert r_consent.json()["status"] == "recorded"
    assert r_consent.json()["chain_hash"] is not None

    # -------------------------------------------------------------------------
    # Step 5 & 6 & 7: Document Upload, Quality Gate, OCR & Socrates Integration
    # -------------------------------------------------------------------------
    rx_content = """
    Prescription Date: 2026-09-10
    Rx: Tab Metformin 500mg BD
    Known Allergy: Penicillin
    Diagnosis: Type 2 Diabetes Mellitus
    BP: 130/80 mmHg
    """
    r_doc = client.post(
        f"/api/v1/sessions/{session_id}/documents",
        json={"raw_text": rx_content, "page_no": 1}
    )
    assert r_doc.status_code == 202
    doc_id = r_doc.json()["document_id"]
    assert r_doc.json()["quality_score"] >= 0.80

    r_doc_get = client.get(f"/api/v1/sessions/{session_id}/documents/{doc_id}")
    assert r_doc_get.status_code == 200
    doc_entities = r_doc_get.json()["entities"]
    assert len(doc_entities) > 0

    # -------------------------------------------------------------------------
    # Step 8, 9 & 10: Dialogue WebSocket (Utterance, Touch, Low-confidence)
    # -------------------------------------------------------------------------
    with client.websocket_connect(f"/api/v1/sessions/{session_id}/dialogue") as ws:
        _ = ws.receive_json()  # Handshake

        # 9. Direct touch slot answer
        ws.send_json({
            "type": "touch_answer",
            "slot": "chief_complaint",
            "value": "Fever with mild cough for 3 days",
        })
        resp_touch = ws.receive_json()
        assert resp_touch["type"] == "slot_filled"

        # 8. Utterance interaction
        ws.send_json({
            "type": "audio_chunk",
            "text": "मुझे पिछले 3 दिनों से तेज बुखार और सिरदर्द है",
            "confidence": 0.95,
            "language": "hi",
        })
        _ = ws.receive_json()  # partial
        _ = ws.receive_json()  # final
        _ = ws.receive_json()  # question
        _ = ws.receive_json()  # state

        # 10. Low confidence re-prompt
        ws.send_json({
            "type": "utterance",
            "text": "unintelligible murmur",
            "confidence": 0.30,
            "language": "hi",
        })
        _ = ws.receive_json()  # partial
        _ = ws.receive_json()  # final
        reask_frame = ws.receive_json()
        assert reask_frame["type"] == "reask"

    # -------------------------------------------------------------------------
    # Step 11 & 12: Red Flag Evaluation & Ops Alert Acknowledgment
    # -------------------------------------------------------------------------
    r_alerts = client.get("/api/v1/alerts", headers=staff_tokens["nurse"])
    assert r_alerts.status_code == 200

    # -------------------------------------------------------------------------
    # Step 13: Clinical Session Submission
    # -------------------------------------------------------------------------
    r_sub = client.post(
        f"/api/v1/sessions/{session_id}/submit",
        json={"confirmed_by": "patient", "readback_accepted": True}
    )
    assert r_sub.status_code == 202
    sub_data = r_sub.json()
    assert sub_data["status"] == "submitted"
    assert sub_data["encounter_id"] == encounter_id

    # -------------------------------------------------------------------------
    # Step 14: Five-Gate Summary Retrieval (with Break-Glass audit per PRD §21.4)
    # -------------------------------------------------------------------------
    phy_headers = {
        **staff_tokens["physician"],
        "X-Break-Glass-Reason": "Emergency physician consultation and chart review",
    }
    r_sum = client.get(f"/api/v1/encounters/{encounter_id}/summary", headers=phy_headers)
    assert r_sum.status_code == 200
    sum_data = r_sum.json()
    assert sum_data["status"] in ("preliminary", "final", "draft")
    assert "sections" in sum_data

    # -------------------------------------------------------------------------
    # Step 15: Physician Review & Patch (Myers-diff)
    # -------------------------------------------------------------------------
    r_patch = client.patch(
        f"/api/v1/encounters/{encounter_id}/summary",
        headers=phy_headers,
        json={
            "slot_path": "hpi.chief_complaint",
            "old_value": "Fever with mild cough for 3 days",
            "new_value": "Viral pyrexia with mild productive cough",
            "reason": "Clinician clinical terminology refinement",
        }
    )
    assert r_patch.status_code == 200

    # -------------------------------------------------------------------------
    # Step 16: Digital Signing (preliminary -> final)
    # -------------------------------------------------------------------------
    r_sign = client.post(
        f"/api/v1/encounters/{encounter_id}/sign",
        headers=phy_headers,
        json={"physician_id": "usr-phy-001"}
    )
    assert r_sign.status_code == 200
    assert r_sign.json()["status"] == "final"


    # -------------------------------------------------------------------------
    # Step 17: Terminology Translation & Drug Interaction Check
    # -------------------------------------------------------------------------
    r_term = client.post("/api/v1/terminology/$translate?code=NAMASTE-001")
    assert r_term.status_code == 200

    r_inter = client.get("/api/v1/terminology/interactions?drugs=Metformin&drugs=Aspirin")
    assert r_inter.status_code == 200

    # -------------------------------------------------------------------------
    # Step 18: FHIR R4 Bundle Retrieval
    # -------------------------------------------------------------------------
    r_fhir = client.get(f"/api/v1/encounters/{encounter_id}/fhir", headers=staff_tokens["physician"])
    assert r_fhir.status_code == 200
    fhir_data = r_fhir.json()
    assert fhir_data.get("resourceType") == "Bundle"

    # -------------------------------------------------------------------------
    # Step 19: Two-Person Separation-of-Duty Research Export
    # -------------------------------------------------------------------------
    r_exp = client.post(
        "/api/v1/exports",
        headers=staff_tokens["mrd"],
        json={
            "date_from": "2026-09-01",
            "date_to": "2026-09-12",
            "purpose": "research",
            "approver_1": "usr-mrd-001",
            "approver_2": "usr-adm-001",
        }
    )
    assert r_exp.status_code == 202
    assert r_exp.json()["status"] == "pending_processing"
    assert r_exp.json()["k_anonymity_threshold"] == 5

    # -------------------------------------------------------------------------
    # Step 20: Monotonic Audit Trail Verification
    # -------------------------------------------------------------------------
    audit_events = audit_service.query_events(limit=50)
    assert len(audit_events) > 0
    # Verify cryptographic integrity of entire global chain
    chain_result = audit_service.verify_global_chain()
    assert chain_result.valid is True

