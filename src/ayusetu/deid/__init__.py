"""
AyuSetu De-Identification & Secure Export Module
================================================
Implements PRD v2.0 §21.4 and §21.9:
- Declarative 18+ identifier policy (direct suppression & quasi-identifier transformation).
- District population >= 20,000 threshold evaluation with State aggregation.
- Per-patient consistent cryptographically secure random date shifting in [-30, +30] days.
- Age banding with 90+ capping.
- Strict k-anonymity (k >= 5) over defined quasi-identifier equivalence classes.
- Zero-PHI export pre-release safety gate.
- Two-person authorization (Separation of Duties).
- DPDP purpose-bound consent gating & immutable PostgreSQL audit logging.
"""

from ayusetu.deid.service import DeidExportService, deid_export_service

__all__ = ["DeidExportService", "deid_export_service"]
