"""
AgentRunner — Python port of Claude Code's QueryEngine (QueryEngine.ts:184-1177).

One AgentRunner per customer conversation. submit_message() starts a new turn
within the same conversation. State persists across turns.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from butler.engine.agent_loop import LoopConfig, StreamEvent, agent_loop
from butler.engine.context_builder import build_system_prompt
from butler.engine.tool_registry import ToolRegistry


@dataclass
class AgentRunnerConfig:
    """Mirrors QueryEngineConfig from Claude Code."""
    tenant_id: str
    tools: ToolRegistry
    model: str = "claude-sonnet-4-6-20250514"
    max_turns: int = 50
    max_budget_usd: float = 5.0
    enable_compact: bool = True
    compact_threshold_tokens: int = 80_000
    profile_markdown: str | None = None
    memory_index: str | None = None
    custom_system_prompt: str | None = None


@dataclass
class TurnResult:
    """Complete result from a submit_message() call."""
    text: str
    turns: int
    model: str
    provider: str
    conversation_id: str
    messages: list[dict] = field(default_factory=list)


class AgentRunner:
    """
    Owns the query lifecycle and session state for one tenant conversation.

    Usage:
        runner = AgentRunner(config)
        async for event in runner.submit_message("查一下我这个月的资产情况"):
            if event.type == "text_delta":
                send_to_wechat(event.data)  # stream to customer
            elif event.type == "done":
                final_result = event.data
    """

    def __init__(self, config: AgentRunnerConfig, llm: Any = None) -> None:
        self.config = config
        self._llm = llm  # Injected LLM client (for testing)
        self.messages: list[dict] = []
        self._conversation_id = str(uuid.uuid4())
        self._session_id = str(uuid.uuid4())
        self._total_turns = 0
        self._total_cost_estimate = 0.0
        self._abort = asyncio.Event()
        self._token_input = 0
        self._token_output = 0

    @property
    def estimated_cost_usd(self) -> float:
        """Rough cost estimate based on token usage."""
        # Claude Sonnet: ~$3/$15 per 1M input/output tokens
        input_cost = (self._token_input / 1_000_000) * 3.0
        output_cost = (self._token_output / 1_000_000) * 15.0
        return input_cost + output_cost

    @property
    def is_over_budget(self) -> bool:
        return self.estimated_cost_usd >= self.config.max_budget_usd

    async def submit_message(
        self,
        prompt: str,
        *,
        attachments: list[dict] | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Submit a user message and yield streaming response events.

        This is the main entry point. Callers iterate over the generator
        to receive text_delta, tool_call, tool_result, and done events.
        """
        self._abort.clear()

        # Build system prompt (refreshed each turn to pick up profile/memory changes)
        system_prompt = await build_system_prompt(
            tenant_id=self.config.tenant_id,
            profile_markdown=self.config.profile_markdown,
            memory_index=self.config.memory_index,
            custom_override=self.config.custom_system_prompt,
        )

        # Add user message with content boundary markers for injection defense
        wrapped_prompt = f"<user_query>\n{prompt}\n</user_query>"
        user_msg: dict[str, Any] = {
            "role": "user",
            "content": wrapped_prompt,
        }
        if attachments:
            user_msg["content"] = [
                {"type": "text", "text": prompt},
                *attachments,
            ]
        self.messages.append(user_msg)

        # Run agent loop with budget enforcement
        def _budget_check():
            cost = self.estimated_cost_usd
            return cost, cost >= self.config.max_budget_usd

        loop_config = LoopConfig(
            tenant_id=self.config.tenant_id,
            tools=self.config.tools,
            system_prompt=system_prompt,
            max_turns=self.config.max_turns,
            max_budget_usd=self.config.max_budget_usd,
            compact_threshold_tokens=self.config.compact_threshold_tokens,
            enable_compact=self.config.enable_compact,
            budget_check=_budget_check,
        )

        try:
            final_text = None
            async for event in agent_loop(self.messages, loop_config, llm=self._llm):
                # Check for abort
                if self._abort.is_set():
                    yield StreamEvent(type="done", data="Interrupted")
                    return

                yield event

                if event.type == "done":
                    final_text = event.data

            self._total_turns += 1

        except asyncio.CancelledError:
            yield StreamEvent(type="done", data="Cancelled")

    def interrupt(self) -> None:
        """Abort the current query. Thread-safe."""
        self._abort.set()

    def add_message(self, role: str, content: str) -> None:
        """Manually inject a message into the conversation (e.g., system note)."""
        self.messages.append({"role": role, "content": content})

    def get_conversation_id(self) -> str:
        return self._conversation_id

    def get_session_id(self) -> str:
        return self._session_id

    # ── Lifecycle ──

    async def start_session(self) -> None:
        """Called when a new customer session begins."""
        self._session_id = str(uuid.uuid4())
        self.messages = []

    async def end_session(self) -> None:
        """Called when customer session ends. Persist conversation."""
        # Persist to DB in later phases
        pass
