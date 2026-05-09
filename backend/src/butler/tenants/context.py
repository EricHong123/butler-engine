"""Request-scoped tenant resolution. FastAPI dependency injection."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from butler.config import settings
from butler.memory.memory_manager import MemoryManager

# Thread-safe request-scoped tenant context
_current_tenant: ContextVar["TenantContext | None"] = ContextVar(
    "current_tenant", default=None
)


@dataclass
class TenantContext:
    """Per-request tenant information."""
    tenant_id: str
    customer_id: str | None = None
    plan_tier: str = "entry"

    @property
    def data_dir(self) -> Path:
        return settings.data_root / self.tenant_id

    @property
    def profile_path(self) -> Path:
        return self.data_dir / "profile" / "CLAUDE.md"

    def get_memory_manager(self) -> MemoryManager:
        return MemoryManager(self.tenant_id, settings.data_root)


def set_current_tenant(ctx: TenantContext) -> None:
    _current_tenant.set(ctx)


def get_current_tenant() -> TenantContext:
    ctx = _current_tenant.get()
    if ctx is None:
        raise RuntimeError("No tenant context set. Are you outside a request?")
    return ctx


async def get_tenant_context() -> TenantContext:
    """FastAPI dependency that returns the current tenant context."""
    return get_current_tenant()
