"""
Smoke test for the core agent loop.
Uses a mock LLM client to verify the loop structure without API calls.
"""

import json
from collections.abc import AsyncGenerator

import pytest
from pydantic import BaseModel, Field

from butler.engine.agent_loop import LoopConfig, StreamEvent, agent_loop
from butler.engine.agent_runner import AgentRunner, AgentRunnerConfig
from butler.engine.base_tool import BaseTool, ToolResult
from butler.engine.tool_registry import ToolRegistry


# ── Mock LLM Client ──

class MockLLMClient:
    """Mock LLM that returns controlled responses."""

    def __init__(self, responses: list[list[dict]]):
        """
        responses: list of turn responses. Each turn response is a list of events.
        """
        self.responses = responses
        self.call_count = 0

    async def stream(self, **kwargs) -> AsyncGenerator[dict, None]:
        if self.call_count >= len(self.responses):
            yield {"type": "text_delta", "text": "No more responses"}
            yield {"type": "message_stop"}
            return

        for event in self.responses[self.call_count]:
            yield event
        self.call_count += 1


# ── Mock Tool ──

class WeatherInput(BaseModel):
    city: str = Field(description="City name to look up weather for")


class MockWeatherTool(BaseTool):
    name = "get_weather"
    search_hint = "weather forecast temperature"

    async def call(self, args: dict, context) -> ToolResult:
        return ToolResult(data={"city": args.get("city"), "temp": 22, "condition": "sunny"})

    async def description(self, input: dict, options) -> str:
        return f"Get weather for {input.get('city', 'unknown')}"

    def input_schema(self):
        return WeatherInput


# ── Tests ──

@pytest.mark.asyncio
async def test_simple_text_response():
    """Agent responds with plain text, no tool calls."""
    mock_llm = MockLLMClient(responses=[
        [
            {"type": "text_delta", "text": "Hello! "},
            {"type": "text_delta", "text": "How can I help?"},
            {"type": "message_stop"},
        ]
    ])

    registry = ToolRegistry()
    config = LoopConfig(
        tenant_id="test-001",
        tools=registry,
        system_prompt=[{"type": "text", "text": "You are a helpful assistant."}],
        max_turns=5,
    )

    events = []
    result = None
    async for event in agent_loop(
        messages=[{"role": "user", "content": "Hello"}],
        config=config,
        llm=mock_llm,
    ):
        events.append(event)
        if event.type == "done":
            result = event.data

    text_events = [e for e in events if e.type == "text_delta"]
    assert len(text_events) == 2
    assert "Hello!" in result
    assert "How can I help?" in result


@pytest.mark.asyncio
async def test_tool_calling_loop():
    """Agent calls a tool, receives result, responds."""
    mock_llm = MockLLMClient(responses=[
        # Turn 1: model calls tool
        [
            {
                "type": "tool_use_start",
                "id": "tool_001",
                "name": "get_weather",
            },
            {"type": "input_json_delta", "partial_json": '{"city": "Shanghai"}'},
            {"type": "message_stop"},
        ],
        # Turn 2: model responds to tool result
        [
            {"type": "text_delta", "text": "Shanghai is 22°C and sunny."},
            {"type": "message_stop"},
        ],
    ])

    weather_tool = MockWeatherTool()
    registry = ToolRegistry([weather_tool])

    config = LoopConfig(
        tenant_id="test-002",
        tools=registry,
        system_prompt=[{"type": "text", "text": "You have tools."}],
        max_turns=5,
    )

    events = []
    async for event in agent_loop(
        messages=[{"role": "user", "content": "What's the weather in Shanghai?"}],
        config=config,
        llm=mock_llm,
    ):
        events.append(event)

    tool_calls = [e for e in events if e.type == "tool_call"]
    tool_results = [e for e in events if e.type == "tool_result"]
    text_events = [e for e in events if e.type == "text_delta"]

    assert len(tool_calls) == 1
    assert tool_calls[0].data["name"] == "get_weather"
    assert len(tool_results) == 1
    assert "22" in str(tool_results[0].data)
    assert len(text_events) == 1


@pytest.mark.asyncio
async def test_max_turns_limit():
    """Agent loop stops when max turns exceeded."""
    # Create a loop where model keeps calling tools forever
    mock_llm = MockLLMClient(responses=[
        [
            {
                "type": "tool_use_start",
                "id": f"tool_{i:03d}",
                "name": "get_weather",
            },
            {"type": "input_json_delta", "partial_json": '{"city": "Shanghai"}'},
            {"type": "message_stop"},
        ]
        for i in range(10)  # More than max_turns=3
    ])

    weather_tool = MockWeatherTool()
    registry = ToolRegistry([weather_tool])

    config = LoopConfig(
        tenant_id="test-003",
        tools=registry,
        system_prompt=[{"type": "text", "text": "You have tools."}],
        max_turns=3,  # Low limit
    )

    events = []
    async for event in agent_loop(
        messages=[{"role": "user", "content": "Loop forever"}],
        config=config,
        llm=mock_llm,
    ):
        events.append(event)

    done_events = [e for e in events if e.type == "done"]
    assert len(done_events) == 1
    assert "Max turns" in str(done_events[0].data)


@pytest.mark.asyncio
async def test_agent_runner_integration():
    """Full integration: AgentRunner with mock LLM."""
    mock_llm = MockLLMClient(responses=[
        [
            {"type": "text_delta", "text": "您好，张先生。"},
            {"type": "text_delta", "text": "我来帮您查看资产情况。"},
            {"type": "message_stop"},
        ]
    ])

    weather_tool = MockWeatherTool()
    registry = ToolRegistry([weather_tool])

    config = AgentRunnerConfig(
        tenant_id="zhang-family",
        tools=registry,
        profile_markdown="# Zhang Family\n- Zhang Wei, 48, Founder",
    )

    runner = AgentRunner(config, llm=mock_llm)

    events = []
    result_text = ""
    async for event in runner.submit_message("查一下我的资产"):
        events.append(event)
        if event.type == "text_delta":
            result_text += event.data

    assert runner.get_conversation_id() is not None
    assert len(runner.messages) >= 1  # User message added
    assert "张先生" in result_text
