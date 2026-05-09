"""Abstract Tool base class. Python port of Claude Code's Tool interface (Tool.ts:362-695)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Literal, TypeVar

from pydantic import BaseModel

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT")


@dataclass
class ToolResult(Generic[OutputT]):
    """Python port of ToolResult<T> (Tool.ts:321-336)."""
    data: OutputT
    new_messages: list[Any] | None = None
    context_modifier: Callable[[Any], Any] | None = None


@dataclass
class ValidationResult:
    """Python port of ValidationResult (Tool.ts:95-101)."""
    valid: bool
    message: str | None = None
    error_code: int | None = None


class BaseTool(ABC, Generic[InputT, OutputT]):
    """
    Python port of Tool interface (Tool.ts:362-695).

    A tool is a function that the AI can call during conversation.
    It has an input schema (Pydantic model), a call() method, and
    permission/display metadata.

    Subclasses must implement: call(), description(), input_schema()
    """

    name: str
    aliases: list[str] = []
    search_hint: str | None = None
    max_result_size_chars: int = 100_000
    interrupt_behavior: Literal["cancel", "block"] = "block"
    is_mcp: bool = False

    # ── Must-implement ──

    @abstractmethod
    async def call(self, args: dict, context: "ToolUseContext") -> ToolResult[OutputT]:
        """Execute the tool. Receives raw dict from model JSON + tenant-scoped context."""
        ...

    @abstractmethod
    async def description(self, input: dict, options: dict) -> str:
        """Human-readable description shown in tool_use UI."""
        ...

    @abstractmethod
    def input_schema(self) -> type[BaseModel]:
        """Return the Pydantic model class for tool input validation."""
        ...

    # ── Defaultable (mirrors Claude Code's TOOL_DEFAULTS) ──

    def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: dict | None = None) -> bool:
        return False

    def is_concurrency_safe(self, input: dict | None = None) -> bool:
        return False  # default: assume not safe

    def is_destructive(self, input: dict | None = None) -> bool:
        return False

    async def validate_input(self, args: dict, context: "ToolUseContext") -> ValidationResult:
        return ValidationResult(valid=True)

    async def check_permissions(self, args: dict, context: "ToolUseContext") -> dict:
        """Return {behavior: 'allow'|'deny', updatedInput, message?}."""
        tenant_id = getattr(context, "tenant_id", None)
        if not tenant_id:
            return {
                "behavior": "deny",
                "updatedInput": args,
                "message": "Access denied: no tenant context",
            }
        return {"behavior": "allow", "updatedInput": args}

    def _require_tenant(self, context: "ToolUseContext") -> str:
        """Validate tenant context and return tenant_id. Raises on missing."""
        tid = getattr(context, "tenant_id", None)
        if not tid:
            raise PermissionError("工具调用缺少租户上下文 — 拒绝执行")
        return tid

    def user_facing_name(self, input: dict | None = None) -> str:
        return self.name

    def to_auto_classifier_input(self, input: dict) -> str:
        return ""

    def get_tool_use_summary(self, input: dict | None = None) -> str | None:
        return None

    def get_activity_description(self, input: dict | None = None) -> str | None:
        return None

    # ── Anthropic API helpers ──

    def to_anthropic_tool(self) -> dict:
        """Convert to Anthropic API tool format."""
        schema = self.input_schema()
        return {
            "name": self.name,
            "description": schema.__doc__ or f"Tool: {self.name}",
            "input_schema": schema.model_json_schema(),
        }
