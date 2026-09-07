"""
Test Suite: Health and Readiness Endpoints
==========================================
Validates /health, /ready, and /api/v1/health endpoints.
"""

from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from ayusetu.api.main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "AyuSetu Platform API"
    assert data["status"] == "running"


def test_liveness_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "ayusetu-backend"


def test_readiness_all_healthy():
    mock_session = MagicMock()
    mock_session.__enter__.return_value = mock_session
    mock_session.execute.return_value = None

    with patch("ayusetu.api.health.SyncSessionLocal", return_value=mock_session), \
         patch("ayusetu.api.health.ping_redis", return_value=True):
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["components"]["database"] == "connected"
        assert data["components"]["redis"] == "connected"


def test_readiness_degraded_when_db_down():
    with patch("ayusetu.api.health.SyncSessionLocal", side_effect=Exception("DB Connection Refused")), \
         patch("ayusetu.api.health.ping_redis", return_value=True):
        response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["components"]["database"] == "unreachable"
        assert data["components"]["redis"] == "connected"


def test_api_v1_health_alias():
    with patch("ayusetu.api.health.SyncSessionLocal") as mock_db, \
         patch("ayusetu.api.health.ping_redis", return_value=True):
        mock_sess = MagicMock()
        mock_sess.__enter__.return_value = mock_sess
        mock_db.return_value = mock_sess

        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
