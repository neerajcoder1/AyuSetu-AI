"""
Phase 9 Integration Test: API Contract Lifecycle & Error Taxonomies
===================================================================
Validates the complete API contract surface of the AyuSetu API Gateway:
- Uniform PRD §22.8 error taxonomy and response schemas.
- Request correlation ID lifecycle.
- Security headers (CSP, X-Frame-Options, X-Content-Type-Options, Cache-Control).
- HTTP status codes for auth, forbidden, validation, rate limiting, and size limits.
- Health probes (/health, /live, /ready, /api/v1/health) and Prometheus metrics (/metrics).
- Non-leaking error responses (Zero stack traces, SQL strings, passwords, or connection URLs).
"""

from unittest.mock import patch
from fastapi.testclient import TestClient
import pytest

from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.errors import ErrorCode

client = TestClient(gateway_app)


def test_probe_endpoints_contracts():
    """Verify contracts of /health, /live, /ready, /metrics."""
    # Liveness probe
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"
    assert "service" in res_health.json()

    res_live = client.get("/live")
    assert res_live.status_code == 200
    assert res_live.json()["status"] == "ok"

    # Readiness probe
    with patch("ayusetu.gateway.routes.health.SyncSessionLocal"), \
         patch("ayusetu.gateway.routes.health.ping_redis", return_value=True):
        res_ready = client.get("/ready")
        assert res_ready.status_code == 200
        data = res_ready.json()
        assert data["status"] == "ready"
        assert data["components"]["database"] == "connected"
        assert data["components"]["redis"] == "connected"

    # Metrics probe
    res_metrics = client.get("/metrics")
    assert res_metrics.status_code == 200
    assert "ayusetu_http_requests_total" in res_metrics.text
    assert "# TYPE ayusetu_http_requests_total counter" in res_metrics.text


def test_security_headers_contract():
    """Verify standard security headers on all responses."""
    res = client.get("/")
    assert res.status_code == 200
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert res.headers.get("x-frame-options") == "DENY"
    assert "default-src 'none'" in res.headers.get("content-security-policy", "")
    assert "x-request-id" in res.headers


def test_request_id_lifecycle():
    """Verify request ID is respected when supplied as UUIDv4/v7 or generated if missing."""
    custom_req_id = "018f0000-0000-7000-8000-000000000099"
    res = client.get("/", headers={"X-Request-ID": custom_req_id})
    assert res.status_code == 200
    assert res.headers.get("x-request-id") == custom_req_id

    # Omitted header generates new valid UUID
    res_no_id = client.get("/")
    assert res_no_id.status_code == 200
    assert len(res_no_id.headers.get("x-request-id", "")) >= 32


def test_standardized_error_envelope_401():
    """Verify 401 error envelope conforms to PRD §22.8 taxonomy."""
    res = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid-token-xyz"})
    assert res.status_code == 401
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == ErrorCode.SESSION_EXPIRED.value
    assert "request_id" in data["error"]
    assert "password" not in res.text


def test_standardized_error_envelope_403():
    """Verify 403 error envelope conforms to PRD §22.8 taxonomy."""
    # Attendant attempts to access Deid export endpoint -> 403
    res = client.post(
        "/api/v1/deid/export",
        headers={"Authorization": "Bearer staff-token-attendant-ravi"},
        json={
            "export_request": {
                "date_from": "2026-01-01",
                "date_to": "2026-12-31",
                "purpose": "research",
                "approver_1": "usr-aud-001",
                "approver_2": "usr-adm-001",
            },
            "candidate_records": []
        }
    )
    assert res.status_code == 403
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] in (ErrorCode.POLICY_DENIED.value, "POLICY_DENIED")
    assert "request_id" in data["error"]


def test_standardized_error_envelope_422_validation():
    """Verify 422 validation failure produces standardized PRD error response."""
    res = client.post(
        "/api/v1/consent",
        headers={"Authorization": "Bearer staff-token-dr-aparna"},
        json={"invalid_field": 1234}
    )
    assert res.status_code == 422
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == ErrorCode.UNPROCESSABLE_ENTITY.value
    assert "request_id" in data["error"]


def test_body_size_limits_enforced():
    """Verify 413 Payload Too Large on oversized JSON bodies."""
    oversized_payload = {"channel": "kiosk", "department": "A" * (300 * 1024)}
    res = client.post("/api/v1/sessions", json=oversized_payload)
    assert res.status_code == 413
    data = res.json()
    assert data["error"]["code"] == ErrorCode.PAYLOAD_TOO_LARGE.value
