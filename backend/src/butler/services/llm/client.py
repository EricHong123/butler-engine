"""LLM client abstraction. Unified async streaming for Claude + OpenAI-compatible providers."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any, Literal

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from butler.config import settings

ProviderKind = Literal["anthropic", "openai"]


def _convert_messages_for_openai(messages: list[dict]) -> list[dict]:
    """
    Convert Anthropic-format messages to OpenAI-format.

    Anthropic: {role, content: str | [{type: "text"|"tool_use"|"tool_result"}]}
    OpenAI:    {role: "user"|"assistant"|"tool", content, tool_calls?, tool_call_id?}

    Critical: OpenAI requires every 'tool' message to follow an 'assistant'
    message that contains the matching tool_call. We track active tool_call IDs
    and skip orphaned tool messages.
    """
    converted = []
    active_tool_ids: set[str] = set()

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # Simple string content
        if isinstance(content, str):
            converted.append({"role": role, "content": content})
            continue

        # Content blocks (Anthropic format)
        if isinstance(content, list):
            text_parts = []
            tool_calls = []
            tool_results = []
            new_tool_ids = set()

            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")

                if btype == "text":
                    text_parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    tid = block.get("id", "")
                    tool_calls.append({
                        "id": tid,
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                        },
                    })
                    new_tool_ids.add(tid)
                elif btype == "tool_result":
                    tool_results.append({
                        "tool_call_id": block.get("tool_use_id", ""),
                        "content": block.get("content", ""),
                    })

            # Emit assistant message first
            if role == "assistant" and (text_parts or tool_calls):
                oai_msg: dict = {"role": "assistant", "content": "\n".join(text_parts) or None}
                if tool_calls:
                    oai_msg["tool_calls"] = tool_calls
                    active_tool_ids.update(new_tool_ids)
                converted.append(oai_msg)

            # Emit tool messages — only if parent tool_call was just emitted
            for tr in tool_results:
                tid = tr["tool_call_id"]
                if tid in active_tool_ids:
                    converted.append({
                        "role": "tool",
                        "tool_call_id": tid,
                        "content": tr["content"],
                    })

            # Emit user text (skip if it was just a tool_result wrapper)
            if role == "user":
                has_real_text = any(
                    b.get("type") == "text" and b.get("text", "").strip()
                    for b in content if isinstance(b, dict)
                )
                if has_real_text:
                    converted.append({"role": "user", "content": "\n".join(text_parts)})
        else:
            converted.append({"role": role, "content": str(content)})

    return converted


class LLMClient:
    """Unified async streaming client for multiple LLM providers."""

    _mock_mode: bool

    def __init__(self) -> None:
        api_key = settings.resolved_api_key
        base_url = settings.resolved_base_url
        provider_type = settings.resolved_provider_type

        self._mock_mode = not api_key
        if self._mock_mode:
            self._anthropic = AsyncAnthropic(api_key="mock-key")
            self._openai = AsyncOpenAI(api_key="mock-key", base_url="https://localhost/v1")
            return

        if provider_type == "anthropic":
            self._anthropic = AsyncAnthropic(
                api_key=api_key,
                base_url=settings.anthropic_base_url or None,
            )
        else:
            self._anthropic = AsyncAnthropic(api_key="unused")

        self._openai = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def stream(
        self,
        *,
        provider: ProviderKind,
        model: str,
        system: str | list[dict],
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
        thinking_budget: int | None = None,
    ) -> AsyncGenerator[dict, None]:
        if provider == "anthropic":
            async for event in self._stream_anthropic(
                model, system, messages, tools, max_tokens, thinking_budget
            ):
                yield event
        else:
            async for event in self._stream_openai(
                model, system, messages, tools, max_tokens
            ):
                yield event

    async def _stream_anthropic(
        self, model, system, messages, tools, max_tokens, thinking_budget
    ) -> AsyncGenerator[dict, None]:
        kwargs: dict[str, Any] = {
            "model": model, "system": system, "messages": messages,
            "max_tokens": max_tokens, "stream": True,
        }
        if tools:
            kwargs["tools"] = [
                {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
                for t in tools
            ]

        async with self._anthropic.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield {"type": "text_delta", "text": event.delta.text}
                    elif event.delta.type == "input_json_delta":
                        yield {"type": "input_json_delta", "partial_json": event.delta.partial_json}
                elif event.type == "content_block_start":
                    if event.content_block.type == "tool_use":
                        yield {"type": "tool_use_start", "id": event.content_block.id, "name": event.content_block.name}
                elif event.type == "content_block_stop":
                    yield {"type": "content_block_stop"}
        yield {"type": "message_stop"}

    async def _stream_openai(
        self, model, system, messages, tools, max_tokens
    ) -> AsyncGenerator[dict, None]:
        # Convert messages from Anthropic format to OpenAI format
        api_messages = _convert_messages_for_openai(messages)

        # Insert system message at the top
        system_text = ""
        if isinstance(system, str):
            system_text = system
        elif isinstance(system, list):
            for block in system:
                if isinstance(block, dict) and block.get("type") == "text":
                    system_text += block.get("text", "")
        if system_text:
            api_messages.insert(0, {"role": "system", "content": system_text})

        kwargs: dict[str, Any] = {
            "model": model, "messages": api_messages,
            "max_tokens": max_tokens, "stream": True,
        }
        if tools:
            kwargs["tools"] = [
                {"type": "function", "function": {
                    "name": t["name"], "description": t.get("description", ""),
                    "parameters": t["input_schema"],
                }}
                for t in tools
            ]

        response = await self._openai.chat.completions.create(**kwargs)
        async for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue
            if delta.content:
                yield {"type": "text_delta", "text": delta.content}
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    if tc.id:
                        yield {"type": "tool_use_start", "id": tc.id, "name": tc.function.name or ""}
                    if tc.function and tc.function.arguments:
                        yield {"type": "input_json_delta", "partial_json": tc.function.arguments}
        yield {"type": "message_stop"}


_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
