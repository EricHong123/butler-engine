"""FastAPI shared dependencies."""

from __future__ import annotations

from butler.engine.agent_definitions import AgentDefinition, get_agent
from butler.engine.tool_registry import ToolRegistry
from butler.tools.check_tax_calendar import CheckTaxCalendarTool
from butler.tools.escalate_to_human import EscalateToHumanTool
from butler.tools.generate_report import GenerateReportTool
from butler.tools.query_assets import QueryAssetsTool
from butler.tools.schedule_event import ScheduleEventTool
from butler.tools.search_docs import SearchDocsTool

# All tools by name
_ALL_TOOLS = {
    "query_assets": QueryAssetsTool,
    "check_tax_calendar": CheckTaxCalendarTool,
    "search_docs": SearchDocsTool,
    "schedule_event": ScheduleEventTool,
    "generate_report": GenerateReportTool,
    "escalate_to_human": EscalateToHumanTool,
}

# Full registry (all tools)
_full_registry: ToolRegistry | None = None
# Per-agent registries (lazy)
_agent_registries: dict[str, ToolRegistry] = {}


def get_full_registry() -> ToolRegistry:
    global _full_registry
    if _full_registry is None:
        _full_registry = ToolRegistry([cls() for cls in _ALL_TOOLS.values()])
    return _full_registry


def get_agent_tools(agent_type: str) -> ToolRegistry:
    """Get a tool registry scoped to this agent's allowed tools."""
    if agent_type in _agent_registries:
        return _agent_registries[agent_type]

    agent = get_agent(agent_type)

    # If no tool restriction, use full registry
    if not agent.tools:
        return get_full_registry()

    # Build scoped registry
    tool_instances = []
    for name in agent.tools:
        cls = _ALL_TOOLS.get(name)
        if cls:
            tool_instances.append(cls())

    registry = ToolRegistry(tool_instances)
    _agent_registries[agent_type] = registry
    return registry
