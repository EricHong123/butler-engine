"""Redis connection manager with auto-fallback."""

from __future__ import annotations

import redis.asyncio as aioredis
from redis.asyncio import Redis

from butler.config import settings

_pool: Redis | None = None
_checked = False
_available = False


async def get_redis() -> Redis | None:
    """Get Redis connection. Returns None if unavailable."""
    global _pool, _checked, _available

    if _checked and not _available:
        return None

    if _pool is None:
        try:
            _pool = aioredis.from_url(
                settings.redis_url,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=True,
            )
            await _pool.ping()
            _available = True
        except Exception:
            _pool = None
            _available = False
        finally:
            _checked = True

    if _pool and _available:
        try:
            await _pool.ping()
            return _pool
        except Exception:
            _available = False
            return None

    return None


async def close_redis() -> None:
    global _pool, _checked, _available
    if _pool:
        await _pool.close()
        _pool = None
        _checked = False
        _available = False
