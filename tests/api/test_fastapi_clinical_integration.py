import io
import tempfile
import numpy as np
import soundfile as sf
import pytest
from fastapi.testclient import TestClient

import ayusetu.api.fastapi_voice as api
from ayusetu.ai.voice.pipeline.voice_pipeline import VoicePipeline, ConversationSession
from contracts.asr_output import ASROutput

client = TestClient(api.app)


def _create_dummy_wav_bytes():
    sr = 16000
    t = np.linspace(0, 0.5, int(sr * 0.5), False)
    tone = 0.5 * np.sin(2 * np.pi * 440 * t)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        sf.write(tmp.name, tone, sr, format="WAV")
        data = open(tmp.name, "rb").read()
    return data


# Mock pipeline to avoid running real Whisper/Chatterbox during API unit tests
class MockPipeline(VoicePipeline):
    def run(self, audio_path: str, session_id: str = None):
        session = self.get_session(session_id) if session_id else None
        # Return red flag trigger if session has chest pain in state or mock
        state = session.state if session else self._dialogue_engine.initialize()
        response_text = self._dialogue_engine.step(
            ASROutput(text="I have severe chest pain", language="en", confidence=0.9), state
        )
        context = {s.value if hasattr(s, "value") else str(s): str(v) for s, v in state.collected_info.items()}
        red_flags = self._red_flag_engine.evaluate(
            encounter_id=session_id or "ephemeral",
            context=context,
            utterance="I have severe chest pain",
        )
        if session and red_flags:
            session.red_flag_events.extend(red_flags)

        return {
            "transcribed_text": "I have severe chest pain",
            "detected_language": "en",
            "asr_confidence": 0.95,
            "low_confidence": False,
            "response_text": response_text,
            "response_audio": np.zeros(16000, dtype=np.float32),
            "response_sample_rate": 16000,
            "response_duration": 1.0,
            "session_id": session_id,
            "red_flags": [rf.model_dump(mode="json") for rf in red_flags],
        }


@pytest.fixture(autouse=True)
def setup_mock_pipeline():
    orig = api.voice_pipeline
    api.voice_pipeline = VoicePipeline()
    yield
    api.voice_pipeline = orig


class TestFastAPIClinicalIntegration:
    def test_normal_clinical_turn_and_red_flags(self):
        # Create session
        res = client.post("/sessions")
        assert res.status_code == 200
        sid = res.json()["session_id"]

        # Run turn with chest pain (red flag)
        wav_bytes = _create_dummy_wav_bytes()
        files = {"audio": ("test.wav", wav_bytes, "audio/wav")}

        # Patch transcribe inside voice_pipeline
        high_conf = ASROutput(text="I have severe chest pain", language="en", confidence=0.92)
        with pytest.MonkeyPatch.context() as m:
            m.setattr("ayusetu.ai.voice.pipeline.voice_pipeline.transcribe", lambda path: high_conf)
            response = client.post(f"/sessions/{sid}/turn", files=files)

        assert response.status_code == 200
        data = response.json()
        assert data["transcribed_text"] == "I have severe chest pain"
        assert "red_flags" in data
        assert len(data["red_flags"]) >= 1
        assert data["red_flags"][0]["category"] == "cardiac"

    def test_session_isolation_red_flags_and_documents(self):
        # Session A: red flags and document upload
        res_a = client.post("/sessions")
        sid_a = res_a.json()["session_id"]

        doc_bytes = b"HbA1c: 9.5% (High 4.0-5.6), Metformin 500mg"
        files_a = {"document": ("lab.txt", doc_bytes, "text/plain")}
        res_doc_a = client.post(f"/sessions/{sid_a}/documents", files=files_a)
        assert res_doc_a.status_code == 200
        assert res_doc_a.json()["extracted_entities_count"] >= 1

        # Session B: completely clean
        res_b = client.post("/sessions")
        sid_b = res_b.json()["session_id"]
        sess_b = api.voice_pipeline.get_session(sid_b)

        assert sess_b.document_entities == []
        assert sess_b.red_flag_events == []

    def test_generate_summary_without_documents(self):
        res = client.post("/sessions")
        sid = res.json()["session_id"]
        sess = api.voice_pipeline.get_session(sid)
        sess.state.collected_info = {"chief_complaint": "headache", "duration": "2 days"}

        res_sum = client.post(f"/sessions/{sid}/summary")
        assert res_sum.status_code == 200
        summary = res_sum.json()
        assert summary["encounter_id"] == sid
        assert summary["status"] == "preliminary"
        assert summary["chief_complaint"] == "headache"

    def test_generate_summary_with_documents_and_intelligence_alerts(self):
        res = client.post("/sessions")
        sid = res.json()["session_id"]

        # Upload document with lab and herb/drug
        doc_bytes = b"Glucose: 250 mg/dL (High 70-99). Patient takes Guggulu and Metformin."
        files = {"document": ("record.txt", doc_bytes, "text/plain")}
        res_doc = client.post(f"/sessions/{sid}/documents", files=files)
        assert res_doc.status_code == 200

        sess = api.voice_pipeline.get_session(sid)
        sess.state.collected_info = {"chief_complaint": "diabetes check", "medications": "Guggulu and Metformin"}

        res_sum = client.post(f"/sessions/{sid}/summary")
        assert res_sum.status_code == 200
        summary = res_sum.json()
        assert summary["encounter_id"] == sid
        assert len(summary["alerts"]) >= 1

    def test_physician_review_sign_off_edit_reject(self):
        res = client.post("/sessions")
        sid = res.json()["session_id"]
        sess = api.voice_pipeline.get_session(sid)
        sess.state.collected_info = {"chief_complaint": "chest pain"}

        # 1. Generate summary
        res_sum = client.post(f"/sessions/{sid}/summary")
        assert res_sum.status_code == 200

        # 2. Edit summary
        res_edit = client.put(
            f"/sessions/{sid}/summary/edit",
            json={
                "slot_path": "chief_complaint",
                "new_value": "severe angina",
                "reason": "more specific terminology",
                "physician_id": "dr_smith",
            },
        )
        assert res_edit.status_code == 200
        assert res_edit.json()["edit_record"]["old_value"] == "chest pain"
        assert res_edit.json()["edit_record"]["new_value"] == "severe angina"

        # 3. Sign-off summary
        res_sign = client.post(
            f"/sessions/{sid}/summary/sign-off",
            json={"physician_id": "dr_smith"},
        )
        assert res_sign.status_code == 200
        assert res_sign.json()["status"] == "final"
        assert res_sign.json()["signed_by"] == "dr_smith"

        # 4. Cannot edit after signing
        res_edit_signed = client.put(
            f"/sessions/{sid}/summary/edit",
            json={
                "slot_path": "chief_complaint",
                "new_value": "test",
                "reason": "test",
                "physician_id": "dr_smith",
            },
        )
        assert res_edit_signed.status_code == 400
