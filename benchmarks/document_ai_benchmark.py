"""
AyuSetu Appendix C.2 — Document AI / OCR Gold Benchmark Harness
===============================================================
Authoritative evaluation runner measuring Entity Precision, Recall,
and F1 across 200 documents (100 printed, 100 handwritten) per PRD v3 §23.2 AC-B2-1.
Target: F1 >= 0.92.

NOTE: When raw gold image dataset is unmounted, reports 'HARNESS READY — DATASET NOT EXECUTED'.
"""

from typing import Any, Dict, List, Optional, Set
from ayusetu.ai.clinical.document_ai.entity_extractor import extract_entities


class DocumentAIBenchmarkHarness:
    """Appendix C.2 Document AI gold-set benchmark."""

    def __init__(self, target_f1: float = 0.92):
        self.target_f1 = target_f1

    def run_benchmark(self, gold_dataset: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Evaluate OCR entity extraction against gold annotations.
        """
        if not gold_dataset:
            return {
                "status": "HARNESS READY — DATASET NOT EXECUTED",
                "target_f1": self.target_f1,
                "gold_set_specification": {
                    "total_documents": 200,
                    "printed_prescriptions": 100,
                    "handwritten_prescriptions": 100,
                    "target_entity_types": ["medication", "allergy", "vital", "condition", "lab"],
                },
            }

        total_tp = 0
        total_fp = 0
        total_fn = 0

        for doc in gold_dataset:
            text = doc.get("raw_text", "")
            gold_entities: Set[str] = set(doc.get("gold_entities", []))

            # Run actual repo entity extractor
            predicted = extract_entities(text)
            pred_entities: Set[str] = set()
            for e in predicted:
                val = e.normalised or e.raw_text
                if isinstance(val, dict):
                    for v in val.values():
                        pred_entities.add(str(v))
                elif val:
                    pred_entities.add(str(val))

            tp = len(gold_entities.intersection(pred_entities))
            fp = len(pred_entities - gold_entities)
            fn = len(gold_entities - pred_entities)


            total_tp += tp
            total_fp += fp
            total_fn += fn

        precision = total_tp / max(1, (total_tp + total_fp))
        recall = total_tp / max(1, (total_tp + total_fn))
        f1 = (2 * precision * recall) / max(1e-6, (precision + recall))

        return {
            "status": "EXECUTED",
            "document_count": len(gold_dataset),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "target_f1": self.target_f1,
            "meets_target": f1 >= self.target_f1,
        }
