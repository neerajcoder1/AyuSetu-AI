"""
Dialogue WebSocket Gateway Endpoint
===================================
Authoritative full-duplex WebSocket handler mounted at:
WS /api/v1/sessions/{id}/dialogue
per PRD v3 §8.2, §8.5, §22.2, §22.6, and schema packages/schemas/dialogue_ws.json.

Handles:
- Session authentication and lifecycle validation
- Binary & JSON chunk streaming
- ASR turn processing with confidence gating & re-prompting
- Client interruption / cancellation (control: cancel/interrupt/abort)
- Dialogue state updates and slot tracking
- Clean disconnect and error taxonomy
"""

import json
import logging
from typing import Any, Dict, Optional
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from ayusetu.common.session_cache import SessionCache
from ayusetu.gateway.errors import ErrorCode
from contracts.asr_output import ASROutput
from contracts.dialogue import DialogueState, DialogueTurn, ClinicalSlot
from ayusetu.ai.conversation.engine import DialogueEngine

logger = logging.getLogger("ayusetu.gateway.dialogue_ws")
router = APIRouter()
session_cache = SessionCache()


class DialogueWebSocketSession:
    """Manages state for an active full-duplex dialogue WebSocket connection."""

    def __init__(self, websocket: WebSocket, session_id: str, session_data: Dict[str, Any]):
        self.websocket = websocket
        self.session_id = session_id
        self.session_data = session_data
        self.dialogue_engine = DialogueEngine()
        self.dialogue_state: DialogueState = self.dialogue_engine.initialize()
        self.is_cancelled: bool = False
        self.turn_count: int = 0

    async def send_json(self, payload: Dict[str, Any]) -> None:
        """Send a JSON frame conforming to dialogue_ws.json schema."""
        try:
            await self.websocket.send_text(json.dumps(payload))
        except Exception as e:
            logger.warning(f"Failed to send WS message to session {self.session_id}: {e}")

    async def send_error(self, code: str, message: str, close: bool = False) -> None:
        """Emit an error frame conforming to PRD error taxonomy."""
        payload = {
            "type": "error",
            "error_code": code,
            "message": message,
            "session_id": self.session_id,
        }
        await self.send_json(payload)
        if close:
            await self.websocket.close(code=status.WS_1008_POLICY_VIOLATION)

    async def handle_control_message(self, data: Dict[str, Any]) -> None:
        """Handle control messages such as interruption, cancellation, or reset."""
        action = data.get("action", "").lower()
        if action in ("cancel", "interrupt", "abort", "barge_in"):
            self.is_cancelled = True
            await self.send_json({
                "type": "control",
                "action": "cancelled",
                "session_id": self.session_id,
                "message": "Turn processing cancelled by client interruption",
            })
        elif action == "ping":
            await self.send_json({
                "type": "control",
                "action": "pong",
                "session_id": self.session_id,
            })
        else:
            await self.send_json({
                "type": "control",
                "action": "acknowledged",
                "session_id": self.session_id,
            })

    async def handle_touch_answer(self, data: Dict[str, Any]) -> None:
        """Process direct touch/PWA slot answer bypassing ASR."""
        slot_name = data.get("slot")
        value = data.get("value")
        if not slot_name or value is None:
            await self.send_error("INVALID_PAYLOAD", "Touch answer requires 'slot' and 'value'")
            return

        # Find matching ClinicalSlot
        matched_slot = None
        for s in ClinicalSlot:
            if s.value == slot_name:
                matched_slot = s
                break

        if matched_slot:
            self.dialogue_state.collected_info[matched_slot] = str(value)
            if matched_slot in self.dialogue_state.missing_slots:
                self.dialogue_state.missing_slots.remove(matched_slot)

        # Update session cache slots
        current_slots = self.session_data.get("slots", {})
        if isinstance(current_slots, dict):
            current_slots[f"hpi.{slot_name}"] = value
        elif isinstance(current_slots, list):
            current_slots.append({
                "path": f"hpi.{slot_name}",
                "value": value,
                "source": "touch",
                "reported_by": "patient",
                "confidence": 1.0,
                "elicited": True,
            })
        session_cache.update_session(self.session_id, {"slots": current_slots})

        await self.send_json({
            "type": "slot_filled",
            "slot": slot_name,
            "value": value,
            "source": "touch",
            "session_id": self.session_id,
        })

    async def handle_text_or_audio_turn(
        self,
        text: str,
        confidence: float = 0.95,
        language: str = "hi",
    ) -> None:
        """Process a recognized turn through the DialogueEngine."""
        self.is_cancelled = False
        self.turn_count += 1

        # Emit interim / partial transcript
        await self.send_json({
            "type": "partial_transcript",
            "text": text,
            "confidence": confidence,
            "language": language,
            "session_id": self.session_id,
        })

        if self.is_cancelled:
            return

        # Emit final transcript
        await self.send_json({
            "type": "final_transcript",
            "text": text,
            "confidence": confidence,
            "language": language,
            "session_id": self.session_id,
            "turn": self.turn_count,
        })

        if self.is_cancelled:
            return

        # Record utterance in session cache
        utterances = self.session_data.get("utterances", [])
        utterances.append({
            "id": str(uuid.uuid4()),
            "seq": self.turn_count,
            "speaker": "patient",
            "text": text,
            "lang": language,
            "asr_confidence": confidence,
        })
        session_cache.update_session(self.session_id, {"utterances": utterances})

        # Low ASR Confidence Re-prompting per PRD §10 & §23.1
        if confidence < self.dialogue_engine.planner.asr_confidence_threshold:
            reprompt_text = "क्षमा करें, मैं समझ नहीं पाया। कृपया दोबारा बोलें।" if language == "hi" else "I could not hear clearly. Could you please repeat?"
            await self.send_json({
                "type": "reask",
                "reason": "low_confidence",
                "confidence": confidence,
                "reprompt_text": reprompt_text,
                "session_id": self.session_id,
            })
            return

        asr_output = ASROutput(
            text=text,
            language=language,
            confidence=confidence,
        )

        # Step Dialogue Engine
        response_text = self.dialogue_engine.step(asr_output, self.dialogue_state)

        if self.is_cancelled:
            return

        # Update session cache with collected slots
        session_slots = self.session_data.get("slots", {})
        if isinstance(session_slots, dict):
            for slot_k, slot_v in self.dialogue_state.collected_info.items():
                slot_key = slot_k.value if hasattr(slot_k, "value") else str(slot_k)
                session_slots[f"hpi.{slot_key}"] = slot_v
        session_cache.update_session(self.session_id, {"slots": session_slots})

        # Emit AI Question / Response
        await self.send_json({
            "type": "question",
            "text": response_text,
            "language": language,
            "session_id": self.session_id,
            "is_complete": self.dialogue_state.is_complete,
        })

        # Emit State Frame
        collected_serializable = {
            (k.value if hasattr(k, "value") else str(k)): v
            for k, v in self.dialogue_state.collected_info.items()
        }
        await self.send_json({
            "type": "state",
            "session_id": self.session_id,
            "collected_slots": collected_serializable,
            "is_complete": self.dialogue_state.is_complete,
            "needs_clarification": self.dialogue_state.needs_clarification,
        })


