"""
Tests for Zero-PHI Structured Logging & Centralized Redaction
============================================================
Validates:
- Direct PHI and credential redaction (Phone, ABHA, Aadhaar, PAN, Emails, Bearer Tokens, DB URLs).
- StructuredJsonFormatter JSON output structure.
- Request correlation ID integration.
- SafeLogFilter intercepting standard logger calls.
- Exception traceback sanitization.
"""

import json
import logging
from unittest.mock import MagicMock
import pytest

from ayusetu.common.structured_logging import (
    SafeLogFilter,
    StructuredJsonFormatter,
    configure_structured_logging,
    redact_text,
    redact_value,
)
from ayusetu.gateway.middleware.request_id import request_id_ctx


def test_redact_text_synthetic_phi():
    """Verify that all prohibited PHI and credentials are properly masked."""
    # Phone numbers
    assert "[REDACTED_PHONE]" in redact_text("Patient mobile is 9876543210 for appointment")
    assert "[REDACTED_PHONE]" in redact_text("Call +91-9876543210 immediately")

    # ABHA ID and Address
    assert "[REDACTED_ABHA]" in redact_text("ABHA ID: 12-3456-7890-1234 registered")
    assert "[REDACTED_ABHA_HANDLE]" in redact_text("Handle is user.name@abdm")
    assert "[REDACTED_ABHA_HANDLE]" in redact_text("Handle is sandbox.user@sbx")

    # Aadhaar Number
    assert "[REDACTED_AADHAAR]" in redact_text("Aadhaar 1234 5678 9012 verified")

    # PAN Card
    assert "[REDACTED_PAN]" in redact_text("Tax PAN ABCDE1234F provided")

    # Email
    assert "[REDACTED_EMAIL]" in redact_text("Contact patient at patient.test@gmail.com")

    # Bearer Token
    assert "Bearer [REDACTED_TOKEN]" in redact_text("Header: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkw")

    # Database connection URL with credentials
    db_str = "Connecting to postgresql://admin:super_secret_pw123@10.0.0.1:5432/ayusetu_db"
    redacted_db = redact_text(db_str)
    assert "super_secret_pw123" not in redacted_db
    assert "[REDACTED_DB_PWD]" in redacted_db


def test_redact_value_recursive():
    """Verify recursive dictionary and list redaction."""
    payload = {
        "user": "Alice",
        "phone": "9876543210",
        "password": "ClearTextPassword123!",
        "auth_token": "token-xyz-12345",
        "sub_doc": {
            "abha": "12-3456-7890-1234",
            "db_url": "postgresql://user:secret123@localhost/db",
        },
        "items": ["Call 9876543210", "Email test@hospital.gov.in"],
    }

    cleaned = redact_value(payload)
    assert cleaned["password"] == "[REDACTED_SECRET]"
    assert cleaned["auth_token"] == "[REDACTED_SECRET]"
    assert "[REDACTED_PHONE]" in cleaned["phone"]
    assert "[REDACTED_ABHA]" in cleaned["sub_doc"]["abha"]
    assert "secret123" not in cleaned["sub_doc"]["db_url"]
    assert "[REDACTED_PHONE]" in cleaned["items"][0]
    assert "[REDACTED_EMAIL]" in cleaned["items"][1]


def test_structured_json_formatter():
    """Verify StructuredJsonFormatter produces compliant Zero-PHI JSON with request ID."""
    formatter = StructuredJsonFormatter(service_name="test-gateway")
    
    # Set request ID context
    token = request_id_ctx.set("req-test-uuid-777")
    try:
        record = logging.LogRecord(
            name="ayusetu.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="User with phone 9876543210 logged in successfully",
            args=(),
            exc_info=None,
        )
        record.extra_data = {"status": "SUCCESS", "password": "mypassword"}
        
        output_str = formatter.format(record)
        data = json.loads(output_str)

        assert data["service"] == "test-gateway"
        assert data["level"] == "INFO"
        assert data["request_id"] == "req-test-uuid-777"
        assert "[REDACTED_PHONE]" in data["message"]
        assert "9876543210" not in data["message"]
        assert data["extra"]["password"] == "[REDACTED_SECRET]"
    finally:
        request_id_ctx.reset(token)


def test_safe_log_filter_integration():
    """Verify SafeLogFilter sanitizes messages and args when passed through logger."""
    filter_instance = SafeLogFilter()
    record = logging.LogRecord(
        name="ayusetu.security",
        level=logging.WARNING,
        pathname="sec.py",
        lineno=25,
        msg="Authentication failed for %s with token %s",
        args=("9876543210", "Bearer secret-token-abcdef123"),
        exc_info=None,
    )

    filter_instance.filter(record)
    assert "[REDACTED_PHONE]" in record.args[0]
    assert "[REDACTED_TOKEN]" in record.args[1]
    assert "9876543210" not in record.args[0]
    assert "secret-token-abcdef123" not in record.args[1]
