"""Add Row-Level Security policies for multi-tenant isolation.

This migration enables RLS on all tenant-scoped tables and creates
policies that restrict access to rows matching the current tenant_id
set via app.tenant_id session variable.

Revision ID: 002_rls
Revises: 001_initial
Create Date: 2026-05-09
"""

from typing import Sequence, Union

from alembic import op

# Revision identifiers
revision: str = "002_rls"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables to protect with RLS
TENANT_TABLES = [
    "conversations",
    "audit_logs",
    "documents",
    "assets",
    "tax_deadlines",
    "tenants",
    "customers",
]

RLS_POLICY_SQL = """
-- Enable RLS on the table
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;

-- Force RLS for all users (including table owner)
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;

-- Create tenant isolation policy
-- Uses current_setting('app.tenant_id') which must be set at connection time
DROP POLICY IF EXISTS tenant_isolation ON {table};
CREATE POLICY tenant_isolation ON {table}
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- Bypass RLS for background jobs or admin queries
-- (set app.tenant_id to 'admin' for full access)
"""


def upgrade() -> None:
    """Enable RLS on all tenant-scoped tables."""
    for table in TENANT_TABLES:
        op.execute(RLS_POLICY_SQL.format(table=table))


def downgrade() -> None:
    """Disable RLS on all tenant-scoped tables."""
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
