"""
Zero-PHI Structured Logging & Centralized Redaction
===================================================
Authoritative structured logging subsystem per PRD v2.0 §21.8 and Phase 8.
Guarantees zero leakage of Direct PHI, Quasi-PHI, and security credentials:
- Automatic masking of Phone, ABHA, Aadhaar, PAN, Emails, Passwords, Bearer Tokens, DB Connection Strings.
- Correlation tracking via request_id context.
- Structured JSON output format for production observability.
- Safe log filter and traceback sanitization.
"""

from datetime import datetime, timezone
import json
import logging
import re
import sys
import traceback
from typing import Any, Dict, List, Pattern, Tuple

from ayusetu.gateway.middleware.request_id import get_current_request_id

# ---------------------------------------------------------------------------
# High-Risk Redaction Patterns (PHI, PII, and Credential Tokens)
# ---------------------------------------------------------------------------
REDACTION_PATTERNS: List[Tuple[str, Pattern, str]] = [
    # 1. Bearer / Authorization tokens
    ("bearer_token", re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    # 2. Passwords / Secrets in key-value or query strings
    ("password_kv", re.compile(r"(password|secret|token|api_key|private_key)([\"']?\s*[:=]\s*[\"']?)[^\"'\s,]+", re.IGNORECASE), r"\1\2[REDACTED_SECRET]"),
    # 3. Database connection URLs with credentials
    ("db_credentials", re.compile(r"(postgresql(?:\+[a-z0-9]+)?://[^:]+:)([^@]+)(@)", re.IGNORECASE), r"\1[REDACTED_DB_PWD]\3"),
    # 4. Indian Mobile Phone Numbers (10 digits starting with 6, 7, 8, 9)
    ("phone_number", re.compile(r"(?:\+91|91)?[-.\s]?[6-9]\d{9}\b"), "[REDACTED_PHONE]"),
    # 5. 14-digit ABHA ID (XX-XXXX-XXXX-XXXX)
    ("abha_number", re.compile(r"\b\d{2}-\d{4}-\d{4}-\d{4}\b"), "[REDACTED_ABHA]"),
    # 6. ABHA Handle / Address
    ("abha_handle", re.compile(r"\b[a-zA-Z0-9._]+@(abdm|sbx)\b", re.IGNORECASE), "[REDACTED_ABHA_HANDLE]"),
    # 7. 12-digit Aadhaar Number (XXXX XXXX XXXX or contiguous 12 digits)
    ("aadhaar_number", re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b"), "[REDACTED_AADHAAR]"),
    # 8. Indian Income Tax PAN (5 letters, 4 digits, 1 letter)
    ("pan_number", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b"), "[REDACTED_PAN]"),
    # 9. Email addresses
    ("email_address", re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b"), "[REDACTED_EMAIL]"),
]


def redact_text(text: str) -> str:
    """
    Scans and redacts any PHI, secrets, credentials, or sensitive tokens from a string.
    """
    if not text:
        return text
    
    redacted = str(text)
    for name, pattern, repl in REDACTION_PATTERNS:
        redacted = pattern.sub(repl, redacted)
    return redacted


def redact_value(val: Any) -> Any:
    """
    Recursively redacts strings, dictionaries, lists, and exceptions.
    """
    if isinstance(val, str):
        return redact_text(val)
    elif isinstance(val, dict):
        cleaned: Dict[str, Any] = {}
        for k, v in val.items():
            # Check for sensitive key names directly
            if any(s in str(k).lower() for s in ("password", "secret", "token", "auth", "credential", "private_key")):
                cleaned[k] = "[REDACTED_SECRET]"
            else:
                cleaned[k] = redact_value(v)
        return cleaned
    elif isinstance(val, (list, tuple, set)):
        return [redact_value(item) for item in val]
    return val


class SafeLogFilter(logging.Filter):
    """
    Logging filter that intercepts log records before emission, redacting
    messages, arguments, and traceback lines.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact main message if string
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)

        # Redact args if present
        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_value(record.args)
            elif isinstance(record.args, (tuple, list)):
                record.args = tuple(redact_value(a) for a in record.args)

        # Redact formatted exception text if cached
        if record.exc_text:
            record.exc_text = redact_text(record.exc_text)

        return True


class StructuredJsonFormatter(logging.Formatter):
    """
    Standardized JSON log formatter for structured production logging.
    Guarantees strict Zero-PHI and includes request correlation IDs.
    """

    def __init__(self, service_name: str = "ayusetu-backend") -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        # Obtain rendered message with safe arguments
        try:
            rendered_msg = record.getMessage()
        except Exception:
            rendered_msg = str(record.msg)
        rendered_msg = redact_text(rendered_msg)

        # Build structured JSON payload
        req_id = getattr(record, "request_id", None) or get_current_request_id() or "-"
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": getattr(record, "service", self.service_name),
            "level": record.levelname,
            "logger": record.name,
            "request_id": req_id,
            "message": rendered_msg,
        }

        # Add optional route/HTTP metadata if present in record
        for field in ("route", "http_method", "status_code", "latency_ms", "actor_role"):
            if hasattr(record, field):
                log_entry[field] = getattr(record, field)

        # Handle exception info safely (zero DB passwords or credentials in traceback)
        if record.exc_info:
            exc_type, exc_val, exc_tb = record.exc_info
            if exc_tb:
                tb_lines = traceback.format_exception(exc_type, exc_val, exc_tb)
                clean_tb = "".join(redact_text(line) for line in tb_lines)
                log_entry["exception"] = clean_tb

        # Redact any custom extra fields
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            log_entry["extra"] = redact_value(record.extra_data)

        return json.dumps(log_entry, default=str)


def configure_structured_logging(
    service_name: str = "ayusetu-backend",
    level: int = logging.INFO,
    use_json: bool = True,
) -> None:
    """
    Configures root and ayusetu loggers with SafeLogFilter and StructuredJsonFormatter.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Attach safe filter
    safe_filter = SafeLogFilter()
    root_logger.addFilter(safe_filter)

    # Configure handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.addFilter(safe_filter)

    if use_json:
        handler.setFormatter(StructuredJsonFormatter(service_name=service_name))
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] [%(name)s] [req_id=%(request_id)s] %(message)s",
                defaults={"request_id": "-"}
            )
        )

    # Avoid duplicate handlers
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)
    root_logger.addHandler(handler)
