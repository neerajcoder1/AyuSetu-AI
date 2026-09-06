# AyuSetu AI — Third-Party Model and Dataset License Attribution
# ================================================================
# Project: AyuSetu AI (SIH 2026, Problem Statement SIH26047)
# Module:  ASR (Automatic Speech Recognition)
# Author:  Neeraj (neeraj/ai-core branch)
#
# This file documents all third-party models, datasets, and libraries
# used in the AyuSetu ASR module and their respective licenses.
#
# IMPORTANT: AyuSetu AI does NOT claim ownership of any third-party model.
# Each model remains the property of its original authors/organizations.
# ================================================================

---

## 1. Primary Development Candidate

### shunyalabs/zero-stt-hinglish

| Field | Details |
|---|---|
| **Model name** | Zero STT Codeswitch (Hinglish open-source version) |
| **Author / Organization** | Shunya Research Labs Pvt. Ltd. |
| **HuggingFace repository** | https://huggingface.co/shunyalabs/zero-stt-hinglish |
| **License** | **OpenRAIL** |
| **OpenRAIL license text** | https://huggingface.co/spaces/bigcode/bigcode-model-license-agreement |
| **Base architecture** | OpenAI Whisper Medium (post-trained by Shunya Labs) |
| **Training datasets** | Vaani (ARTPARK-IISc), Kathbath (AI4Bharat), Shrutilipi (AI4Bharat), proprietary Shunya Labs datasets |

### OpenRAIL License — Key Terms (Summary)

OpenRAIL is a Responsible AI License. It permits:
- Research and academic use ✅
- Non-commercial prototype and demonstration use ✅
- Use in SIH 2026 competition submissions ✅ (research/educational context)

OpenRAIL **restricts**:
- Use to generate harmful, deceptive, or abusive content ❌
- Use in ways that violate applicable law ❌
- Removal of attribution requirements ❌

> ⚠️ **IMPORTANT**: This model is used in AyuSetu AI as a research prototype
> for SIH 2026. It has NOT been reviewed for commercial deployment rights.
> Before any commercial or production deployment beyond the SIH submission,
> the full OpenRAIL license text must be reviewed by a qualified person.
> Do not assume commercial rights without that review.

**Required attribution**: The model is created by Shunya Research Labs Pvt. Ltd.
AyuSetu AI does not claim authorship of this model.

---

## 2. Hindi Specialist Comparison Model

### ARTPARK-IISc/whisper-large-v3-vaani-hindi

| Field | Details |
|---|---|
| **Model name** | whisper-large-v3-vaani-hindi |
| **Author / Organization** | ARTPARK (AI & Robotics Technology Park) + IISc Bangalore |
| **HuggingFace repository** | https://huggingface.co/ARTPARK-IISc/whisper-large-v3-vaani-hindi |
| **License** | **Apache-2.0** |
| **Base architecture** | OpenAI Whisper Large V3 (fine-tuned on Vaani + Indic datasets) |
| **Training datasets** | Vaani (ARTPARK-IISc), IndicVoices, FLEURS Hindi, Gramvaani, IndicTTS, CommonVoice Hindi |

### Apache-2.0 License — Key Terms (Summary)

Apache-2.0 permits:
- Research and academic use ✅
- Commercial use with attribution ✅
- Modification and distribution ✅

Required: Retain copyright notice and attribution to ARTPARK-IISc and IISc Bangalore.

**Model card metadata note**: The `base_model` YAML field in the model card
has been observed to reference `openai/whisper-small` inconsistently with the
model name and description. This is a known template error. The actual base
model is Whisper Large V3, confirmed by the model name, description, and
usage examples. Do not use the `base_model` metadata field as authoritative.

---

## 3. Neutral Baseline Model

### openai/whisper-large-v3-turbo

| Field | Details |
|---|---|
| **Model name** | Whisper Large V3 Turbo |
| **Author / Organization** | OpenAI |
| **HuggingFace repository** | https://huggingface.co/openai/whisper-large-v3-turbo |
| **License** | **MIT** |
| **Base architecture** | Distilled Whisper Large V3 (decoder layers reduced from 32 to 4) |

### MIT License — Key Terms (Summary)

MIT permits:
- Research, commercial, and academic use ✅
- Modification and distribution ✅

Required: Retain copyright notice (Copyright (c) OpenAI).

---

## 4. Inference Library

### faster-whisper (SYSTRAN)

| Field | Details |
|---|---|
| **Library name** | faster-whisper |
| **Author / Organization** | SYSTRAN |
| **Repository** | https://github.com/SYSTRAN/faster-whisper |
| **License** | **MIT** |

---

## 5. Training Datasets (used by primary model)

### Vaani Dataset (ARTPARK-IISc)

| Field | Details |
|---|---|
| **Dataset** | Vaani |
| **Author** | ARTPARK-IISc (IISc Bangalore) |
| **License** | CC-BY 4.0 (core subset) |
| **Coverage** | ~800 hours Hindi speech, 165 districts, multiple Indian states |
| **HuggingFace** | https://huggingface.co/datasets/ARTPARK-IISc/Vaani |

### Kathbath Dataset (AI4Bharat)

| Field | Details |
|---|---|
| **Dataset** | Kathbath |
| **Author** | AI4Bharat |
| **License** | CC-BY 4.0 |
| **Coverage** | Hindi speech benchmark, multiple speakers and conditions |
| **HuggingFace** | https://huggingface.co/datasets/ai4bharat/Kathbath |

### Shrutilipi Dataset (AI4Bharat)

| Field | Details |
|---|---|
| **Dataset** | Shrutilipi |
| **Author** | AI4Bharat |
| **License** | CC-BY 4.0 |
| **HuggingFace** | https://huggingface.co/datasets/ai4bharat/Shrutilipi |

---

## 6. AyuSetu AI Ownership Statement

The AyuSetu AI system, its architecture, clinical ontology, dialogue engine,
and overall design are original work of the AyuSetu AI team for SIH 2026.

The ASR module **uses** the third-party models listed above but does NOT
modify their weights during Phase 1. If fine-tuning is performed in Phase 2,
the fine-tuned weights will be derived works and must be distributed under
terms compatible with the original model license (OpenRAIL or Apache-2.0
as applicable).

**Do not**:
- Claim shunyalabs/zero-stt-hinglish as an AyuSetu proprietary model.
- Remove attribution from model usage documentation.
- Deploy commercially without reviewing OpenRAIL terms.
