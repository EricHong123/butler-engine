"""Document and asset models."""

from datetime import datetime
from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from butler.models.base import UUIDMixin, Base, TimestampMixin


class Document(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    doc_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # bank_statement, insurance, contract, tax, health, education, other
    encrypted_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    mime_type: Mapped[str] = mapped_column(String(100), default="application/pdf")
    tags: Mapped[str | None] = mapped_column(Text)  # Comma-separated
    expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_sensitive: Mapped[bool] = mapped_column(default=False)


class Asset(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "assets"

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # bank_deposit, securities, trust, insurance, real_estate, alternative
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    value_snapshot: Mapped[float] = mapped_column(Float, default=0.0)
    value_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    institution: Mapped[str | None] = mapped_column(String(255))
    account_number_masked: Mapped[str | None] = mapped_column(
        String(50)
    )  # Last 4 digits only
    notes: Mapped[str | None] = mapped_column(Text)


class TaxDeadline(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tax_deadlines"

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    jurisdiction: Mapped[str] = mapped_column(String(100), nullable=False)  # CN, HK, US, SG
    tax_type: Mapped[str] = mapped_column(String(255), nullable=False)
    deadline_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="pending"
    )  # pending, filed, extended
    amount_due: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    notes: Mapped[str | None] = mapped_column(Text)
