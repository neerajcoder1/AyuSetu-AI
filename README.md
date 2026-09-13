# AyuSetu AI

AI‑powered multimodal patient case‑taking system for AyuSetu/Ayurveda clinical workflows.

## Problem / Purpose
AyuSetu AI enables voice‑first patient interviews in Hindi, English, and Hinglish, automatically capturing structured clinical information, processing uploaded documents, detecting red‑flags, generating clinical summaries, and supporting physician review and sign‑off. The system also provides patient memory via Hindsight long‑term memory and ensures privacy through de‑identification, consent, and audit trails.

## Current Implemented Features
- **Voice‑first patient consultation** (audio turn‑taking)
- **Multilingual support**: Hindi, English, Hinglish
- **ASR** using Zero‑STT Hinglish backend
- **ASR fine‑tuning** with LoRA adapters
- **WER / CER evaluation** (baseline and fine‑tuned)
- **Language detection** (Hindi / Hinglish)
- **ASR confidence handling** (re‑prompt on low confidence)
- **Deterministic dialogue engine** with slot‑progression and correction traceability
- **Clinical information extraction** (entity extraction, LLM‑driven extraction)
- **Document upload** with OCR / Document AI pipeline
- **Clinical timeline** visualisation
- **Hindsight long‑term memory** (patient‑wise session persistence)
- **Patient / session isolation**
- **Red‑flag detection & escalation** (rule‑based engine)
- **Structured clinical summary** generation
- **Physician review + sign‑off**
- **Interactive body‑map symptom location UI**
- **TTS**:
  - Chatterbox (CPU‑compatible fallback)
  - IndicF5 native Indic‑language provider
  - Switchable TTS backend via `TTS_BACKEND` env var
- **Multilingual audio generation** (Hindi, English, Hinglish)
- **Frontend audio playback controls** (HTML5 `<audio>` with manual play button)
- **AI processing visualisation** component
- **Patient clinical portal** (React UI)
- **Physician dashboard** (React UI)
- **API Gateway** with RBAC/ABAC enforcement
- **DPDP consent management**
- **Immutable audit chain**
- **FHIR R4 compatibility** (clinical resources)
- **ABDM HIU integration**
- **MPI (Master Patient Index) handling**
- **De‑identification / privacy safety controls**
- **Security / load‑shedding** (rate limiting, size limits)
- **Docker / containerised deployment** (backend & frontend)

## Architecture
```
Patient
│
├─ Voice / Body‑Map / Document upload
│   ├─ ASR (Zero‑STT Hinglish)            ← audio → text
│   └─ OCR / Document AI                  ← images → text
│
├─ Dialogue Engine                       ← language & slot handling
│
├─ Clinical Extraction (entity, LLM)     ← structured data
│
├─ Red‑Flag detection & Hindsight memory
│
├─ Clinical Summary generation
│
├─ Physician Review & Sign‑off
│
└─ Summary persistence (Hindsight)
```
**TTS response path**: Text → TTS backend (Chatterbox / IndicF5) → WAV audio → FastAPI `response_audio` → frontend Blob → HTML `<audio>` playback.

## Tech Stack
- **Backend**: Python 3.11, FastAPI, Pydantic, SQLAlchemy, Redis, PostgreSQL, Docker
- **ASR**: `shunyalabs/zero-stt-hinglish` (Transformers backend), LoRA fine‑tuning, confidence scoring
- **TTS**: Chatterbox (CPU fallback), IndicF5 (native Indic), configurable via `TTS_BACKEND`
- **Clinical pipeline**: Custom DialogueEngine, extraction modules, red‑flag rules, Hindsight memory
- **API Gateway**: FastAPI routers, RBAC/ABAC, DPDP consent, audit chain
- **Frontend**: React 18, Vite, TailwindCSS, Zustand for state, TypeScript
- **Security**: Rate limiting, request size caps, audit immutability, de‑identification, FHIR R4 models
- **Infrastructure**: Docker Compose, CI/CD with GitHub Actions

## Voice / ASR Results
| Model | WER | CER |
|------|-----|-----|
| Baseline (Zero‑STT Hinglish) | 60.11 % | 25.61 % |
| Fine‑tuned (LoRA) | 48.79 % | 20.41 % |

*These numbers are obtained from the project’s evaluation suite and represent the test set used for development. They are not guarantees for production use.*

