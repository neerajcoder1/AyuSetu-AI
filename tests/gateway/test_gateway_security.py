"""
Test Suite: Gateway Security Controls & Hardening
==================================================
Validates security headers, CORS, body size limits, rate limiting, and error taxonomy.
"""

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.errors import ErrorCode, AyuSetuGatewayError
from ayusetu.gateway.middleware.rate_limit import _in_memory_buckets, _in_memory_counters

client = TestClient(gateway_app)


def test_security_headers_present():
    response = client.get("/")
    assert response.status_code == 200
    headers = response.headers

    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "default-src 'none'" in headers.get("Content-Security-Policy", "")
    assert "no-store" in headers.get("Cache-Control", "")
    assert headers.get("Pragma") == "no-cache"


def test_cors_allowed_origin():
    response = client.options(
        "/api/v1/sessions",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, X-Request-ID",
        }
    )
    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
    assert response.headers.get("Access-Control-Allow-Credentials") == "true"


def test_cors_disallowed_origin():
    response = client.options(
        "/api/v1/sessions",
        headers={
            "Origin": "http://malicious-attacker.com",
            "Access-Control-Request-Method": "POST",
        }
    )
    # Disallowed origin does not get Access-Control-Allow-Origin
    assert response.headers.get("Access-Control-Allow-Origin") is None


def test_body_size_limit_json_rejected():
    # 256 KB max for JSON endpoints. Let's send a 300 KB Content-Length header.
    oversized_length = 300 * 1024
    response = client.post(
        "/api/v1/sessions",
        headers={"Content-Length": str(oversized_length)},
        content=b"{}"
    )
    assert response.status_code == 413
    data = response.json()
    assert data["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert "exceeds maximum allowed size" in data["error"]["message"]


def test_rate_limiting_device_exceeded():
    # Clear in-memory rate limiters for test
    _in_memory_buckets.clear()
    _in_memory_counters.clear()

    device_header = {"X-Device-Fingerprint": "kiosk-test-station-01"}
    
    # Send 61 requests rapidly to exceed 60 req/min device limit
    responses = []
    for _ in range(61):
        responses.append(client.get("/api/v1/mpi/candidates", headers=device_header))

    last_response = responses[-1]
    assert last_response.status_code == 429
    data = last_response.json()
    assert data["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in last_response.headers
    assert data["error"]["details"]["limit_type"] == "device"


def test_error_taxonomy_format_on_404():
    response = client.get("/api/v1/unknown-endpoint")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert data["error"]["request_id"] is not None


def test_validation_error_format_on_invalid_payload():
    # Submit missing required field 'confirmed_by'
    response = client.post("/api/v1/sessions/018f0000-0000-0000-0000-000000000000/submit", json={})
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "UNPROCESSABLE_ENTITY"
    assert isinstance(data["error"]["details"], list)
    assert len(data["error"]["details"]) > 0


def test_unhandled_exception_safe_handling():
    # Simulate an internal unexpected error in an endpoint handler
    with patch("ayusetu.gateway.routes.stubs.session_cache.create_session", side_effect=RuntimeError("Secret DB Connection String details: postgresql://admin:supersecret@10.0.0.1")):
        response = client.post("/api/v1/sessions", json={})
        assert response.status_code == 500
        data = response.json()
        assert data["error"]["code"] == "INTERNAL_ERROR"
        # Verify no secret, stack trace or DB details leaked
        assert "supersecret" not in response.text
        assert "RuntimeError" not in response.text
        assert "Traceback" not in response.text
        assert data["error"]["message"] == "An unexpected internal server error occurred. Please try again later."


def test_separation_of_duties_export_policy_denied():
    # Same person cannot be both approver 1 and approver 2 per PRD §21.4
    headers = {"Authorization": "Bearer staff-token-mrd-officer"}
    response = client.post("/api/v1/exports", headers=headers, json={
        "date_from": "2026-01-01",
        "date_to": "2026-09-01",
        "approver_1": "usr-mrd-001",
        "approver_2": "usr-mrd-001"  # Same user!
    })
    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "POLICY_DENIED"
    assert "Separation of Duties" in data["error"]["message"]
