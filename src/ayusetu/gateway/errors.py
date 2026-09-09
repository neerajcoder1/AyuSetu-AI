"""
AyuSetu Error Taxonomy
======================
Authoritative error codes and HTTP mappings defined in PRD v2.0 §22.8.
"""

from enum import Enum
from typing import Any, Dict, Optional
from fastapi import HTTPException


class ErrorCode(str, Enum):
    # PRD §22.8 Domain Error Codes
    ASR_UNAVAILABLE = "ASR_UNAVAILABLE"               # 503
    ASR_LOW_CONFIDENCE = "ASR_LOW_CONFIDENCE"         # 200 (re-ask closed)
    DOC_QUALITY_REJECTED = "DOC_QUALITY_REJECTED"     # 422
    DOC_PARSE_FAILED = "DOC_PARSE_FAILED"             # 422
    CONSENT_REQUIRED = "CONSENT_REQUIRED"             # 403
    SESSION_EXPIRED = "SESSION_EXPIRED"               # 401
    MPI_AMBIGUOUS = "MPI_AMBIGUOUS"                   # 409
    ABDM_UNAVAILABLE = "ABDM_UNAVAILABLE"             # 503
    TERMINOLOGY_UNRESOLVED = "TERMINOLOGY_UNRESOLVED" # 200
    RATE_LIMITED = "RATE_LIMITED"                     # 429
    GATE_REJECTED = "GATE_REJECTED"                   # 200
    POLICY_DENIED = "POLICY_DENIED"                   # 403

    # Standard Gateway / Platform Error Codes
    BAD_REQUEST = "BAD_REQUEST"                       # 400
    NOT_FOUND = "NOT_FOUND"                           # 404
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"           # 413
    UNPROCESSABLE_ENTITY = "UNPROCESSABLE_ENTITY"     # 422
    INTERNAL_ERROR = "INTERNAL_ERROR"                 # 500
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"       # 503


ERROR_HTTP_STATUS_MAP: Dict[ErrorCode, int] = {
    ErrorCode.ASR_UNAVAILABLE: 503,
    ErrorCode.ASR_LOW_CONFIDENCE: 200,
    ErrorCode.DOC_QUALITY_REJECTED: 422,
    ErrorCode.DOC_PARSE_FAILED: 422,
    ErrorCode.CONSENT_REQUIRED: 403,
    ErrorCode.SESSION_EXPIRED: 401,
    ErrorCode.MPI_AMBIGUOUS: 409,
    ErrorCode.ABDM_UNAVAILABLE: 503,
    ErrorCode.TERMINOLOGY_UNRESOLVED: 200,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.GATE_REJECTED: 200,
    ErrorCode.POLICY_DENIED: 403,
    ErrorCode.BAD_REQUEST: 400,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.PAYLOAD_TOO_LARGE: 413,
    ErrorCode.UNPROCESSABLE_ENTITY: 422,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.SERVICE_UNAVAILABLE: 503,
}


class AyuSetuGatewayError(HTTPException):
    """Structured Gateway exception mapped to PRD §22.8 error taxonomy."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: Optional[int] = None,
        details: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        final_status = status_code or ERROR_HTTP_STATUS_MAP.get(code, 500)
        super().__init__(status_code=final_status, detail=message, headers=headers)
        self.code = code
        self.message = message
        self.details = details
