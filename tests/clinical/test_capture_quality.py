from ayusetu.ai.clinical.document_ai.capture_quality import score_capture


def _sharp_grid(rows=20, cols=20):
    # Alternating bright/dark rows -> strong edges, strong row-sum banding.
    return [[240 if r % 2 == 0 else 10 for _ in range(cols)] for r in range(rows)]


def _blurry_grid(rows=20, cols=20):
    # Uniform gray -> no edges at all.
    return [[128 for _ in range(cols)] for _ in range(rows)]


def _glare_grid(rows=20, cols=20):
    # Mostly blown-out white.
    return [[250 for _ in range(cols)] for _ in range(rows)]


def test_sharp_well_banded_image_is_accepted():
    score = score_capture(_sharp_grid())
    assert score.accepted
    assert score.rejection_reasons == []


def test_uniform_gray_image_is_rejected_as_blurry():
    score = score_capture(_blurry_grid())
    assert not score.accepted
    assert "blurry" in score.rejection_reasons


def test_saturated_image_is_rejected_for_glare():
    score = score_capture(_glare_grid())
    assert not score.accepted
    assert "glare" in score.rejection_reasons


def test_scores_are_within_bounds():
    score = score_capture(_sharp_grid())
    assert 0.0 <= score.blur_score <= 1.0
    assert 0.0 <= score.glare_score <= 1.0
    assert 0.0 <= score.skew_score <= 1.0
