import io
import json
import base64
import tempfile
import numpy as np
import soundfile as sf
import pytest
from fastapi.testclient import TestClient

import ayusetu.api.fastapi_voice as api

client = TestClient(api.app)

# Helper DummyPipeline to replace the real one during tests
class DummyPipeline:
    def __init__(self):
        self._sessions = {}

    def create_session(self) -> str:
        session_id = "dummy-session-id"
        self._sessions[session_id] = {}
        return session_id

    def get_state(self, session_id: str):
        if session_id not in self._sessions:
            raise KeyError
        # Return a minimal DialogueState compatible dict (Pydantic will handle)
        from contracts.dialogue import DialogueState
        return DialogueState()

    def end_session(self, session_id: str):
        if session_id not in self._sessions:
            raise KeyError
        del self._sessions[session_id]

    def get_session(self, session_id: str):
        if session_id not in self._sessions:
            raise KeyError
        class MockSession:
            def __init__(self, s_id):
                self.session_id = s_id
                from contracts.dialogue import DialogueState
                self.state = DialogueState()
                self.red_flag_events = []
                self.document_entities = []
                self.summary = None
        return MockSession(session_id)

    def run(self, audio_path: str, session_id: str = None):
        # Return a deterministic result regardless of input audio
        return {
            "transcribed_text": "hello",
            "detected_language": "en",
            "asr_confidence": 0.95,
            "low_confidence": False,
            "response_text": "hi there",
            "response_audio": np.zeros(16000, dtype=np.float32),  # 1 sec dummy audio
            "response_sample_rate": 16000,
            "response_duration": 1.0,
            "session_id": session_id,
        }

# Patch the global pipeline in the api module
api.voice_pipeline = DummyPipeline()

def _create_dummy_wav_bytes():
    # 0.5 second mono wav at 16000 Hz
    sr = 16000
    t = np.linspace(0, 0.5, int(sr * 0.5), False)
    tone = 0.5 * np.sin(2 * np.pi * 440 * t)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        sf.write(tmp.name, tone, sr, format="WAV")
        data = open(tmp.name, "rb").read()
    return data

def test_create_session():
    response = client.post("/sessions")
    assert response.status_code == 200
    payload = response.json()
    assert "session_id" in payload
    assert payload["session_id"] == "dummy-session-id"

def test_valid_turn():
    wav_bytes = _create_dummy_wav_bytes()
    files = {"audio": ("test.wav", wav_bytes, "audio/wav")}
    response = client.post(f"/sessions/dummy-session-id/turn", files=files)
    assert response.status_code == 200
    data = response.json()
    # Basic fields
    assert data["transcribed_text"] == "hello"
    assert data["response_text"] == "hi there"
    # Audio must be base64 encoded and decode to a valid wav file
    wav_b64 = data["response_audio"]
    wav_raw = base64.b64decode(wav_b64)
    # Verify that soundfile can read it
    with io.BytesIO(wav_raw) as f:
        audio, sr = sf.read(f)
    assert sr == 16000
    assert audio.shape[0] > 0

def test_missing_audio():
    response = client.post("/sessions/dummy-session-id/turn", files={})
    # FastAPI returns 422 Unprocessable Entity when required file missing
    assert response.status_code == 422

def test_invalid_session_turn():
    wav_bytes = _create_dummy_wav_bytes()
    files = {"audio": ("test.wav", wav_bytes, "audio/wav")}
    response = client.post("/sessions/unknown-session/turn", files=files)
    assert response.status_code == 404

def test_get_state():
    response = client.get("/sessions/dummy-session-id/state")
    assert response.status_code == 200
    data = response.json()
    # The response should contain a "state" key with DialogueState fields
    assert "state" in data
    # Basic sanity: ensure the returned object is a dict (DialogueState serializes to dict)
    assert isinstance(data["state"], dict)

def test_delete_session():
    # Delete existing session
    response = client.delete("/sessions/dummy-session-id")
    assert response.status_code == 204
    # Subsequent delete should 404
    response2 = client.delete("/sessions/dummy-session-id")
    assert response2.status_code == 404

def test_low_confidence_turn(monkeypatch):
    # Patch run to return low confidence and no audio
    def low_conf_run(self, audio_path: str, session_id: str = None):
        return {
            "transcribed_text": "garbled",
            "detected_language": "en",
            "asr_confidence": 0.3,
            "low_confidence": True,
            "response_text": None,
            "response_audio": None,
            "response_sample_rate": None,
            "response_duration": None,
            "session_id": session_id,
        }
    monkeypatch.setattr(api.voice_pipeline, "run", low_conf_run.__get__(api.voice_pipeline, type(api.voice_pipeline)))
    # Re‑create session for this test
    client.post("/sessions")
    wav_bytes = _create_dummy_wav_bytes()
    files = {"audio": ("test.wav", wav_bytes, "audio/wav")}
    response = client.post(f"/sessions/dummy-session-id/turn", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["low_confidence"] is True
    assert data["response_audio"] is None
    assert data["response_text"] is None

def test_cors_headers():
    response = client.options("/sessions", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") in ["*", "http://localhost:5173"]

def test_get_timeline():
    # Re-create session
    client.post("/sessions")
    response = client.get("/sessions/dummy-session-id/timeline")
    assert response.status_code == 200
    events = response.json()
    assert isinstance(events, list)
    assert len(events) > 0
    assert events[0]["event_type"] == "encounter"

def test_get_timeline_not_found():
    response = client.get("/sessions/nonexistent-session/timeline")
    assert response.status_code == 404

