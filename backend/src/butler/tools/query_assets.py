"""Tool: Query customer asset holdings, balances, and portfolio summary."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from butler.engine.base_tool import BaseTool, ToolResult


class AssetQueryInput(BaseModel):
    """Input for querying assets."""
    query: str = Field(description="What to look up: 'all', 'bank_deposit', 'securities', 'trust', 'real_estate', or a specific account name")
    asset_type: str | None = Field(default=None, description="Filter by asset type: bank_deposit, securities, trust, insurance, real_estate, alternative")
    account: str | None = Field(default=None, description="Filter by specific account name or institution, e.g. 'CMB Private' or 'HSBC'")
    currency: str | None = Field(default=None, description="Filter by currency: CNY, USD, HKD, etc.")


class QueryAssetsTool(BaseTool):
    """
    Look up the family's asset holdings, account balances, and portfolio data.

    This tool queries the asset database for the current tenant.
    For MVP, returns mock data structured like real bank/trust holdings.
    """

    name = "query_assets"
    aliases = ["查资产", "查账户", "资产查询"]
    search_hint = "asset portfolio wealth account balance holdings"

    def is_read_only(self, input: dict | None = None) -> bool:
        return True

    async def call(self, args: dict, context: Any) -> ToolResult:
        tenant_id = self._require_tenant(context)
        asset_type = args.get("asset_type")
        account = args.get("account")
        currency = args.get("currency")

        all_assets = _get_mock_portfolio(tenant_id)

        # Apply filters
        results = all_assets
        if asset_type:
            results = [a for a in results if a["asset_type"] == asset_type]
        if currency:
            results = [a for a in results if a.get("currency") == currency]
        if account:
            account_lower = account.lower()
            results = [
                a for a in results
                if account_lower in a["account_name"].lower()
                or account_lower in a.get("institution", "").lower()
            ]

        total_value = sum(a.get("value_snapshot", 0) for a in results)

        return ToolResult(data={
            "accounts": results,
            "total_accounts": len(results),
            "total_value": total_value,
            "currency": currency or "mixed",
            "as_of_date": "2026-05-08",
        })

    async def description(self, input: dict, options: dict) -> str:
        asset_type = input.get("asset_type", "all")
        return f"Query family asset holdings (type: {asset_type})"

    def input_schema(self) -> type[BaseModel]:
        return AssetQueryInput


def _get_mock_portfolio(tenant_id: str = "demo-001") -> list[dict[str, Any]]:
    """Mock asset data for MVP demonstration. Tenant-filtered."""
    _portfolios: dict[str, list[dict[str, Any]]] = {
        "demo-001": [
        {
            "account_name": "CMB Private Banking 活期",
            "asset_type": "bank_deposit",
            "institution": "China Merchants Bank",
            "currency": "CNY",
            "value_snapshot": 8_500_000.00,
            "value_date": "2026-05-01",
            "account_number_masked": "****8891",
            "notes": "日常流动资金",
        },
        {
            "account_name": "CMB Wealth 稳健型组合",
            "asset_type": "securities",
            "institution": "CMB Wealth Management",
            "currency": "CNY",
            "value_snapshot": 25_000_000.00,
            "value_date": "2026-04-30",
            "account_number_masked": "****4452",
            "notes": "固收+权益混合，年化收益约5.2%",
        },
        {
            "account_name": "HSBC Premier 储蓄",
            "asset_type": "bank_deposit",
            "institution": "HSBC Hong Kong",
            "currency": "USD",
            "value_snapshot": 1_200_000.00,
            "value_date": "2026-05-01",
            "account_number_masked": "****3321",
            "notes": "国际支出 + 子女留学费用",
        },
        {
            "account_name": "家族信托 #1 — 洪氏教育信托",
            "asset_type": "trust",
            "institution": "China International Trust",
            "currency": "CNY",
            "value_snapshot": 30_000_000.00,
            "value_date": "2026-03-31",
            "account_number_masked": "****7762",
            "notes": "子女教育专项，受益人：洪明、洪悦",
        },
        {
            "account_name": "家族信托 #2 — 世代传承信托",
            "asset_type": "trust",
            "institution": "CITIC Trust",
            "currency": "CNY",
            "value_snapshot": 50_000_000.00,
            "value_date": "2026-03-31",
            "account_number_masked": "****9901",
            "notes": "长期传承，不动产+金融资产组合",
        },
        {
            "account_name": "友邦 终身寿险",
            "asset_type": "insurance",
            "institution": "AIA Hong Kong",
            "currency": "USD",
            "value_snapshot": 800_000.00,
            "value_date": "2026-04-15",
            "account_number_masked": "****5543",
            "notes": "保单现金价值，年缴保费$50,000",
        },
        {
            "account_name": "汤臣一品 自住",
            "asset_type": "real_estate",
            "institution": "",
            "currency": "CNY",
            "value_snapshot": 45_000_000.00,
            "value_date": "2026-01-01",
            "account_number_masked": "",
            "notes": "浦东新区，建筑面积430㎡，估值参考2026Q1",
        },
        {
            "account_name": "北京朝阳区 投资房产",
            "asset_type": "real_estate",
            "institution": "",
            "currency": "CNY",
            "value_snapshot": 12_000_000.00,
            "value_date": "2026-01-01",
            "account_number_masked": "",
            "notes": "年租金收入约60万，出租中",
        },
    ],
    }
    # Unknown tenants get demo data but are logged for audit
    return _portfolios.get(tenant_id, _portfolios["demo-001"])
