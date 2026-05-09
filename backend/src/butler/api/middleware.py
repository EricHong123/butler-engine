"""
Rate limiting middleware for Butler Engine API.

Provides per-tenant rate limiting using a sliding window algorithm.
In-memory implementation for MVP; Redis-backed in production.
"""

from __future__ import annotations

import time as _time
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware


@dataclass
class RateLimitConfig:
    """Per-tenant rate limit configuration."""
    max_requests: int = 100       # Max requests in the window
    window_seconds: float = 60.0  # Sliding window size
    block_seconds: float = 300.0  # How long to block after exceeding limit


# Default limits per tenant
DEFAULT_LIMITS = RateLimitConfig()

# Stricter limits for LLM-heavy endpoints
LLM_LIMITS = RateLimitConfig(max_requests=20, window_seconds=60.0, block_seconds=600.0)


class RateLimiter:
    """Sliding window rate limiter per tenant."""

    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or DEFAULT_LIMITS
        # {tenant_id: [timestamps]}
        self._windows: dict[str, list[float]] = defaultdict(list)
        # {tenant_id: block_until_timestamp}
        self._blocked: dict[str, float] = {}

    def check(self, tenant_id: str) -> bool:
        """
        Check if a request is allowed for the given tenant.
        Returns True if allowed, False if rate limited.
        """
        now = _time.time()

        # Check if currently blocked
        if tenant_id in self._blocked:
            if now < self._blocked[tenant_id]:
                return False
            del self._blocked[tenant_id]

        # Slide the window
        cutoff = now - self.config.window_seconds
        self._windows[tenant_id] = [
            ts for ts in self._windows[tenant_id] if ts > cutoff
        ]

        # Check limit
        if len(self._windows[tenant_id]) >= self.config.max_requests:
            self._blocked[tenant_id] = now + self.config.block_seconds
            return False

        # Record request
        self._windows[tenant_id].append(now)
        return True

    def remaining(self, tenant_id: str) -> int:
        """Number of requests remaining in the current window."""
        cutoff = _time.time() - self.config.window_seconds
        count = len([ts for ts in self._windows.get(tenant_id, []) if ts > cutoff])
        return max(0, self.config.max_requests - count)

    def reset(self, tenant_id: str) -> None:
        """Reset rate limit for a tenant."""
        self._windows.pop(tenant_id, None)
        self._blocked.pop(tenant_id, None)


# Global singletons
_tenant_limiter = RateLimiter(DEFAULT_LIMITS)
_llm_limiter = RateLimiter(LLM_LIMITS)


def check_tenant_rate_limit(tenant_id: str) -> None:
    """Check tenant rate limit. Raises HTTPException if exceeded."""
    if not _tenant_limiter.check(tenant_id):
        remaining_seconds = 0
        if tenant_id in _tenant_limiter._blocked:
            remaining_seconds = max(0, _tenant_limiter._blocked[tenant_id] - _time.time())
        raise HTTPException(
            status_code=429,
            detail={
                "error": "请求过于频繁，请稍后再试",
                "retry_after_seconds": int(remaining_seconds),
                "limit": _tenant_limiter.config.max_requests,
                "window_seconds": int(_tenant_limiter.config.window_seconds),
            },
        )


def check_llm_rate_limit(tenant_id: str) -> None:
    """Check LLM API rate limit (stricter). Raises HTTPException if exceeded."""
    if not _llm_limiter.check(tenant_id):
        remaining_seconds = 0
        if tenant_id in _llm_limiter._blocked:
            remaining_seconds = max(0, _llm_limiter._blocked[tenant_id] - _time.time())
        raise HTTPException(
            status_code=429,
            detail={
                "error": "AI 请求过于频繁，请稍后再试",
                "retry_after_seconds": int(remaining_seconds),
                "limit": _llm_limiter.config.max_requests,
                "window_seconds": int(_llm_limiter.config.window_seconds),
            },
        )


def get_rate_limit_status(tenant_id: str) -> dict:
    """Get current rate limit status for a tenant."""
    return {
        "remaining": _tenant_limiter.remaining(tenant_id),
        "limit": _tenant_limiter.config.max_requests,
        "llm_remaining": _llm_limiter.remaining(tenant_id),
        "llm_limit": _llm_limiter.config.max_requests,
    }


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that applies rate limiting to all API routes."""

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for non-API paths
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        # Extract tenant from request
        tenant_id = "unknown"
        # Try to get tenant from JWT in Authorization header
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            try:
                from butler.api.router_auth import verify_token
                payload = verify_token(auth[7:])
                tenant_id = payload.get("tenant_id", "anonymous")
            except Exception:
                tenant_id = "anonymous"
        else:
            # Try query param
            tenant_id = request.query_params.get("tenant_id", "anonymous")

        # Apply rate limit
        try:
            check_tenant_rate_limit(tenant_id)
        except HTTPException as e:
            return e  # type: ignore[return-value]

        # Apply stricter LLM limit for chat endpoint
        if request.url.path.endswith("/chat"):
            try:
                check_llm_rate_limit(tenant_id)
            except HTTPException as e:
                return e  # type: ignore[return-value]

        return await call_next(request)