## Text‑to‑Speech (TTS)
- **Chatterbox** – CPU‑compatible fallback, works for all supported languages.
- **IndicF5** – Native Indic‑language TTS, provides higher naturalness for Hindi.
- **Backend selection** via `TTS_BACKEND` environment variable (`chatterbox` or `indic`).
- Verified 24 kHz audio generation for Hindi, English, and Hinglish where supported.
- No GPU performance guarantees; GPU usage is experimental.

## API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions` | Create a new patient session |
| `PATCH` | `/sessions/{session_id}` | Update session metadata (e.g., language) |
| `DELETE` | `/sessions/{session_id}` | Delete a session |
| `POST` | `/sessions/{session_id}/turn` | Submit an audio turn (ASR → dialogue) |
| `GET` | `/sessions/{session_id}/state` | Retrieve current session state |
| `POST` | `/sessions/{session_id}/document` | Upload a clinical document (PDF/IMG) |
| `GET` | `/sessions/{session_id}/summary` | Generate clinical summary |
| `PATCH` | `/sessions/{session_id}/summary` | Edit / approve summary |
| `POST` | `/sessions/{session_id}/summary/signoff` | Physician sign‑off |
| `GET` | `/sessions/{session_id}/timeline` | Retrieve clinical timeline |
| `GET` | `/health` | Service health check |
| (Additional routes under `/gateway` for auth, RBAC, audit, consent, etc.) |
All routes are versioned under `/api/v1` in the source (`src/ayusetu/api`).

## Frontend
- **React + Vite** application located in `frontend/`.
- Major screens/components:
  - `PatientInterviewScreen.jsx` – audio turn UI with playback controls.
  - `AIProcessingVisual.jsx` – subtle visual cue while AI processes input.
  - `BodyMapSelector.jsx` – interactive symptom location map.
  - `SummaryReviewModal.jsx` – physician review and sign‑off UI.
  - `Sidebar.jsx`, `Header.jsx` – navigation and branding.
- Built with TailwindCSS and TypeScript, bundled via `npm --prefix frontend run build`.

## Testing / Verification (Release‑Candidate)
- Frontend production build: **PASSED**
- API test suite: **22 / 22 PASSED**
- Voice tests: **13 / 13 PASSED**
- Reconciliation tests: **5 / 5 PASSED**
- Hindi/English/Hinglish E2E audio verification: **PASSED**
- Patient isolation verification: **PASSED**
- Physician sign‑off + Hindsight persistence: **PASSED**

## Project Status
| Area | Status |
|------|--------|
| Project scaffold & contracts | ✅ Complete |
| ASR pipeline | ✅ Complete |
| ASR evaluation | ✅ Complete |
| ASR fine‑tuning | ✅ Complete |
| Voice pipeline | ✅ Complete |
| Multilingual TTS | ✅ Complete |
| Clinical dialogue engine | ✅ Complete |
| Clinical extraction | ✅ Complete |
| Document intelligence | ✅ Complete |
| Hindsight memory | ✅ Complete |
| Red‑flag detection | ✅ Complete |
| Clinical summary | ✅ Complete |
| Physician workflow | ✅ Complete |
| Body‑map UI | ✅ Complete |
| Patient portal | ✅ Complete |
| Physician dashboard | ✅ Complete |
| Backend platform integration | ✅ Complete |
| Security / privacy controls | ✅ Complete |
| SIH integration | ✅ Complete |

## Deployment
- **Backend**: Docker image `ayusetu/backend` exposing FastAPI on port 8000. Run via `docker compose up -d backend`.
- **Frontend**: Docker image `ayusetu/frontend` serving static assets via Nginx. Run via `docker compose up -d frontend`.
- **Database**: PostgreSQL + Redis containers included in the compose file.
- Full stack can be started with `docker compose up -d`.

## Development / Running Locally
```bash
# Clone the repository
git clone https://github.com/neerajcoder1/AyuSetu-AI.git
cd AyuSetu-AI

# Checkout the integration branch
git checkout feature/sih-2026-integration

# Install backend dependencies (editable install)
pip install -e "[dev]"

# Set up environment
cp .env.example .env   # edit if needed

# Start backend (FastAPI)
uvicorn src.ayusetu.api.main:app --reload

# Frontend
npm --prefix frontend install
npm --prefix frontend run dev   # Vite dev server

# Run tests
pytest -vv
```

## License
The project is licensed under the **Apache‑2.0** license. See `LICENSE` for details.

---
*This README reflects the state of the repository after merging `feature/sih-2026-integration` into `main`. All listed features are present in the codebase and have been verified by the release‑candidate test suite.*
