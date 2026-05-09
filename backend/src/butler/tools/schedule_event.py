"""Tool: Schedule, check, or modify appointments and reminders."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from butler.engine.base_tool import BaseTool, ToolResult


class ScheduleInput(BaseModel):
    """Input for scheduling operations."""
    action: str = Field(description="Action: 'check', 'book', 'cancel', or 'list'")
    title: str | None = Field(default=None, description="Event title or description")
    datetime_str: str | None = Field(default=None, description="Date/time in ISO format, e.g. '2026-05-15T14:00'")
    duration_minutes: int = Field(default=60, ge=15, le=480, description="Duration in minutes")
    participants: str | None = Field(default=None, description="Participants or context")
    priority: str = Field(default="normal", description="Priority: 'low', 'normal', 'high', 'urgent'")


class ScheduleEventTool(BaseTool):
    """
    Manage the family's calendar: book appointments, check availability,
    list upcoming events, and set reminders.
    """

    name = "schedule_event"
    aliases = ["日程", "预约", "提醒", "日历"]
    search_hint = "calendar schedule appointment booking reminder event"

    def is_read_only(self, input: dict | None = None) -> bool:
        return input.get("action") in ("check", "list") if input else False

    async def call(self, args: dict, context: Any) -> ToolResult:
        action = args.get("action", "list")
        title = args.get("title", "")
        datetime_str = args.get("datetime_str", "")
        duration = args.get("duration_minutes", 60)
        priority = args.get("priority", "normal")

        existing_events = _get_mock_events()

        if action == "list":
            return ToolResult(data={
                "events": existing_events,
                "total": len(existing_events),
                "action": "list",
            })

        elif action == "check":
            if datetime_str:
                conflicts = [
                    e for e in existing_events
                    if e["datetime"] == datetime_str
                ]
                return ToolResult(data={
                    "is_available": len(conflicts) == 0,
                    "conflicts": conflicts,
                    "requested_time": datetime_str,
                    "action": "check",
                })
            return ToolResult(data={
                "events": existing_events[:5],
                "action": "check",
            })

        elif action == "book":
            if not title or not datetime_str:
                return ToolResult(data={
                    "error": "title and datetime_str are required for booking",
                    "action": "book",
                })
            return ToolResult(data={
                "status": "booked",
                "event": {
                    "title": title,
                    "datetime": datetime_str,
                    "duration_minutes": duration,
                    "priority": priority,
                    "participants": args.get("participants", ""),
                },
                "action": "book",
            })

        elif action == "cancel":
            return ToolResult(data={
                "status": "cancelled",
                "title": title,
                "action": "cancel",
            })

        return ToolResult(data={"error": f"Unknown action: {action}"})

    async def description(self, input: dict, options: dict) -> str:
        action = input.get("action", "list")
        title = input.get("title", "")
        return f"Calendar: {action} {title}".strip()

    def input_schema(self) -> type[BaseModel]:
        return ScheduleInput


def _get_mock_events() -> list[dict[str, Any]]:
    """Mock calendar events."""
    return [
        {
            "title": "季度资产回顾会议（与陈律师）",
            "datetime": "2026-05-15T14:00",
            "duration_minutes": 60,
            "priority": "high",
            "participants": "陈律师 (Li & Partners)",
            "location": "视频会议",
        },
        {
            "title": "洪明 SAT 考试",
            "datetime": "2026-06-07T08:00",
            "duration_minutes": 240,
            "priority": "high",
            "participants": "洪明",
            "location": "上海美国学校",
        },
        {
            "title": "友邦保险保费到期",
            "datetime": "2026-06-01T09:00",
            "duration_minutes": 15,
            "priority": "normal",
            "participants": "",
            "location": "",
        },
        {
            "title": "香港物业税申报截止",
            "datetime": "2026-05-31T23:59",
            "duration_minutes": 15,
            "priority": "urgent",
            "participants": "会计师",
            "location": "",
        },
        {
            "title": "洪悦钢琴比赛",
            "datetime": "2026-05-20T10:00",
            "duration_minutes": 120,
            "priority": "normal",
            "participants": "洪悦",
            "location": "上海音乐学院",
        },
    ]
