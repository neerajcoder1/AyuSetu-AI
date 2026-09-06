"""
AyuSetu AI — ASR Evaluation Harness  [Phase 1C Placeholder]
=============================================================
This module will contain the three-model WER/CER/CS-WER evaluation harness.

It is NOT implemented in Phase 1B (single-model baseline).
Implementation begins after the baseline pipeline is confirmed working
and smoke tests pass for Hindi, English, and Hinglish.

Planned public functions
------------------------
    evaluate_model(model_id, dataset, output_path) -> EvaluationResult
        Run a single model against the standardised AyuSetu eval dataset.

    compare_models(model_ids, dataset, output_path) -> ComparisonReport
        Run all three candidate models and produce a side-by-side report.

Planned metrics
---------------
    overall_wer           Word Error Rate across all samples
    overall_cer           Character Error Rate across all samples
    hindi_wer             WER on samples tagged type="hi"
    english_wer           WER on samples tagged type="en"
    hinglish_wer          WER on samples tagged type="hi-en"
    cs_wer                Code-Switching WER at language-boundary windows
    medical_vocab_error   % of medical terms incorrectly transcribed
    noisy_wer             WER on noise-augmented or telephony samples
    avg_inference_ms      Per-utterance wall-clock inference time

Datasets to be used (see eval/datasets/README.md when created)
--------------------------------------------------------------
    Kathbath Hindi test split    (ai4bharat/Kathbath)
    FLEURS Hindi hi_in test      (google/fleurs)
    MUCS 2021 CS test set        (IIIT-Hyderabad, public)
    Custom AyuSetu utterances    (manually recorded)

See implementation_plan.md §3 for the full evaluation design.

TODO: Implement in Phase 1C.
"""

# ─── Phase 1C implementation will go here ─────────────────────────────────────

__all__: list = []
