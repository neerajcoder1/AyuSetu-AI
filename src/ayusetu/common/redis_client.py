"""
Redis Client Foundation
========================
Provides synchronous and asynchronous Redis client instances with fast timeouts.
"""

from typing import Optional
import redis
import redis.asyncio as aioredis
from ayusetu.common.config import settings

_sync_redis: Optional[redis.Redis] = None
_async_redis: Optional[aioredis.Redis] = None


def get_redis_client() -> redis.Redis:
    """Return singleton synchronous Redis client with connection timeouts."""
    global _sync_redis
    if _sync_redis is None:
        _sync_redis = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=0.1,
            socket_timeout=0.2,
        )
    return _sync_redis


def get_async_redis_client() -> aioredis.Redis:
    """Return singleton asynchronous Redis client with connection timeouts."""
    global _async_redis
    if _async_redis is None:
        _async_redis = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=0.1,
            socket_timeout=0.2,
        )
    return _async_redis


def ping_redis() -> bool:
    """Synchronous ping for health checks."""
    try:
        client = get_redis_client()
        return bool(client.ping())
    except Exception:
        return False


async def async_ping_redis() -> bool:
    """Asynchronous ping for async health checks."""
    try:
        client = get_async_redis_client()
        return bool(await client.ping())
    except Exception:
        return False
