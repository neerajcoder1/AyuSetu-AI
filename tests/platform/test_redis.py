"""
Test Suite: Redis Ephemeral Session Cache
=========================================
Validates session creation, 30-minute TTL, retrieval, token generation, and panic-clear.
"""

from unittest.mock import MagicMock, patch
import uuid
import pytest
from ayusetu.common.session_cache import SessionCache, SESSION_PREFIX, TOKEN_PREFIX


def test_session_token_generation():
    token1 = SessionCache.generate_token()
    token2 = SessionCache.generate_token()
    assert len(token1) == 64  # 32 bytes hex encoded = 64 characters (256-bit)
    assert token1 != token2


def test_session_cache_flow_with_mock():
    mock_redis = MagicMock()
    stored_data = {}

    def mock_set(key, value, ex=None):
        stored_data[key] = value

    def mock_get(key):
        return stored_data.get(key)

    def mock_delete(key):
        stored_data.pop(key, None)

    mock_pipeline = MagicMock()
    mock_pipeline.set.side_effect = mock_set
    mock_pipeline.delete.side_effect = mock_delete
    mock_redis.pipeline.return_value = mock_pipeline
    mock_redis.get.side_effect = mock_get
    mock_redis.set.side_effect = mock_set

    with patch("ayusetu.common.session_cache.get_redis_client", return_value=mock_redis):
        cache = SessionCache(ttl_seconds=1800)  # 30 min
        encounter_id = uuid.uuid4()
        patient_id = uuid.uuid4()

        # 1. Create Session
        created = cache.create_session(
            encounter_id=encounter_id,
            patient_id=patient_id,
            channel="kiosk"
        )
        session_id = created["session_id"]
        assert created["status"] == "IDENTIFY"
        assert created["ttl_seconds"] == 1800
        assert created["token"] is not None

        # 2. Retrieve Session
        retrieved = cache.get_session(session_id)
        assert retrieved is not None
        assert retrieved["encounter_id"] == str(encounter_id)

        # 3. Update Session
        updated = cache.update_session(session_id, {"status": "INTERVIEW"})
        assert updated["status"] == "INTERVIEW"

        # 4. Panic Clear (under 2s revocation)
        cleared = cache.panic_clear(session_id)
        assert cleared is True
        assert cache.get_session(session_id) is None
