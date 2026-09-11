"""
Tests for Operational Telemetry & Prometheus Metrics
=====================================================
Validates:
- Metrics registry recording counters and histograms.
- Strict low-cardinality path normalization (no raw UUIDs or tokens as labels).
- Prometheus text exposition format (version 0.0.4).
- JSON metrics snapshot endpoint.
- Zero-PHI in metric label sets.
- REST endpoints /metrics and /api/v1/metrics.
"""

from fastapi.testclient import TestClient
import pytest

from ayusetu.common.metrics import (
    MetricsRegistry,
    metrics_registry,
    normalize_route_path,
)
from ayusetu.gateway.app import gateway_app

client = TestClient(gateway_app)


def test_route_path_normalization():
    """Verify variable identifiers are converted to static tokens to prevent high-cardinality label explosions."""
    # UUID replacement
    raw_uuid_path = "/api/v1/sessions/018f0000-0000-7000-8000-000000000011/consent"
    assert normalize_route_path(raw_uuid_path) == "/api/v1/sessions/{id}/consent"

    # Hex token replacement
    raw_token_path = "/pwa/companion/8ddcaad0f45249edb76e78b115c4655b"
    assert normalize_route_path(raw_token_path) == "/pwa/companion/{token}"

    # Query params stripped
    raw_query = "/api/v1/audit/events?from_seq=1&limit=50"
    assert normalize_route_path(raw_query) == "/api/v1/audit/events"


def test_metrics_registry_recording_and_exposition():
    """Verify registry counts, histograms, and Prometheus text generation."""
    reg = MetricsRegistry()

    # Record HTTP requests
    reg.record_http_request("GET", "/api/v1/health", 200, 0.015)
    reg.record_http_request("POST", "/api/v1/sessions/018f0000-0000-7000-8000-000000000011/identify", 200, 0.045)
    reg.record_http_request("POST", "/api/v1/sessions/018f0000-0000-7000-8000-000000000022/identify", 200, 0.050)
    
    # Record security events
    reg.record_security_event("AUTH_FAILED", "DENY")
    reg.record_security_event("IDOR_ATTEMPT", "DENY")

    # Record red flag and deid telemetry
    reg.record_redflag_trigger(1, "RF-CARD-001")
    reg.record_deid_export("research", "ALLOW")

    # Generate Prometheus text format
    prom_text = reg.generate_prometheus_text()
    
    assert "ayusetu_http_requests_total" in prom_text
    assert 'method="GET",path="/api/v1/health",status="200"' in prom_text
    assert 'method="POST",path="/api/v1/sessions/{id}/identify",status="200"' in prom_text
    # Ensure no raw UUID in metric output
    assert "018f0000" not in prom_text

    assert 'event_type="AUTH_FAILED"' in prom_text
    assert 'outcome="DENY"' in prom_text
    assert 'rule_id="RF-CARD-001"' in prom_text
    assert 'tier="1"' in prom_text
    assert 'purpose="research"' in prom_text
    assert 'outcome="ALLOW"' in prom_text


def test_metrics_endpoints_via_client():
    """Verify /metrics and /metrics/json HTTP endpoints."""
    # 1. Prometheus text format
    res_prom = client.get("/metrics")
    assert res_prom.status_code == 200
    assert "text/plain" in res_prom.headers["content-type"]
    assert "ayusetu_http_requests_total" in res_prom.text

    # 2. JSON snapshot format
    res_json = client.get("/metrics/json")
    assert res_json.status_code == 200
    data = res_json.json()
    assert "counters" in data
    assert "histograms" in data


def test_api_v1_metrics_alias():
    """Verify /api/v1/metrics alias."""
    res = client.get("/api/v1/metrics")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
