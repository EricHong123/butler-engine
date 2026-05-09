"""Tool Registry. Python port of findToolByName / toolMatchesName (Tool.ts:348-359)."""

from __future__ import annotations

from .base_tool import BaseTool


class ToolRegistry:
    """Stores and looks up tools by name or alias."""

    def __init__(self, tools: list[BaseTool] | None = None):
        self._tools: dict[str, BaseTool] = {}
        self._aliases: dict[str, str] = {}
        if tools:
            for tool in tools:
                self.register(tool)

    def register(self, tool: BaseTool) -> None:
        """Register a tool. Raises if name collision."""
        if tool.name in self._tools:
            raise ValueError(f"Tool name conflict: {tool.name}")
        self._tools[tool.name] = tool
        for alias in tool.aliases:
            if alias in self._aliases:
                raise ValueError(f"Tool alias conflict: {alias}")
            self._aliases[alias] = tool.name

    def find(self, name: str) -> BaseTool | None:
        """Find tool by name or alias. Returns None if not found."""
        effective = self._aliases.get(name, name)
        return self._tools.get(effective)

    def get(self, name: str) -> BaseTool:
        """Find tool, raising KeyError if not found."""
        tool = self.find(name)
        if tool is None:
            raise KeyError(f"Tool not found: {name}")
        return tool

    def list_enabled(self) -> list[BaseTool]:
        """Return all enabled tools."""
        return [t for t in self._tools.values() if t.is_enabled()]

    def to_anthropic_format(self) -> list[dict]:
        """Convert all enabled tools to Anthropic API format."""
        return [t.to_anthropic_tool() for t in self.list_enabled()]

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return self.find(name) is not None
