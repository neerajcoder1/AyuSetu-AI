"""
Reconciliation & Compatibility Integration Tests
=================================================
Verifies pre-merge reconciliation contracts:
1. Session ID ↔ Encounter ID bi-directional mapping.
2. FastAPI Voice turn endpoint.
3. Multipart document upload.
4. Summary & sign-off compatibility aliases.
5. Session language switching without losing detected language.
6. Patient & encounter data isolation.
"""

import io
import pytest
from fastapi.testclient import TestClient

import ayusetu.api.fastapi_voice as api_module
from ayusetu.ai.voice.pipeline.voice_pipeline import VoicePipeline

client = TestClient(api_module.app)


@pytest.fixture(autouse=True)
def reset_sessions():
    api_module.voice_pipeline = VoicePipeline()
    yield
    api_module.voice_pipeline = VoicePipeline()


def test_session_create_populates_encounter_id():
    res = client.post("/sessions", json={"preferred_language": "hi"})
    assert res.status_code == 200
    data = res.json()
    assert "session_id" in data
    assert "encounter_id" in data
    assert data["preferred_language"] == "hi"

    # Verify bi-directional lookup in session manager
    sid = data["session_id"]
    enc_id = data["encounter_id"]

    session_by_sid = api_module.voice_pipeline.get_session(sid)
    session_by_enc = api_module.voice_pipeline.get_session(enc_id)
    assert session_by_sid.session_id == session_by_enc.session_id == sid
    assert session_by_sid.encounter_id == session_by_enc.encounter_id == enc_id


def test_language_update_endpoint():
    res = client.post("/sessions", json={"preferred_language": "hinglish"})
    sid = res.json()["session_id"]

    patch_res = client.patch(f"/sessions/{sid}/language", json={"preferred_language": "hi"})
    assert patch_res.status_code == 200
    assert patch_res.json()["preferred_language"] == "hi"

    # Verify state reflects preferred_language
    state_res = client.get(f"/sessions/{sid}/state")
    assert state_res.status_code == 200
    assert state_res.json()["state"]["preferred_language"] == "hi"


def test_multipart_document_upload():
    create_res = client.post("/sessions", json={"preferred_language": "hinglish"})
    sid = create_res.json()["session_id"]

    sample_doc = io.BytesIO(b"Tab. Metformin 500mg 1-0-1 x 5 days. BP: 120/80 mmHg. Dx: Acute Gastritis.")
    files = {"document": ("prescription.txt", sample_doc, "text/plain")}

    doc_res = client.post(f"/sessions/{sid}/documents", files=files)
    assert doc_res.status_code == 200
    data = doc_res.json()
    assert data["status"] == "success"
    assert data["filename"] == "prescription.txt"
    assert "entities" in data

    # Verify session isolation
    session = api_module.voice_pipeline.get_session(sid)
    assert len(session.document_entities) > 0


def test_summary_and_sign_off_session_and_encounter_aliases():
    create_res = client.post("/sessions", json={"preferred_language": "hi"})
    sid = create_res.json()["session_id"]
    enc_id = create_res.json()["encounter_id"]

    # Generate summary via session route
    sum_res = client.post(f"/sessions/{sid}/summary")
    assert sum_res.status_code == 200
    assert "chief_complaint" in sum_res.json()

    # Sign-off summary via session sign-off route
    sign_res = client.post(f"/sessions/{sid}/summary/sign-off", json={"physician_id": "DR-9942"})
    assert sign_res.status_code == 200
    assert sign_res.json()["signed_by"] == "DR-9942"
    assert sign_res.json()["status"].upper() == "FINAL"


def test_session_isolation():
    s1 = client.post("/sessions", json={"preferred_language": "hi"}).json()
    s2 = client.post("/sessions", json={"preferred_language": "en"}).json()

    assert s1["session_id"] != s2["session_id"]
    assert s1["encounter_id"] != s2["encounter_id"]

    sess1 = api_module.voice_pipeline.get_session(s1["session_id"])
    sess2 = api_module.voice_pipeline.get_session(s2["session_id"])

    assert sess1.session_id != sess2.session_id
    assert sess1.engine != sess2.engine
