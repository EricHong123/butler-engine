"""
Tests for all 6 butler-specific tools.
Each tool tested in isolation with controlled input.
"""

import pytest

from butler.engine.tool_registry import ToolRegistry
from butler.tools.check_tax_calendar import CheckTaxCalendarTool
from butler.tools.escalate_to_human import EscalateToHumanTool
from butler.tools.generate_report import GenerateReportTool
from butler.tools.query_assets import QueryAssetsTool
from butler.tools.schedule_event import ScheduleEventTool
from butler.tools.search_docs import SearchDocsTool


# ── Mock context ──

class MockContext:
    tenant_id = "test-tenant"
    messages = []


class TestQueryAssetsTool:
    @pytest.mark.asyncio
    async def test_query_all_assets(self):
        tool = QueryAssetsTool()
        result = await tool.call({"query": "all"}, MockContext())
        data = result.data
        assert data["total_accounts"] == 8
        assert data["total_value"] > 100_000_000  # >¥1亿
        assert len(data["accounts"]) == 8

    @pytest.mark.asyncio
    async def test_filter_by_asset_type(self):
        tool = QueryAssetsTool()
        result = await tool.call({"asset_type": "trust"}, MockContext())
        assert result.data["total_accounts"] == 2
        for acct in result.data["accounts"]:
            assert acct["asset_type"] == "trust"

    @pytest.mark.asyncio
    async def test_filter_by_currency(self):
        tool = QueryAssetsTool()
        result = await tool.call({"currency": "USD"}, MockContext())
        assert result.data["total_accounts"] == 2
        for acct in result.data["accounts"]:
            assert acct["currency"] == "USD"

    @pytest.mark.asyncio
    async def test_search_by_account_name(self):
        tool = QueryAssetsTool()
        result = await tool.call({"query": "CMB"}, MockContext())
        assert result.data["total_accounts"] >= 2

    def test_is_read_only(self):
        assert QueryAssetsTool().is_read_only() is True

    def test_schema(self):
        from butler.tools.query_assets import AssetQueryInput
        schema = QueryAssetsTool().input_schema()
        assert schema is not None


class TestCheckTaxCalendar:
    @pytest.mark.asyncio
    async def test_all_pending(self):
        tool = CheckTaxCalendarTool()
        result = await tool.call({}, MockContext())
        assert result.data["total_pending"] == 6
        assert len(result.data["jurisdictions"]) >= 2
        assert "CN" in result.data["jurisdictions"]
        assert "HK" in result.data["jurisdictions"]

    @pytest.mark.asyncio
    async def test_filter_by_jurisdiction(self):
        tool = CheckTaxCalendarTool()
        result = await tool.call({"jurisdiction": "HK"}, MockContext())
        assert result.data["total_pending"] == 2
        for d in (result.data["urgent"] + result.data["upcoming"]):
            assert d["jurisdiction"] == "HK"

    @pytest.mark.asyncio
    async def test_this_month(self):
        tool = CheckTaxCalendarTool()
        result = await tool.call({"date_range": "this_month"}, MockContext())
        # May has HK property tax + CRS deadlines
        assert result.data["total_pending"] >= 2


class TestSearchDocs:
    @pytest.mark.asyncio
    async def test_search_by_keyword(self):
        tool = SearchDocsTool()
        result = await tool.call({"query": "HSBC"}, MockContext())
        assert result.data["returned"] >= 1
        assert any("HSBC" in m["filename"] for m in result.data["matches"])

    @pytest.mark.asyncio
    async def test_search_by_doc_type(self):
        tool = SearchDocsTool()
        result = await tool.call({"doc_type": "insurance"}, MockContext())
        for match in result.data["matches"]:
            assert match["doc_type"] == "insurance"

    @pytest.mark.asyncio
    async def test_search_limit(self):
        tool = SearchDocsTool()
        result = await tool.call({"query": "", "limit": 3}, MockContext())
        assert result.data["returned"] <= 3

    @pytest.mark.asyncio
    async def test_search_no_results(self):
        tool = SearchDocsTool()
        result = await tool.call({"query": "nonexistent_xyz"}, MockContext())
        assert result.data["returned"] == 0


