"""Tenant metadata CRUD (stub for future DB integration)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from butler.config import settings


@dataclass
class TenantRecord:
    tenant_id: str
    name: str
    plan_tier: str = "entry"
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    profile_markdown: str = ""
    metadata: dict = field(default_factory=dict)


class TenantStore:
    """
    Simple filesystem + YAML tenant registry.
    Post-MVP: replace with SQLAlchemy DB queries.
    """

    def __init__(self, root: Path | None = None):
        self.root = root or settings.data_root
        self._cache: dict[str, TenantRecord] = {}

    async def get(self, tenant_id: str) -> TenantRecord | None:
        if tenant_id in self._cache:
            return self._cache[tenant_id]

        config_path = self.root / tenant_id / "tenant.yaml"
        if not config_path.exists():
            return None

        data = yaml.safe_load(config_path.read_text())
        record = TenantRecord(**data)
        self._cache[tenant_id] = record
        return record

    async def save(self, record: TenantRecord) -> None:
        tenant_dir = self.root / record.tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        config_path = tenant_dir / "tenant.yaml"
        config_path.write_text(yaml.dump({
            "tenant_id": record.tenant_id,
            "name": record.name,
            "plan_tier": record.plan_tier,
            "is_active": record.is_active,
            "created_at": record.created_at,
            "profile_markdown": record.profile_markdown,
            "metadata": record.metadata,
        }))
        self._cache[record.tenant_id] = record

    async def load_profile(self, tenant_id: str) -> str | None:
        """Load tenant's CLAUDE.md profile."""
        profile_path = self.root / tenant_id / "profile" / "CLAUDE.md"
        if not profile_path.exists():
            return None
        return profile_path.read_text(encoding="utf-8")

    async def save_profile(self, tenant_id: str, markdown: str) -> None:
        """Save tenant's CLAUDE.md profile."""
        profile_dir = self.root / tenant_id / "profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        profile_path = profile_dir / "CLAUDE.md"
        profile_path.write_text(markdown, encoding="utf-8")
