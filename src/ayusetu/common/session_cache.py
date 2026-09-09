"""
Ephemeral Session Cache (Redis with In-Memory Fallback)
=======================================================
Manages in-memory ephemeral session state with 30-minute authority TTL per PRD v2.0 §7.2, §21.6 & §22.4.
Provides panic-clear revocation (<2s) and encounter binding.
"""

import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid

from ayusetu.common.config import settings
from ayusetu.common.redis_client import get_redis_client, get_async_redis_client

SESSION_PREFIX = "ayusetu:session:"
TOKEN_PREFIX = "ayusetu:token:"

# In-memory session store when Redis is unavailable (e.g. offline kiosks / unit tests)
_in_memory_sessions: Dict[str, Dict[str, Any]] = {}
_in_memory_tokens: Dict[str, str] = {}


class SessionCache:
    """Session Cache operations with automatic Redis & in-memory resilience."""

    def __init__(self, ttl_seconds: Optional[int] = None):
        self.ttl_seconds = ttl_seconds or (settings.SESSION_TTL_MINUTES * 60)

    @classmethod
    def generate_token(cls) -> str:
        """Generate opaque 256-bit (32 bytes = 64 hex chars) secure token per PRD §21.6."""
        return secrets.token_hex(32)

    def create_session(
        self,
        encounter_id: uuid.UUID,
        patient_id: Optional[uuid.UUID] = None,
        channel: str = "kiosk",
        device_fingerprint: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new ephemeral session state bound to encounter and device fingerprint."""
        sess_id = session_id or str(uuid.uuid4())
        token = self.generate_token()
        now_iso = datetime.now(timezone.utc).isoformat()

        session_data = {
            "session_id": sess_id,
            "encounter_id": str(encounter_id),
            "patient_id": str(patient_id) if patient_id else None,
            "token": token,
            "channel": channel,
            "status": "IDENTIFY",
            "device_fingerprint": device_fingerprint,
            "created_at": now_iso,
            "last_active_at": now_iso,
            "ttl_seconds": self.ttl_seconds
        }

        # Store session payload and token mapping in Redis or In-Memory
        key = f"{SESSION_PREFIX}{sess_id}"
        token_key = f"{TOKEN_PREFIX}{token}"
        
        try:
            client = get_redis_client()
            pipeline = client.pipeline()
            pipeline.set(key, json.dumps(session_data), ex=self.ttl_seconds)
            pipeline.set(token_key, sess_id, ex=self.ttl_seconds)
            pipeline.execute()
        except Exception:
            _in_memory_sessions[sess_id] = session_data
            _in_memory_tokens[token] = sess_id

        return session_data

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session data if not expired."""
        try:
            client = get_redis_client()
            raw = client.get(f"{SESSION_PREFIX}{session_id}")
            if not raw:
                return _in_memory_sessions.get(session_id)
            return json.loads(raw)
        except Exception:
            return _in_memory_sessions.get(session_id)

    def update_session(self, session_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update session data and refresh TTL if active."""
        data = self.get_session(session_id)
        if not data:
            return None
        data.update(updates)
        data["last_active_at"] = datetime.now(timezone.utc).isoformat()

        key = f"{SESSION_PREFIX}{session_id}"
        try:
            client = get_redis_client()
            client.set(key, json.dumps(data), ex=self.ttl_seconds)
        except Exception:
            _in_memory_sessions[session_id] = data
        return data

    def panic_clear(self, session_id: str) -> bool:
        """
        Immediately delete session and associated tokens per PRD §21.6.
        Target under 2 seconds.
        """
        data = self.get_session(session_id)
        if not data:
            return False
        
        token = data.get("token")
        key = f"{SESSION_PREFIX}{session_id}"
        
        try:
            client = get_redis_client()
            pipeline = client.pipeline()
            pipeline.delete(key)
            if token:
                pipeline.delete(f"{TOKEN_PREFIX}{token}")
            pipeline.execute()
        except Exception:
            pass

        _in_memory_sessions.pop(session_id, None)
        if token:
            _in_memory_tokens.pop(token, None)

        return True