class TestScheduleEvent:
    @pytest.mark.asyncio
    async def test_list_events(self):
        tool = ScheduleEventTool()
        result = await tool.call({"action": "list"}, MockContext())
        assert result.data["total"] >= 4

    @pytest.mark.asyncio
    async def test_check_available(self):
        tool = ScheduleEventTool()
        result = await tool.call({
            "action": "check",
            "datetime_str": "2026-12-25T10:00",
        }, MockContext())
        assert result.data["is_available"] is True

    @pytest.mark.asyncio
    async def test_check_conflict(self):
        tool = ScheduleEventTool()
        result = await tool.call({
            "action": "check",
            "datetime_str": "2026-05-15T14:00",
        }, MockContext())
        assert result.data["is_available"] is False
        assert len(result.data["conflicts"]) >= 1

    @pytest.mark.asyncio
    async def test_book_event(self):
        tool = ScheduleEventTool()
        result = await tool.call({
            "action": "book",
            "title": "与会计师视频会议",
            "datetime_str": "2026-05-25T10:00",
            "duration_minutes": 45,
            "priority": "high",
        }, MockContext())
        assert result.data["status"] == "booked"
        assert "会计师" in result.data["event"]["title"]

    @pytest.mark.asyncio
    async def test_cancel_event(self):
        tool = ScheduleEventTool()
        result = await tool.call({
            "action": "cancel",
            "title": "旧事件",
        }, MockContext())
        assert result.data["status"] == "cancelled"


class TestGenerateReport:
    @pytest.mark.asyncio
    async def test_asset_monthly_report(self):
        tool = GenerateReportTool()
        result = await tool.call({
            "report_type": "asset_monthly",
            "period": "2026-04",
        }, MockContext())
        assert "资产月报" in result.data["report_markdown"]
        assert "1.72亿" in result.data["report_markdown"]

    @pytest.mark.asyncio
    async def test_tax_quarterly_report(self):
        tool = GenerateReportTool()
        result = await tool.call({
            "report_type": "tax_quarterly",
            "period": "2026-Q1",
        }, MockContext())
        assert "税务" in result.data["report_markdown"]
        assert "2026-05-31" in result.data["report_markdown"]

    @pytest.mark.asyncio
    async def test_health_annual_report(self):
        tool = GenerateReportTool()
        result = await tool.call({
            "report_type": "health_annual",
            "period": "2026",
        }, MockContext())
        assert "洪伟" in result.data["report_markdown"]
        assert "胆固醇" in result.data["report_markdown"]

    @pytest.mark.asyncio
    async def test_education_progress_report(self):
        tool = GenerateReportTool()
        result = await tool.call({
            "report_type": "education_progress",
            "period": "2026-05",
        }, MockContext())
        assert "洪明" in result.data["report_markdown"]
        assert "SAT" in result.data["report_markdown"]

    @pytest.mark.asyncio
    async def test_summary_format(self):
        tool = GenerateReportTool()
        result = await tool.call({
            "report_type": "asset_monthly",
            "format": "summary",
        }, MockContext())
        assert len(result.data["report_markdown"]) < 500  # Summary is shorter


class TestEscalateToHuman:
    @pytest.mark.asyncio
    async def test_escalate_legal_advice(self):
        tool = EscalateToHumanTool()
        result = await tool.call({
            "reason": "legal_advice",
            "priority": "urgent",
            "context": "客户询问信托法律结构问题",
            "draft_response": "建议咨询陈律师确认...",
        }, MockContext())

        assert result.data["ticket_id"].startswith("REV-")
        assert result.data["priority"] == "urgent"
        assert result.data["sla_minutes"] == 5
        assert result.data["status"] == "pending_review"

    @pytest.mark.asyncio
    async def test_escalate_financial_advice(self):
        tool = EscalateToHumanTool()
        result = await tool.call({
            "reason": "major_financial",
            "priority": "standard",
            "context": "建议出售部分证券组合",
        }, MockContext())
        assert result.data["priority"] == "standard"
        assert result.data["sla_minutes"] == 30

    def test_not_read_only(self):
        assert EscalateToHumanTool().is_read_only() is False

    def test_concurrency_safe(self):
        assert EscalateToHumanTool().is_concurrency_safe() is True


class TestToolRegistry:
    """Verify all 6 tools register correctly."""

    def test_all_tools_register(self):
        tools = [
            QueryAssetsTool(),
            CheckTaxCalendarTool(),
            SearchDocsTool(),
            ScheduleEventTool(),
            GenerateReportTool(),
            EscalateToHumanTool(),
        ]
        registry = ToolRegistry(tools)
        assert len(registry) == 6

    def test_tool_aliases(self):
        tools = [
            QueryAssetsTool(),
            CheckTaxCalendarTool(),
            SearchDocsTool(),
            ScheduleEventTool(),
            GenerateReportTool(),
            EscalateToHumanTool(),
        ]
        registry = ToolRegistry(tools)

        # Query by alias
        assert registry.find("查资产") is not None
        assert registry.find("税务日历") is not None
        assert registry.find("搜文档") is not None
        assert registry.find("日程") is not None

    def test_anthropic_format(self):
        tools = [
            QueryAssetsTool(),
            CheckTaxCalendarTool(),
            SearchDocsTool(),
            ScheduleEventTool(),
            GenerateReportTool(),
            EscalateToHumanTool(),
        ]
        registry = ToolRegistry(tools)
        api_tools = registry.to_anthropic_format()
        assert len(api_tools) == 6
        for t in api_tools:
            assert "name" in t
            assert "input_schema" in t
