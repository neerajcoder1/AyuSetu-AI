"""
Capture-time quality scoring: "reject before accepting" (PRD §11.1).

Images are poor at the kiosk camera far more often than they are poor after
a careful phone scan — blur from hand tremor, glare off glossy prescription
paper, skew from an off-axis overhead camera. Scoring happens BEFORE OCR so
a bad capture gets a spoken re-prompt instead of silently failing extraction
several stages downstream.

Deliberately dependency-light: takes a plain grayscale pixel grid
(`List[List[int]]`, values 0-255) rather than requiring numpy/PIL/OpenCV in
this module. A capture-side adapter (kiosk camera driver) is responsible for
decoding whatever image format it captures into this grid; that adapter is
where a real CV library belongs.

The heuristics here are intentionally simple and documented as such — they
are a placeholder scoring function, not a benchmarked blur/glare/skew
detector. Swap `score_capture`'s internals for a proper CV pipeline
(Laplacian variance via OpenCV, a real deskew estimate, etc.) without
touching the CaptureQualityScore contract or callers.
"""

from typing import List

from ayusetu.ai.clinical.document_ai.contracts import CaptureQualityScore

Grid = List[List[int]]

DEFAULT_BLUR_THRESHOLD = 0.35
DEFAULT_GLARE_THRESHOLD = 0.5
DEFAULT_SKEW_THRESHOLD = 0.3


def _blur_score(grid: Grid) -> float:
    """
    Sharpness proxy: mean absolute discrete 2D Laplacian magnitude over
    interior pixels, normalised to [0, 1]. A blurred image has low-magnitude
    local gradients everywhere (in any orientation); a sharp image has
    strong edges.
    """
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    total = 0.0
    count = 0
    for r in range(1, rows - 1):
        row, up, down = grid[r], grid[r - 1], grid[r + 1]
        for c in range(1, cols - 1):
            laplacian = 4 * row[c] - up[c] - down[c] - row[c - 1] - row[c + 1]
            total += abs(laplacian)
            count += 1
    if count == 0:
        return 0.0
    mean_laplacian = total / count
    # Normalise against a generous ceiling; real edges commonly exceed 80.
    return max(0.0, min(1.0, mean_laplacian / 80.0))


def _glare_score(grid: Grid, saturation_threshold: int = 245) -> float:
    """1.0 = no glare. Penalises the fraction of near-saturated (blown out) pixels."""
    total = 0
    saturated = 0
    for row in grid:
        for px in row:
            total += 1
            if px >= saturation_threshold:
                saturated += 1
    if total == 0:
        return 1.0
    return max(0.0, 1.0 - (saturated / total))


def _skew_score(grid: Grid) -> float:
    """
    1.0 = well-aligned text. Proxy: normalised variance of the row-sum
    projection profile. Horizontal text lines on a level page produce a
    strongly banded (high-variance) row profile; a skewed page smears rows
    into each other and flattens the profile.
    """
    if not grid:
        return 0.0
    row_sums = [sum(row) for row in grid]
    n = len(row_sums)
    mean = sum(row_sums) / n
    if mean == 0:
        return 0.0
    variance = sum((s - mean) ** 2 for s in row_sums) / n
    coeff_of_variation = (variance ** 0.5) / mean
    # A well-banded page typically has CoV well above 0.15; flatten -> low skew score.
    return max(0.0, min(1.0, coeff_of_variation / 0.25))


def score_capture(
    grid: Grid,
    blur_threshold: float = DEFAULT_BLUR_THRESHOLD,
    glare_threshold: float = DEFAULT_GLARE_THRESHOLD,
    skew_threshold: float = DEFAULT_SKEW_THRESHOLD,
) -> CaptureQualityScore:
    blur = _blur_score(grid)
    glare = _glare_score(grid)
    skew = _skew_score(grid)

    reasons = []
    if blur < blur_threshold:
        reasons.append("blurry")
    if glare < glare_threshold:
        reasons.append("glare")
    if skew < skew_threshold:
        reasons.append("skewed")

    return CaptureQualityScore(
        blur_score=blur,
        glare_score=glare,
        skew_score=skew,
        accepted=not reasons,
        rejection_reasons=reasons,
    )
