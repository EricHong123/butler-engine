"""Repository for Tenant and Customer models."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from butler.models.tenant import Customer, Tenant


class TenantRepo:
    """Async CRUD for tenants."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, tenant_id: str) -> Tenant | None:
        return await self.session.get(Tenant, tenant_id)

    async def get_by_name(self, name: str) -> Tenant | None:
        result = await self.session.execute(
            select(Tenant).where(Tenant.name == name)
        )
        return result.scalar_one_or_none()

    async def create(self, tenant: Tenant) -> Tenant:
        self.session.add(tenant)
        await self.session.flush()
        return tenant

    async def list_active(self, limit: int = 50) -> list[Tenant]:
        result = await self.session.execute(
            select(Tenant).where(Tenant.is_active == True).limit(limit)
        )
        return list(result.scalars().all())


class CustomerRepo:
    """Async CRUD for customers."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, customer_id: str) -> Customer | None:
        return await self.session.get(Customer, customer_id)

    async def get_by_wechat_id(self, wechat_id: str) -> Customer | None:
        result = await self.session.execute(
            select(Customer).where(Customer.wechat_id == wechat_id)
        )
        return result.scalar_one_or_none()

    async def get_by_tenant(self, tenant_id: str) -> list[Customer]:
        result = await self.session.execute(
            select(Customer).where(Customer.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    async def create(self, customer: Customer) -> Customer:
        self.session.add(customer)
        await self.session.flush()
        return customer
