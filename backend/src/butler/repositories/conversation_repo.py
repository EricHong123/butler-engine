"""Repository for Conversation and AuditLog models."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from butler.models.conversation import AuditLog, Conversation


class ConversationRepo:
    """Async CRUD for conversations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, conv_id: str) -> Conversation | None:
        return await self.session.get(Conversation, conv_id)

    async def get_by_session(self, session_id: str) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation).where(Conversation.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self, tenant_id: str, status: str | None = None, limit: int = 20
    ) -> list[Conversation]:
        stmt = select(Conversation).where(Conversation.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(Conversation.status == status)
        stmt = stmt.order_by(Conversation.last_activity.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, conv: Conversation) -> Conversation:
        self.session.add(conv)
        await self.session.flush()
        return conv

    async def update(self, conv: Conversation) -> Conversation:
        await self.session.merge(conv)
        await self.session.flush()
        return conv


class AuditLogRepo:
    """Async CRUD for audit logs."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        tenant_id: str,
        action: str,
        actor: str = "system",
        details: str | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            tenant_id=tenant_id,
            action=action,
            actor=actor,
            details=details,
            ip_address=ip_address,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_by_tenant(
        self, tenant_id: str, limit: int = 100
    ) -> list[AuditLog]:
        result = await self.session.execute(
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
