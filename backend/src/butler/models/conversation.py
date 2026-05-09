"""Conversation and message models."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from butler.models.base import UUIDMixin, Base, TimestampMixin


class Conversation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("customers.id"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(String(36), unique=True)
    status: Mapped[str] = mapped_column(
        String(50), default="active", nullable=False
    )  # active, ended, compacted
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(default=0.0)
    last_activity: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Compressed messages stored as JSONB for transcripts
    messages_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AuditLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)  # "system", "customer", "expert"
    details: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(50))