@router.websocket("/sessions/{id}/dialogue")
async def websocket_dialogue_endpoint(websocket: WebSocket, id: str):
    """
    WebSocket endpoint for real-time voice and multimodal dialogue interaction.
    Protocol conforms to packages/schemas/dialogue_ws.json.
    """
    # 1. Check session validity before accepting
    session = session_cache.get_session(id)
    if not session:
        await websocket.accept()
        err_payload = {
            "type": "error",
            "error_code": ErrorCode.SESSION_EXPIRED.value,
            "message": f"Session '{id}' not found or expired",
            "session_id": id,
        }
        await websocket.send_text(json.dumps(err_payload))
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    handler = DialogueWebSocketSession(websocket=websocket, session_id=id, session_data=session)

    # Send initial state/handshake
    await handler.send_json({
        "type": "state",
        "session_id": id,
        "status": "connected",
        "channel": session.get("channel", "kiosk"),
        "language": session.get("language", "hi"),
        "message": "Dialogue WebSocket connected and ready for audio/touch streams",
    })

    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                msg = json.loads(raw_message)
            except Exception:
                await handler.send_error("INVALID_JSON", "Payload must be valid JSON")
                continue

            msg_type = msg.get("type")
            if not msg_type:
                await handler.send_error("MISSING_TYPE", "Message missing 'type' field")
                continue

            if msg_type == "control":
                await handler.handle_control_message(msg)
            elif msg_type == "touch_answer":
                await handler.handle_touch_answer(msg)
            elif msg_type in ("audio_chunk", "final_transcript", "utterance"):
                # Handle text transcription payload or synthesized turn
                text = msg.get("text") or msg.get("transcription") or ""
                confidence = float(msg.get("confidence", 0.95))
                language = msg.get("language") or session.get("language", "hi")
                await handler.handle_text_or_audio_turn(text=text, confidence=confidence, language=language)
            else:
                # Unsupported or custom type
                await handler.send_json({
                    "type": "state",
                    "session_id": id,
                    "received_type": msg_type,
                    "status": "acknowledged",
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected cleanly for session {id}")
    except Exception as e:
        logger.error(f"WebSocket unexpected error for session {id}: {e}")
        try:
            await handler.send_error("INTERNAL_ERROR", str(e))
        except Exception:
            pass
