"""
OCR provider abstraction.

Kept provider-agnostic (same pattern as ayusetu.ai.conversation.llm_provider)
so the kiosk's Tesseract/cloud-OCR choice is swappable without touching the
entity extraction layer that consumes OCRResult.
"""

from typing import Protocol

from ayusetu.ai.clinical.document_ai.contracts import OCRResult


class OCRProvider(Protocol):
    def run(self, image_path: str, page_no: int = 1) -> OCRResult:
        ...


class TesseractOCRProvider:
    """
    Thin wrapper around pytesseract. Import is deferred so this module can be
    imported (and the rest of the package used/tested) in environments that
    don't have tesseract installed, e.g. CI containers or unit tests that
    exercise entity extraction against fixture text directly.
    """

    def __init__(self, lang: str = "eng+hin"):
        self.lang = lang

    def run(self, image_path: str, page_no: int = 1) -> OCRResult:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as e:
            raise RuntimeError(
                "TesseractOCRProvider requires the 'pytesseract' and 'Pillow' "
                "packages and the tesseract binary. Install them or use "
                "MockOCRProvider / another OCRProvider for testing."
            ) from e

        image = Image.open(image_path)
        data = pytesseract.image_to_data(image, lang=self.lang, output_type=pytesseract.Output.DICT)

        words = [w for w in data.get("text", []) if w.strip()]
        confidences = [
            float(c) for c, w in zip(data.get("conf", []), data.get("text", [])) if w.strip() and float(c) >= 0
        ]
        mean_confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0

        return OCRResult(
            page_no=page_no,
            raw_text=" ".join(words),
            mean_confidence=max(0.0, min(1.0, mean_confidence)),
        )


class MockOCRProvider:
    """
    Deterministic OCR provider for tests and offline development: returns
    pre-canned text keyed by image_path instead of touching any image
    library or the tesseract binary.
    """

    def __init__(self, fixtures: dict[str, str], confidence: float = 0.9):
        self.fixtures = fixtures
        self.confidence = confidence

    def run(self, image_path: str, page_no: int = 1) -> OCRResult:
        return OCRResult(
            page_no=page_no,
            raw_text=self.fixtures.get(image_path, ""),
            mean_confidence=self.confidence,
        )
