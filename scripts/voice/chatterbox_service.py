import sys
import os

# Prevent shadowing by removing the workspace root and script directory from sys.path
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
script_dir = os.path.abspath(os.path.dirname(__file__))
sys.path = [p for p in sys.path if os.path.abspath(p or ".") not in (workspace_root, script_dir)]

if "chatterbox" in sys.modules:
    del sys.modules["chatterbox"]
if "chatterbox.tts" in sys.modules:
    del sys.modules["chatterbox.tts"]

import torch
import base64
import numpy as np
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

try:
    from chatterbox.tts import ChatterboxTTS
except ImportError as e:
    raise RuntimeError(f"Could not import real ChatterboxTTS: {e}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

model = None
sample_rate = 24000

@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    logger.info("Initializing Chatterbox TTS Model...")
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Using device: {device}")
    
    model = ChatterboxTTS.from_pretrained(device=device)
    logger.info("Model loaded successfully.")
    
    yield
    
    logger.info("Shutting down TTS service.")
    model = None

app = FastAPI(lifespan=lifespan)

class SynthesizeRequest(BaseModel):
    text: str
    language: str = "en"

@app.get("/health")
def health():
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"status": "ok", "device": "cuda" if torch.cuda.is_available() else "cpu"}

@app.post("/synthesize")
def synthesize(req: SynthesizeRequest):
    if not model:
        raise HTTPException(status_code=503, detail="Model not loaded")
        
    logger.info(f"Synthesizing text: {req.text} (lang: {req.language})")
    
    try:
        audio = model.generate(req.text)
        
        if hasattr(audio, 'cpu'):
            audio = audio.cpu().numpy()
        
        if len(audio.shape) > 1:
            audio = audio.squeeze()
            
        audio_float32 = audio.astype(np.float32)
        duration = len(audio_float32) / sample_rate
        
        audio_b64 = base64.b64encode(audio_float32.tobytes()).decode("utf-8")
        
        return {
            "audio_b64": audio_b64,
            "sample_rate": sample_rate,
            "duration": float(duration)
        }
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
