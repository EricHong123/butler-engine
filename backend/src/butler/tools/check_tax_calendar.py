"""Tool: Check upcoming tax deadlines and compliance dates."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from butler.engine.base_tool import BaseTool, ToolResult


class TaxCalendarInput(BaseModel):
    """Input for checking tax deadlines."""
    jurisdiction: str | None = Field(default=None, description="Tax jurisdiction: CN, HK, US, SG, or 'all'")
    date_range: str | None = Field(default=None, description="Date range: 'this_month', 'next_30_days', 'this_quarter', or 'all_pending'")
    tax_type: str | None = Field(default=None, description="Tax type: 'income', 'property', 'trust', 'vat', 'corporate'")


class CheckTaxCalendarTool(BaseTool):
    """
    Check upcoming tax deadlines, filing dates, and compliance requirements
    across the family's jurisdictions.
    """

    name = "check_tax_calendar"
    aliases = ["税务日历", "税务提醒", "报税截止日"]
    search_hint = "tax deadline filing compliance calendar"

    def is_read_only(self, input: dict | None = None) -> bool:
        return True

    async def call(self, args: dict, context: Any) -> ToolResult:
        tenant_id = self._require_tenant(context)
        jurisdiction = args.get("jurisdiction", "all")
        date_range = args.get("date_range", "all_pending")
        tax_type = args.get("tax_type")

        today = date.today()
        all_deadlines = _get_mock_deadlines(today, tenant_id)

        # Filter by jurisdiction
        if jurisdiction and jurisdiction != "all":
            all_deadlines = [
                d for d in all_deadlines
                if d["jurisdiction"].lower() == jurisdiction.lower()
            ]

        # Filter by date range
        if date_range == "this_month":
            all_deadlines = [
                d for d in all_deadlines
                if d["deadline"].month == today.month
            ]
        elif date_range == "next_30_days":
            from datetime import timedelta
            cutoff = today + timedelta(days=30)
            all_deadlines = [
                d for d in all_deadlines
                if d["deadline"] <= cutoff and d["deadline"] >= today
            ]

        # Filter by tax type
        if tax_type:
            all_deadlines = [
                d for d in all_deadlines
                if tax_type.lower() in d.get("tax_type", "").lower()
            ]

        # Sort by deadline
        all_deadlines.sort(key=lambda d: d["deadline"])

        # Calculate urgency
        urgent = [d for d in all_deadlines if d["deadline"] <= date(today.year, today.month, today.day + 14)]
        upcoming = [d for d in all_deadlines if d not in urgent]

        return ToolResult(data={
            "urgent": urgent,
            "upcoming": upcoming,
            "total_pending": len(all_deadlines),
            "jurisdictions": list(set(d["jurisdiction"] for d in all_deadlines)),
            "as_of_date": today.isoformat(),
        })

    async def description(self, input: dict, options: dict) -> str:
        jurisdiction = input.get("jurisdiction", "all")
        return f"Check tax deadlines (jurisdiction: {jurisdiction})"

    def input_schema(self) -> type[BaseModel]:
        return TaxCalendarInput


def _get_mock_deadlines(today: date, tenant_id: str = "demo-001") -> list[dict[str, Any]]:
    """Mock tax deadlines for 2026. Tenant-filtered."""
    y = today.year
    _deadlines: dict[str, list[dict[str, Any]]] = {
        "demo-001": [
        {
            "jurisdiction": "CN",
            "tax_type": "个人所得税 — 年度汇算清缴",
            "deadline": date(y, 6, 30),
            "status": "pending",
            "amount_due": None,
            "currency": "CNY",
            "notes": "综合所得年度汇算，通过个人所得税APP申报",
        },
        {
            "jurisdiction": "CN",
            "tax_type": "房产税",
            "deadline": date(y, 12, 31),
            "status": "pending",
            "amount_due": 85_000.00,
            "currency": "CNY",
            "notes": "上海+北京房产，按评估值计算",
        },
        {
            "jurisdiction": "HK",
            "tax_type": "利得税 — 2025/26课税年度",
            "deadline": date(y, 8, 15),
            "status": "pending",
            "amount_due": None,
            "currency": "HKD",
            "notes": "香港公司利得税申报，需会计师出具审计报告",
        },
        {
            "jurisdiction": "HK",
            "tax_type": "物业税",
            "deadline": date(y, 5, 31),
            "status": "pending",
            "amount_due": 120_000.00,
            "currency": "HKD",
            "notes": "香港投资物业租金收入报税",
        },
        {
            "jurisdiction": "US",
            "tax_type": "FBAR申报",
            "deadline": date(y, 10, 15),
            "status": "pending",
            "amount_due": None,
            "currency": "USD",
            "notes": "海外账户申报，HSBC HK账户余额>$10,000需申报",
        },
        {
            "jurisdiction": "CN",
            "tax_type": "CRS信息申报",
            "deadline": date(y, 5, 31),
            "status": "pending",
            "amount_due": None,
            "currency": "CNY",
            "notes": "共同申报准则，金融机构自动交换",
        },
    ],
    }
    return _deadlines.get(tenant_id, _deadlines["demo-001"])
