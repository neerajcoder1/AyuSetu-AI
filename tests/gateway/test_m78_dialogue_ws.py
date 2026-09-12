"""
Tests for M7.8 Dialogue WebSocket Gateway Endpoint
=================================================
Verifies WS /api/v1/sessions/{id}/dialogue per PRD v3 §8.2, §8.5, §22.2, and packages/schemas/dialogue_ws.json.
"""

import json
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ayusetu.gateway.app import gateway_app
from ayusetu.common.session_cache import SessionCache
import uuid6


@pytest.fixture
def client():
    return TestClient(gateway_app)


@pytest.fixture
def active_session():
    cache = SessionCache()
    sess_id = str(uuid6.uuid7())
    enc_id = str(uuid6.uuid7())
    sess = cache.create_session(encounter_id=enc_id, session_id=sess_id)
    return sess


def test_ws_dialogue_expired_session_rejection(client):
    """Test connecting to WebSocket with a non-existent or expired session."""
    non_existent_id = "00000000-0000-0000-0000-000000000000"
    with client.websocket_connect(f"/api/v1/sessions/{non_existent_id}/dialogue") as ws_conn:
        data = ws_conn.receive_json()
        assert data["type"] == "error"
        assert data["error_code"] == "SESSION_EXPIRED"



def test_ws_dialogue_successful_handshake(client, active_session):
    """Test initial connection handshake emits state message."""
    sess_id = active_session["session_id"]
    with client.websocket_connect(f"/api/v1/sessions/{sess_id}/dialogue") as ws:
        initial = ws.receive_json()
        assert initial["type"] == "state"
        assert initial["session_id"] == sess_id
        assert initial["status"] == "connected"


def test_ws_dialogue_touch_answer(client, active_session):
    """Test direct touch/PWA answer updates slot state."""
    sess_id = active_session["session_id"]
    with client.websocket_connect(f"/api/v1/sessions/{sess_id}/dialogue") as ws:
        _ = ws.receive_json()  # Handshake

        # Send touch answer
        ws.send_json({
            "type": "touch_answer",
            "slot": "chief_complaint",
            "value": "Severe headache for 3 days",
        })

        resp = ws.receive_json()
        assert resp["type"] == "slot_filled"
        assert resp["slot"] == "chief_complaint"
        assert resp["value"] == "Severe headache for 3 days"
        assert resp["source"] == "touch"


def test_ws_dialogue_valid_utterance_flow(client, active_session):
    """Test standard utterance flow through ASR and dialogue engine."""
    sess_id = active_session["session_id"]
    with client.websocket_connect(f"/api/v1/sessions/{sess_id}/dialogue") as ws:
        _ = ws.receive_json()  # Handshake

        # Send recognized utterance frame
        ws.send_json({
            "type": "audio_chunk",
            "text": "मुझे 2 दिन से बुखार और सिरदर्द है",
            "confidence": 0.95,
            "language": "hi",
        })

        # 1. Partial transcript
        partial = ws.receive_json()
        assert partial["type"] == "partial_transcript"
        assert "बुखार" in partial["text"]

        # 2. Final transcript
        final = ws.receive_json()
        assert final["type"] == "final_transcript"
        assert final["confidence"] == 0.95

        # 3. Question from dialogue engine
        question = ws.receive_json()
        assert question["type"] == "question"
        assert question["text"] is not None

        # 4. State frame
        state = ws.receive_json()
        assert state["type"] == "state"
        assert state["session_id"] == sess_id


def test_ws_dialogue_low_confidence_reprompt(client, active_session):
    """Test low ASR confidence triggers reask frame per PRD §10."""
    sess_id = active_session["session_id"]
    with client.websocket_connect(f"/api/v1/sessions/{sess_id}/dialogue") as ws:
        _ = ws.receive_json()  # Handshake

        # Send low-confidence transcript (confidence 0.35 < 0.60 threshold)
        ws.send_json({
            "type": "utterance",
            "text": "muffled noise unintelligible",
            "confidence": 0.35,
            "language": "hi",
        })

        # Partial
        _ = ws.receive_json()
        # Final
        _ = ws.receive_json()

        # Reask frame
        reask = ws.receive_json()
        assert reask["type"] == "reask"
        assert reask["reason"] == "low_confidence"
        assert reask["confidence"] == 0.35
        assert "दोबारा बोलें" in reask["reprompt_text"] or "repeat" in reask["reprompt_text"].lower()


def test_ws_dialogue_client_interruption(client, active_session):
    """Test client control cancel/interruption resets turn."""
    sess_id = active_session["session_id"]
    with client.websocket_connect(f"/api/v1/sessions/{sess_id}/dialogue") as ws:
        _ = ws.receive_json()  # Handshake

        # Send control interrupt
        ws.send_json({
            "type": "control",
            "action": "cancel",
        })

        ctrl_resp = ws.receive_json()
        assert ctrl_resp["type"] == "control"
        assert ctrl_resp["action"] == "cancelled"


def test_ws_dialogue_malformed_payload(client, active_session):
    """Test malformed JSON / missing type handling."""
    sess_id = active_session["session_id"]
    with client.websocket_connect(f"/api/v1/sessions/{sess_id}/dialogue") as ws:
        _ = ws.receive_json()  # Handshake

        # Send missing type
        ws.send_json({"foo": "bar"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["error_code"] == "MISSING_TYPE"

        # Send non-JSON text
        ws.send_text("THIS IS NOT JSON")
        err2 = ws.receive_json()
        assert err2["type"] == "error"
        assert err2["error_code"] == "INVALID_JSON"
