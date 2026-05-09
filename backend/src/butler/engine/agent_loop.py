"""
Core agent loop. Python port of query() in Claude Code's src/query.ts.

Structure:
    while True:
        1. Check auto-compact
        2. Stream from model
        3. Collect tool_use blocks
        4. If no tools → stop, return result
        5. Execute tools (validate → check permissions → call)
        6. Attach results, inject memories, continue
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from butler.engine.base_tool import BaseTool
from butler.engine.compact import (
    CompactTracker,
    compact_conversation,
    should_auto_compact,
)
from butler.engine.tool_registry import ToolRegistry
from butler.services.llm.client import LLMClient, get_llm_client
from butler.services.llm.router import route_model

import asyncio as _asyncio
from butler.engine.audit import audit_tool_call, audit_turn


@dataclass
class StreamEvent:
    """Normalized event emitted from the agent loop."""
    type: str  # "text_delta", "tool_call", "tool_result", "thinking", "done", "error"
    data: Any = None
    metadata: dict = field(default_factory=dict)


@dataclass
class LoopConfig:
    """Parameters for a single submit_message() run."""
    tenant_id: str
    tools: ToolRegistry
    system_prompt: list[dict]
    max_turns: int = 50
    max_budget_usd: float = 5.0
    compact_threshold_tokens: int = 80_000
    enable_compact: bool = True
    # Budget enforcement: callable that returns (current_cost, is_over_budget)
    budget_check: Any = None


@dataclass
class PendingToolCall:
    """A tool_use that we've collected from the stream but not yet executed."""
    id: str
    name: str
    input_json: str  # partial JSON accumulated from stream


async def agent_loop(
    messages: list[dict],
    config: LoopConfig,
    llm: LLMClient | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    """
    The core agent loop. Async generator yielding StreamEvents.

    Yields StreamEvent objects including a final 'done' event with the result text.
    """
    if llm is None:
        llm = get_llm_client()

    tracker = CompactTracker()
    turn_count = 0
    final_text_parts: list[str] = []

    def _make_done() -> StreamEvent:
        return StreamEvent(
            type="done",
            data="\n".join(final_text_parts),
            metadata={"turns": turn_count},
        )

    while True:
        turn_count += 1
        tracker.turn_since_last_compact += 1

        if turn_count > config.max_turns:
            yield StreamEvent(type="done", data="Max turns reached")
            return

        # ── Budget enforcement ──
        if config.budget_check is not None:
            try:
                cost, over = config.budget_check()
                if over:
                    yield StreamEvent(
                        type="done",
                        data=f"Budget exceeded: ${cost:.4f} (limit: ${config.max_budget_usd:.2f})",
                        metadata={"cost_usd": cost, "budget_limit": config.max_budget_usd},
                    )
                    return
            except Exception:
                pass  # Budget check is advisory — don't crash the loop

        # ── Step 1: Auto-compact ──
        if config.enable_compact and await should_auto_compact(
            messages, config.compact_threshold_tokens, tracker
        ):
            result = await compact_conversation(messages, config.system_prompt)
            if result.compacted:
                messages = result.post_compact_messages
                tracker.total_compactions += 1
                tracker.turn_since_last_compact = 0
                yield StreamEvent(
                    type="system",
                    data=f"Conversation compacted (freed ~{result.tokens_freed} tokens)",
                )
            else:
                tracker.consecutive_failures += 1

        # ── Step 2: Route model + stream ──
        model, provider = route_model(messages)

        # Convert tool registry to API format
        api_tools = config.tools.to_anthropic_format()

        tool_calls: list[PendingToolCall] = []
        current_tool: PendingToolCall | None = None

        async for event in llm.stream(
            provider=provider,
            model=model,
            system=config.system_prompt,
            messages=messages,
            tools=api_tools if api_tools else None,
        ):
            if event["type"] == "text_delta":
                final_text_parts.append(event["text"])
                yield StreamEvent(type="text_delta", data=event["text"])

            elif event["type"] == "tool_use_start":
                current_tool = PendingToolCall(
                    id=event["id"],
                    name=event["name"],
                    input_json="",
                )
                tool_calls.append(current_tool)

            elif event["type"] == "input_json_delta":
                if current_tool:
                    current_tool.input_json += event["partial_json"]

            elif event["type"] == "message_stop":
                pass  # Final

        # ── Step 3: No tools → done ──
        if not tool_calls:
            yield StreamEvent(
                type="done",
                data="\n".join(final_text_parts),
                metadata={"turns": turn_count, "model": model, "provider": provider},
            )
            return

        # ── Step 4: Execute tools ──
        for tc in tool_calls:
            tool = config.tools.find(tc.name)
            if tool is None:
                error_msg = f"Unknown tool: {tc.name}"
                yield StreamEvent(type="error", data=error_msg)
                messages.append(_tool_error_block(tc.id, error_msg))
                continue

            try:
                input_dict = json.loads(tc.input_json) if tc.input_json.strip() else {}
            except json.JSONDecodeError:
                yield StreamEvent(
                    type="error",
                    data=f"Invalid JSON from model for tool {tc.name}: {tc.input_json[:200]}",
                )
                messages.append(
                    _tool_error_block(tc.id, f"Invalid input JSON for {tc.name}")
                )
                continue

            yield StreamEvent(
                type="tool_call",
                data={"id": tc.id, "name": tc.name, "input": input_dict},
            )

            # Execute tool
            try:
                # Build a minimal ToolUseContext
                ctx = _make_tool_context(config, messages)
                result = await tool.call(input_dict, ctx)  # type: ignore[arg-type]
                result_text = json.dumps(result.data, ensure_ascii=False, default=str)

                # Fire-and-forget audit: tool invocation logged
                _asyncio.ensure_future(audit_tool_call(
                    tenant_id=config.tenant_id,
                    tool_name=tc.name,
                    tool_input=input_dict,
                    tool_output=result_text,
                ))

                yield StreamEvent(
                    type="tool_result",
                    data={"tool_use_id": tc.id, "result": result_text},
                )

                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tc.id,
                            "content": result_text,
                        }
                    ],
                })

            except Exception as exc:
                error_msg = f"Tool {tc.name} failed: {exc}"
                yield StreamEvent(type="error", data=error_msg)
                messages.append(_tool_error_block(tc.id, error_msg))

        # ── Loop back to stream model's response to tool results ──


def _tool_error_block(tool_use_id: str, error: str) -> dict:
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": error,
                "is_error": True,
            }
        ],
    }


class ToolUseContext:
    """Tenant-scoped context passed to every tool invocation."""

    def __init__(self, tenant_id: str, messages: list[dict]) -> None:
        if not tenant_id:
            raise ValueError("tenant_id must not be empty")
        self.tenant_id = tenant_id
        self.messages = messages


def _make_tool_context(config: LoopConfig, msgs: list[dict]) -> ToolUseContext:
    """Build tenant-scoped ToolUseContext for tool execution."""
    return ToolUseContext(tenant_id=config.tenant_id, messages=msgs)
