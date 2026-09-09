"""
Gateway Rate Limiting Middleware
================================
Enforces rate limits per PRD v2.0 §21.6 using Redis with an in-memory fallback.
Limits:
  - Per device: 60 req/min sustained, 120 burst
  - Per IP (PWA): 30 req/min
  - Per session: 300 total requests
  - Document uploads: 20 per session
"""

import hashlib
import secrets
import time
from typing import Optional, Tuple
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

from ayusetu.common.config import settings
from ayusetu.common.redis_client import get_redis_client
from ayusetu.gateway.errors import ErrorCode

# In-memory fallback tracking when Redis is offline
_in_memory_buckets: dict[str, list[float]] = {}
_in_memory_counters: dict[str, int] = {}


def _hash_key(prefix: str, identifier: str) -> str:
    """Create an anonymized, collision-safe cache key without exposing raw identifiers."""
    hashed = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:16]
    return f"ayusetu:ratelimit:{prefix}:{hashed}"


class RateLimiter:
    """Token-bucket and sliding window rate limiter backed by Redis or In-Memory."""

    @classmethod
    def check_rate_limit(
        cls, key: str, max_requests: int, window_seconds: int
    ) -> Tuple[bool, int]:
        """
        Check if request is allowed.
        Returns: (is_allowed: bool, retry_after_seconds: int)
        """
        now = time.time()
        try:
            client = get_redis_client()
            member_id = f"{now}_{secrets.token_hex(4)}"
            
            pipeline = client.pipeline()
            pipeline.zremrangebyscore(key, 0, now - window_seconds)
            pipeline.zcard(key)
            pipeline.zadd(key, {member_id: now})
            pipeline.expire(key, window_seconds + 1)
            results = pipeline.execute()
            current_count = results[1]

            if current_count >= max_requests:
                oldest_entries = client.zrange(key, 0, 0, withscores=True)
                if oldest_entries:
                    oldest_time = oldest_entries[0][1]
                    retry_after = max(1, int(window_seconds - (now - oldest_time)))
                else:
                    retry_after = window_seconds
                return False, retry_after
            return True, 0

        except Exception:
            # In-memory fallback
            timestamps = _in_memory_buckets.get(key, [])
            timestamps = [t for t in timestamps if now - t < window_seconds]
            if len(timestamps) >= max_requests:
                retry_after = max(1, int(window_seconds - (now - timestamps[0])))
                _in_memory_buckets[key] = timestamps
                return False, retry_after
            timestamps.append(now)
            _in_memory_buckets[key] = timestamps
            return True, 0

    @classmethod
    def check_counter_limit(cls, key: str, max_count: int, ttl_seconds: int = 3600) -> Tuple[bool, int]:
        """Check monotonic session limit (e.g. max 300 requests or 20 uploads)."""
        try:
            client = get_redis_client()
            count = client.incr(key)
            if count == 1:
                client.expire(key, ttl_seconds)
            if count > max_count:
                return False, ttl_seconds
            return True, 0
        except Exception:
            count = _in_memory_counters.get(key, 0) + 1
            _in_memory_counters[key] = count
            if count > max_count:
                return False, 60
            return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware applying PRD rate limits based on client identity:
    1. Device Certificate / Hardware ID
    2. Session Token / ID
    3. Client IP (Public PWA)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Exclude internal health checks from rate limiting
        if request.url.path in ["/health", "/ready", "/api/v1/health", "/"]:
            return await call_next(request)

        device_id = request.headers.get("X-Device-Fingerprint") or request.headers.get("X-Device-ID")
        session_id = request.headers.get("X-Session-ID") or request.cookies.get("session_id")
        
        # Check URL path for session ID extraction (e.g. /api/v1/sessions/{id}/...)
        path_parts = request.url.path.strip("/").split("/")
        if len(path_parts) >= 3 and path_parts[1] == "sessions":
            session_id = session_id or path_parts[2]

        is_upload = "/documents" in request.url.path.lower()
        client_ip = request.client.host if request.client else "127.0.0.1"

        # 1. Device Rate Limit
        if device_id:
            dev_key = _hash_key("device", device_id)
            allowed, retry_after = RateLimiter.check_rate_limit(
                dev_key,
                max_requests=settings.RATE_LIMIT_DEVICE_RPM,
                window_seconds=60
            )
            if not allowed:
                return self._rate_limit_response(request, retry_after, "device")

        # 2. Session Rate Limits (Total requests + Document uploads)
        if session_id:
            sess_req_key = _hash_key("sess_req", session_id)
            allowed, retry_after = RateLimiter.check_counter_limit(
                sess_req_key,
                max_count=settings.RATE_LIMIT_SESSION_TOTAL,
                ttl_seconds=settings.SESSION_TTL_MINUTES * 60
            )
            if not allowed:
                return self._rate_limit_response(request, retry_after, "session_total")

            if is_upload:
                sess_doc_key = _hash_key("sess_doc", session_id)
                allowed, retry_after = RateLimiter.check_counter_limit(
                    sess_doc_key,
                    max_count=settings.RATE_LIMIT_DOC_UPLOAD_TOTAL,
                    ttl_seconds=settings.SESSION_TTL_MINUTES * 60
                )
                if not allowed:
                    return self._rate_limit_response(request, retry_after, "session_document_upload")

        # 3. IP Rate Limit (PWA / Public client fallback)
        if not device_id:
            ip_key = _hash_key("ip", client_ip)
            allowed, retry_after = RateLimiter.check_rate_limit(
                ip_key,
                max_requests=settings.RATE_LIMIT_PWA_RPM,
                window_seconds=60
            )
            if not allowed:
                return self._rate_limit_response(request, retry_after, "ip")

        return await call_next(request)

    def _rate_limit_response(self, request: Request, retry_after: int, limit_type: str) -> Response:
        req_id = getattr(request.state, "request_id", "")
        return JSONResponse(
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": {
                    "code": ErrorCode.RATE_LIMITED.value,
                    "message": f"Rate limit exceeded for {limit_type}. Please retry after {retry_after} seconds.",
                    "request_id": req_id,
                    "details": {
                        "retry_after_seconds": retry_after,
                        "limit_type": limit_type
                    }
                }
            },
            headers={
                "Retry-After": str(retry_after),
                "X-Request-ID": req_id
            }
        )
