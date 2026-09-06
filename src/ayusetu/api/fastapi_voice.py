import base64
import tempfile
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import soundfile as sf
import imageio_ffmpeg
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ayusetu.ai.voice.pipeline.voice_pipeline import VoicePipeline
from contracts.dialogue import DialogueState

app = FastAPI(title="AyuSetu Voice API")

# Single shared pipeline instance (in‑memory session manager)
voice_pipeline = VoicePipeline()

# ---------- Pydantic response models ----------
class SessionCreateResponse(BaseModel):
    session_id: str

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

class DialogueStateResponse(BaseModel):
    state: DialogueState

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
def create_session():
    session_id = voice_pipeline.create_session()
    return SessionCreateResponse(session_id=session_id)

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
