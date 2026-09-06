# AyuSetu AI — ASR Module

ASR (Automatic Speech Recognition) module for AyuSetu AI.
Supports Hindi, English, and Hindi-English code-switching (Hinglish).

**SIH 2026 | Problem Statement SIH26047 | Branch: `neeraj/ai-core`**

---

## Quick Start

### 1. Clone and set up

```bash
# From the repository root (neeraj/ai-core branch):
pip install -e ".[dev]"

# Or using requirements.txt directly:
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — the defaults work for Phase 1 testing
```

The defaults in `.env.example` are:
```
ASR_MODEL=shunyalabs/zero-stt-hinglish
ASR_BACKEND=transformers
ASR_DEVICE=cpu
ASR_COMPUTE_TYPE=int8
ASR_FORCE_LANGUAGE=           ← leave empty for Hinglish support
```

### 3. Run unit tests (no model download required)

```bash
pytest tests/test_asr.py -v -k "not Smoke"
```

Expected: all unit tests pass in < 5 seconds with no model download.

### 4. Run smoke tests with real audio

```bash
# Set paths to your audio files (WAV, 16kHz recommended):
SKIP_MODEL_TESTS=0 \
HINDI_AUDIO=samples/hindi.wav \
ENGLISH_AUDIO=samples/english.wav \
HINGLISH_AUDIO=samples/hinglish.wav \
pytest tests/test_asr.py -v -k "Smoke"
```

The model (~1.5 GB) will download automatically on first run.

### 5. Use the API directly

```python
from neeraj.asr.transcriber import transcribe

output = transcribe("path/to/audio.wav")
print(output.to_dict())
# {"text": "मुझे दो दिन से fever है", "language": "hi-en", "confidence": 0.84}
```

---

## Architecture

```
Audio file (WAV/MP3/FLAC/OGG)
    │
    ▼  neeraj/asr/audio_utils.py
Load + resample to 16kHz mono float32
    │
    ▼  neeraj/asr/model.py (TransformersBackend or FasterWhisperBackend)
ASR inference
    │
    ▼  neeraj/asr/confidence.py
Compute confidence from token logprobs
Infer language from script composition
    │
    ▼  neeraj/asr/transcriber.py  ← THE ONLY PUBLIC API
Assemble + validate ASROutput
    │
    ▼  contracts/asr_output.py
{"text": "...", "language": "...", "confidence": 0.0}
    │
    ▼
Sai's clinical extraction / red-flag / summary modules
```

---

## Module Reference

| File | Purpose | Public? |
|---|---|---|
| `contracts/asr_output.py` | Pydantic contract (frozen schema) | ✅ Import by Sai |
| `neeraj/asr/transcriber.py` | `transcribe(path) → ASROutput` | ✅ Only external-facing ASR API |
| `neeraj/asr/config.py` | Env-var configuration | Internal |
| `neeraj/asr/audio_utils.py` | Load + validate audio | Internal |
| `neeraj/asr/model.py` | Transformers / faster-whisper backends | Internal |
| `neeraj/asr/confidence.py` | Log-prob → confidence; language heuristic | Internal |
| `neeraj/asr/evaluate.py` | Phase 1C WER harness (placeholder) | Internal |

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `ASR_MODEL` | `shunyalabs/zero-stt-hinglish` | HuggingFace model ID |
| `ASR_BACKEND` | `transformers` | `transformers` or `faster-whisper` |
| `ASR_DEVICE` | `cpu` | `cpu` or `cuda` |
| `ASR_COMPUTE_TYPE` | `int8` | `int8`, `float16`, `float32` |
| `ASR_FORCE_LANGUAGE` | *(empty)* | Leave empty for Hinglish. See warning below. |
| `ASR_CONFIDENCE_THRESHOLD` | `0.60` | Below this → re-prompt warning |
| `ASR_MAX_DURATION_SECONDS` | `120.0` | Reject audio longer than this |
| `HF_TOKEN` | *(empty)* | HuggingFace token (all Phase 1 models are public) |

### ⚠️ ASR_FORCE_LANGUAGE warning

For `shunyalabs/zero-stt-hinglish`, **leave `ASR_FORCE_LANGUAGE` empty**.

Setting it to `hi` or `en` forces Whisper's decoder into monolingual mode,
which suppresses mixed-script token generation and defeats the model's
Hinglish capability.

For `ARTPARK-IISc/whisper-large-v3-vaani-hindi`, set `ASR_FORCE_LANGUAGE=hi`
(this is what the model card requires).

---

## Switching Models (Evaluation Mode)

To run the pipeline with a different model, change only `.env`:

```bash
# Test with ARTPARK vaani-hindi:
ASR_MODEL=ARTPARK-IISc/whisper-large-v3-vaani-hindi
ASR_FORCE_LANGUAGE=hi

# Test with neutral baseline:
ASR_MODEL=openai/whisper-large-v3-turbo
ASR_FORCE_LANGUAGE=
```

No code changes required.

---

## faster-whisper Backend (Optional)

The `faster-whisper` backend uses CTranslate2 for faster CPU inference.
It requires model conversion before use.

```bash
# Install conversion tool:
pip install ctranslate2

# Convert the model:
ct2-transformers-converter \
    --model shunyalabs/zero-stt-hinglish \
    --output_dir ./models/zero-stt-ct2 \
    --quantization int8

# Update .env:
ASR_BACKEND=faster-whisper
ASR_MODEL=./models/zero-stt-ct2
```

**IMPORTANT**: After conversion, always run the Hinglish smoke test:

```bash
SKIP_MODEL_TESTS=0 \
HINGLISH_AUDIO=samples/hinglish.wav \
pytest tests/test_asr.py::TestSmoke::test_hinglish_mixed_script -v
```

If the test shows `has_devanagari=False` or `has_latin=False` (monolingual output),
the conversion has affected code-switching. In that case, revert to
`ASR_BACKEND=transformers` for Phase 1 and document the issue.

---

## ASR Output Contract

The contract is frozen. Do not change without team agreement.

```python
from contracts.asr_output import ASROutput

# Sai's modules consume this:
output = ASROutput(
    text="मुझे दो दिन से fever है",
    language="hi-en",
    confidence=0.84,
)
print(output.to_dict())
# {"text": "मुझे दो दिन से fever है", "language": "hi-en", "confidence": 0.84}
```

Language codes:
- `"hi"` — Hindi (Devanagari only)
- `"en"` — English (Latin only)
- `"hi-en"` — Hinglish (mixed script)
- `"unknown"` — could not be determined

---

## License and Attribution

See [`LICENSE_ATTRIBUTION.md`](LICENSE_ATTRIBUTION.md) for full details.

- `shunyalabs/zero-stt-hinglish` — **OpenRAIL** (Shunya Research Labs)
- `ARTPARK-IISc/whisper-large-v3-vaani-hindi` — **Apache-2.0** (ARTPARK / IISc)
- `openai/whisper-large-v3-turbo` — **MIT** (OpenAI)

AyuSetu AI does not claim ownership of any third-party model.
The OpenRAIL license must be reviewed before any deployment beyond the SIH prototype.

---

## Phase Roadmap

| Phase | Goal | Status |
|---|---|---|
| 1A | Scaffold + contracts | ✅ Complete |
| 1B | Single-model pipeline (Zero STT Hinglish) | ✅ Complete |
| 1C | Three-model WER/CER evaluation | 🔲 Planned |
| 2 | Domain-specific fine-tuning | 🔲 Planned (after 1C) |
| 3 | Voice pipeline integration (pyaudio, TTS) | 🔲 Planned |
