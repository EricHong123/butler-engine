"""Tenant and customer models."""

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from butler.models.base import UUIDMixin, Base, TimestampMixin


class Tenant(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    plan_tier: Mapped[str] = mapped_column(
        String(50), default="entry", nullable=False
    )  # entry, family, flagship, custom
    is_active: Mapped[bool] = mapped_column(default=True)

    # Profile stored as filesystem markdown, path stored here
    profile_path: Mapped[str | None] = mapped_column(String(500))
    memory_path: Mapped[str | None] = mapped_column(String(500))

    customers = relationship("Customer", back_populates="tenant")


class Customer(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("tenant_id", "wechat_id"),)

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    wechat_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))

    tenant = relationship("Tenant", back_populates="customers")
