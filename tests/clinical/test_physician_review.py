import pytest

from contracts.dialogue import ClinicalSlot
from ayusetu.ai.clinical.summary import physician_review
from ayusetu.ai.clinical.summary.composer import SummaryGenerator
from ayusetu.ai.clinical.summary.contracts import RejectionReason, SummaryStatus


@pytest.fixture
def summary():
    generator = SummaryGenerator()
    return generator.generate(
        "enc-1",
        {ClinicalSlot.CHIEF_COMPLAINT: "fever", ClinicalSlot.DURATION: "3 days"},
        [ClinicalSlot.ALLERGIES],
    )


def test_sign_transitions_preliminary_to_final(summary):
    physician_review.sign(summary, physician_id="dr-1")
    assert summary.status == SummaryStatus.FINAL
    assert summary.signed_by == "dr-1"
    assert summary.signed_at is not None


def test_cannot_sign_twice(summary):
    physician_review.sign(summary, physician_id="dr-1")
    with pytest.raises(physician_review.AlreadySignedError):
        physician_review.sign(summary, physician_id="dr-1")


def test_edit_field_records_diff_and_updates_value(summary):
    edit = physician_review.edit_field(
        summary, slot_path="chief_complaint", new_value="high fever", reason="clarified by physician", editor="dr-1"
    )
    assert edit.old_value == "fever"
    assert edit.new_value == "high fever"
    assert summary.chief_complaint == "high fever"


def test_cannot_edit_final_summary(summary):
    physician_review.sign(summary, physician_id="dr-1")
    with pytest.raises(physician_review.AlreadySignedError):
        physician_review.edit_field(summary, "chief_complaint", "x", "reason", "dr-1")


def test_reject_records_structured_reason(summary):
    rejection = physician_review.reject(summary, RejectionReason.UNSAFE, rejected_by="dr-1", detail="wrong dosage")
    assert rejection.reason == RejectionReason.UNSAFE
    assert rejection.detail == "wrong dosage"
    # Rejecting doesn't silently finalise a summary.
    assert summary.status == SummaryStatus.PRELIMINARY


def test_patient_facing_version_uses_only_gate_passed_fields(summary):
    text_en = physician_review.generate_patient_facing_version(summary, language="en")
    assert "fever" in text_en
    assert "3 days" in text_en

    text_hi = physician_review.generate_patient_facing_version(summary, language="hi")
    assert "fever" in text_hi  # value is substituted verbatim regardless of template language
