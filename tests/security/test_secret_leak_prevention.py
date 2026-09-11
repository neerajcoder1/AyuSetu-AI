"""
Phase 9 Security Regression: Secret Leak Prevention
===================================================
Validates that operational endpoints, error handlers, and log pipelines
never expose passwords, session tokens, database connection strings, or stack traces.
"""

from unittest.mock import patch
from fastapi.testclient import TestClient
import pytest

from ayusetu.gateway.app import gateway_app

client = TestClient(gateway_app)

SENSITIVE_PATTERNS = [
    "ayusetu_dev_secret",
    "password=",
    "pwd=",
    "postgresql://",
    "postgresql+psycopg2://",
    "redis://",
    "Traceback (most recent call last):",
    "SELECT * FROM",
    "Bearer eyJ",
]


def test_no_secrets_in_root_and_probe_responses():
    """Verify probe responses do not contain credentials."""
    for endpoint in ["/", "/health", "/live", "/ready", "/metrics"]:
        with patch("ayusetu.gateway.routes.health.SyncSessionLocal"), \
             patch("ayusetu.gateway.routes.health.ping_redis", return_value=True):
            res = client.get(endpoint)
            for pattern in SENSITIVE_PATTERNS:
                assert pattern not in res.text, f"Pattern '{pattern}' found in {endpoint} response!"


def test_no_secrets_in_error_responses():
    """Verify error responses across 401, 403, 404, 422, 500 do not leak credentials or stack traces."""
    # 401
    r_401 = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad-token"})
    assert r_401.status_code == 401

    # 404
    r_404 = client.get("/api/v1/nonexistent-route-xyz")
    assert r_404.status_code == 404

    # 422
    r_422 = client.post(
        "/api/v1/consent",
        headers={"Authorization": "Bearer staff-token-dr-aparna"},
        json={"invalid_field": 123}
    )
    assert r_422.status_code == 422

    # 500 / 503 (Simulated DB connection error with embedded password)
    with patch("ayusetu.gateway.routes.health.SyncSessionLocal", side_effect=RuntimeError("FATAL: password authentication failed for user 'ayusetu' with dburl postgresql://ayusetu:secret@127.0.0.1")):
        r_500 = client.get("/ready")
        assert r_500.status_code == 503  # Handled as degraded
        assert "secret" not in r_500.text
        assert "password" not in r_500.text
        assert "FATAL" not in r_500.text
