import base64
import tempfile
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, List
import soundfile as sf
import imageio_ffmpeg
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ayusetu.ai.voice.pipeline.voice_pipeline import VoicePipeline
from contracts.dialogue import DialogueState
from ayusetu.ai.clinical.document_ai.ocr import MockOCRProvider
from ayusetu.ai.clinical.document_ai.entity_extractor import extract_entities
from ayusetu.ai.clinical.summary.composer import SummaryGenerator
from ayusetu.ai.clinical.summary.contracts import ClinicalSummary, RejectionReason, SummaryEdit, SummaryRejection
from ayusetu.ai.clinical.summary import physician_review
from ayusetu.ai.clinical.memory.contracts import EncounterSnapshot, TimelineEvent
from ayusetu.ai.clinical.memory.timeline import build_timeline_from_encounter

app = FastAPI(title="AyuSetu Voice API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single shared pipeline instance (in‑memory session manager)
voice_pipeline = VoicePipeline()

# ---------- Pydantic response & request models ----------
class SessionCreateRequest(BaseModel):
    preferred_language: Optional[str] = "hinglish"

class SessionCreateResponse(BaseModel):
    session_id: str
    preferred_language: Optional[str] = "hinglish"

class LanguageUpdateRequest(BaseModel):
    preferred_language: str

class TurnResponse(BaseModel):
    transcribed_text: str
    detected_language: str
    asr_confidence: float
    low_confidence: bool
    response_text: Optional[str] = None
    response_audio: Optional[str] = None  # Base64‑encoded WAV
    response_sample_rate: Optional[int] = None
    response_duration: Optional[float] = None
    session_id: Optional[str] = None
    red_flags: Optional[List[Dict[str, Any]]] = None
    preferred_language: Optional[str] = None

class DialogueStateResponse(BaseModel):
    state: DialogueState

class SignOffRequest(BaseModel):
    physician_id: str

class EditRequest(BaseModel):
    slot_path: str
    new_value: Optional[str] = None
    reason: str
    physician_id: str

class RejectRequest(BaseModel):
    reason: RejectionReason
    physician_id: str
    detail: Optional[str] = None

# ---------------- Helper functions ----------------
def _convert_to_wav(src_path: Path) -> Path:
    """Convert *src_path* (any supported format) to a 16kHz mono WAV.
    Returns the path to a temporary WAV file which the caller must delete.
    """
    # Create a safe temporary file for the output WAV
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_wav:
        wav_path = Path(tmp_wav.name)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    # Force 16kHz mono output – the ASR expects this format.
    result = subprocess.run(
        [ffmpeg, "-y", "-i", str(src_path), "-ar", "16000", "-ac", "1", str(wav_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Cleanup before raising
        wav_path.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg conversion failed: {result.stderr}")
    return wav_path

def _wav_bytes_from_numpy(audio: Any, sample_rate: int) -> bytes:
    """Encode a NumPy (or array‑like) audio waveform as a WAV byte stream."""
    # ``soundfile`` accepts any array‑like object.
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        sf.write(tmp.name, audio, samplerate=sample_rate, format="WAV")
        tmp_path = Path(tmp.name)
    wav_bytes = tmp_path.read_bytes()
    tmp_path.unlink(missing_ok=True)
    return wav_bytes

# ------------------- Endpoints -------------------
@app.post("/sessions", response_model=SessionCreateResponse)
def create_session(req: Optional[SessionCreateRequest] = None):
    preferred_lang = req.preferred_language if req and req.preferred_language else "hinglish"
    session_id = voice_pipeline.create_session(preferred_language=preferred_lang)
    return SessionCreateResponse(session_id=session_id, preferred_language=preferred_lang)

@app.patch("/sessions/{session_id}/language")
def update_language(session_id: str, req: LanguageUpdateRequest):
    try:
        session = voice_pipeline.get_session(session_id)
        session.state.preferred_language = req.preferred_language.lower()
        return {"session_id": session_id, "preferred_language": session.state.preferred_language}
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

@app.post("/sessions/{session_id}/turn", response_model=TurnResponse)
def turn(
    session_id: str,
    audio: UploadFile = File(...),
):
    # Verify session exists early
    try:
        _ = voice_pipeline.get_state(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    # Save uploaded file to a temporary path
    try:
        suffix = Path(audio.filename).suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_input:
            tmp_input_path = Path(tmp_input.name)
            tmp_input.write(audio.file.read())
    finally:
        audio.file.close()

    # Convert to the required WAV format
    try:
        wav_path = _convert_to_wav(tmp_input_path)
    except Exception as e:
        tmp_input_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        # Remove the original upload regardless of conversion success
        tmp_input_path.unlink(missing_ok=True)

    # Execute pipeline
    try:
        result: Dict[str, Any] = voice_pipeline.run(str(wav_path), session_id=session_id)
    except KeyError:
        wav_path.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail="Session not found")
    except Exception as e:
        wav_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Pipeline processing error")
    finally:
        wav_path.unlink(missing_ok=True)

    # Serialize audio if present
    audio_b64: Optional[str] = None
    if result.get("response_audio") is not None:
        wav_bytes = _wav_bytes_from_numpy(result["response_audio"], result["response_sample_rate"])
        audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")

    # Retrieve session state for preferred language
    session_obj = voice_pipeline.get_session(session_id)
    pref_lang = getattr(session_obj.state, "preferred_language", "hinglish")

    # Build response model
    return TurnResponse(
        transcribed_text=result["transcribed_text"],
        detected_language=result["detected_language"],
        asr_confidence=result["asr_confidence"],
        low_confidence=result["low_confidence"],
        response_text=result.get("response_text"),
        response_audio=audio_b64,
        response_sample_rate=result.get("response_sample_rate"),
        response_duration=result.get("response_duration"),
        session_id=result.get("session_id"),
        red_flags=result.get("red_flags", []),
        preferred_language=pref_lang,
    )

@app.get(
    "/sessions/{session_id}/state",
    response_model=DialogueStateResponse,
)
def get_state(session_id: str) -> DialogueStateResponse:
    try:
        state = voice_pipeline.get_state(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    return DialogueStateResponse(state=state)

@app.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str):
    try:
        voice_pipeline.end_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)

# ------------------- Document AI Endpoint -------------------
@app.post("/sessions/{session_id}/documents")
def upload_document(session_id: str, document: UploadFile = File(...)):
    try:
        session = voice_pipeline.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    content = document.file.read()
    # Decode text for OCR parsing
    text = content.decode("utf-8", errors="ignore")
    from ayusetu.ai.clinical.document_ai.contracts import OCRResult
    ocr_result = OCRResult(page_no=1, raw_text=text, mean_confidence=0.9)
    entities = extract_entities(ocr_result.raw_text)
    session.document_entities.extend(entities)

    return {
        "status": "success",
        "session_id": session_id,
        "filename": document.filename,
        "extracted_entities_count": len(entities),
        "entities": [e.model_dump(mode="json") for e in entities],
    }

# ------------------- Clinical Summary Endpoints -------------------
@app.post("/sessions/{session_id}/summary", response_model=ClinicalSummary)
def generate_summary(session_id: str):
    try:
        session = voice_pipeline.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    collected_info = {
        s.value if hasattr(s, "value") else str(s): str(v)
        for s, v in session.state.collected_info.items()
    }
    missing_slots = [
        s.value if hasattr(s, "value") else str(s)
        for s in session.state.missing_slots
    ]

    summary = SummaryGenerator().generate(
        encounter_id=session_id,
        collected_info=collected_info,
        missing_slots=missing_slots,
        red_flag_events=session.red_flag_events,
        document_entities=session.document_entities,
    )
    session.summary = summary
    return summary

# ------------------- Physician Review Endpoints -------------------
@app.post("/sessions/{session_id}/summary/sign-off", response_model=ClinicalSummary)
def sign_off_summary_endpoint(session_id: str, req: SignOffRequest):
    try:
        session = voice_pipeline.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.summary is None:
        raise HTTPException(status_code=400, detail="No summary generated yet for this session")

    try:
        updated = physician_review.sign(session.summary, req.physician_id)
    except physician_review.AlreadySignedError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return updated

@app.put("/sessions/{session_id}/summary/edit")
def edit_summary_endpoint(session_id: str, req: EditRequest):
    try:
        session = voice_pipeline.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.summary is None:
        raise HTTPException(status_code=400, detail="No summary generated yet for this session")

    try:
        edit_record = physician_review.edit_field(
            session.summary, req.slot_path, req.new_value, req.reason, req.physician_id
        )
    except physician_review.AlreadySignedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "edit_record": edit_record.model_dump(mode="json"),
        "summary": session.summary.model_dump(mode="json"),
    }

@app.post("/sessions/{session_id}/summary/reject")
def reject_summary_endpoint(session_id: str, req: RejectRequest):
    try:
        session = voice_pipeline.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.summary is None:
        raise HTTPException(status_code=400, detail="No summary generated yet for this session")

    try:
        rejection_record = physician_review.reject(
            session.summary, req.reason, req.physician_id, req.detail
        )
    except physician_review.AlreadySignedError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "rejection": rejection_record.model_dump(mode="json"),
    }

# ------------------- Patient Timeline Endpoint -------------------
@app.get("/sessions/{session_id}/timeline", response_model=List[TimelineEvent])
def get_timeline(session_id: str) -> List[TimelineEvent]:
    try:
        session = voice_pipeline.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    red_flag_titles = [
        rf.trigger_text if hasattr(rf, "trigger_text") else str(rf)
        for rf in session.red_flag_events
    ]

    snapshot = EncounterSnapshot(
        encounter_id=session_id,
        collected_info=session.state.collected_info,
        missing_slots=session.state.missing_slots,
        document_entities=session.document_entities,
        red_flag_titles=red_flag_titles,
    )
    events = build_timeline_from_encounter(snapshot)
    return events

