"""
Ephemeral Session Cache (Redis)
===============================
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


class SessionCache:
    """Synchronous Session Cache operations."""

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
        client = get_redis_client()
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

        # Store session payload and token mapping
        key = f"{SESSION_PREFIX}{sess_id}"
        token_key = f"{TOKEN_PREFIX}{token}"
        
        pipeline = client.pipeline()
        pipeline.setex(key, self.ttl_seconds, json.dumps(session_data))
        pipeline.setex(token_key, self.ttl_seconds, sess_id)
        pipeline.execute()

        return session_data

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session data if not expired."""
        client = get_redis_client()
        raw = client.get(f"{SESSION_PREFIX}{session_id}")
        if not raw:
            return None
        return json.loads(raw)

    def update_session(self, session_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update session data and refresh TTL if active."""
        client = get_redis_client()
        key = f"{SESSION_PREFIX}{session_id}"
        raw = client.get(key)
        if not raw:
            return None
        data = json.loads(raw)
        data.update(updates)
        data["last_active_at"] = datetime.now(timezone.utc).isoformat()
        client.setex(key, self.ttl_seconds, json.dumps(data))
        return data

    def panic_clear(self, session_id: str) -> bool:
        """
        Immediately delete session and associated tokens per PRD §21.6.
        Target under 2 seconds.
        """
        client = get_redis_client()
        key = f"{SESSION_PREFIX}{session_id}"
        raw = client.get(key)
        if not raw:
            return False
        
        data = json.loads(raw)
        token = data.get("token")
        
        pipeline = client.pipeline()
        pipeline.delete(key)
        if token:
            pipeline.delete(f"{TOKEN_PREFIX}{token}")
        pipeline.execute()
        return True


class AsyncSessionCache:
    """Asynchronous Session Cache operations."""

    def __init__(self, ttl_seconds: Optional[int] = None):
        self.ttl_seconds = ttl_seconds or (settings.SESSION_TTL_MINUTES * 60)

    async def create_session(
        self,
        encounter_id: uuid.UUID,
        patient_id: Optional[uuid.UUID] = None,
        channel: str = "kiosk",
        device_fingerprint: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        client = get_async_redis_client()
        sess_id = session_id or str(uuid.uuid4())
        token = SessionCache.generate_token()
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

        key = f"{SESSION_PREFIX}{sess_id}"
        token_key = f"{TOKEN_PREFIX}{token}"

        async with client.pipeline(transaction=True) as pipe:
            pipe.setex(key, self.ttl_seconds, json.dumps(session_data))
            pipe.setex(token_key, self.ttl_seconds, sess_id)
            await pipe.execute()

        return session_data

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        client = get_async_redis_client()
        raw = await client.get(f"{SESSION_PREFIX}{session_id}")
        if not raw:
            return None
        return json.loads(raw)

    async def panic_clear(self, session_id: str) -> bool:
        client = get_async_redis_client()
        key = f"{SESSION_PREFIX}{session_id}"
        raw = await client.get(key)
        if not raw:
            return False
        
        data = json.loads(raw)
        token = data.get("token")
        
        async with client.pipeline(transaction=True) as pipe:
            pipe.delete(key)
            if token:
                pipe.delete(f"{TOKEN_PREFIX}{token}")
            await pipe.execute()
        return True
