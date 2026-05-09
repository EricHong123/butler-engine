"""Tool: Escalate a customer request to a human expert for review."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from butler.engine.base_tool import BaseTool, ToolResult


class EscalateInput(BaseModel):
    """Input for escalating to human review."""
    reason: str = Field(description="Why this needs human review: 'legal_advice', 'medical_advice', 'major_financial', 'tax_advice', 'complaint', 'other'")
    priority: str = Field(default="standard", description="Priority: 'urgent' (5min SLA), 'standard' (30min SLA)")
    context: str | None = Field(default=None, description="Brief context for the human reviewer")
    draft_response: str | None = Field(default=None, description="AI's draft response that needs review before sending")


class EscalateToHumanTool(BaseTool):
    """
    Flag a customer request that requires human expert review before responding.

    Used when:
    - Customer asks for legal, medical, or major financial advice
    - Customer is dissatisfied and needs escalation
    - Response involves specific amounts, rates, or recommendations
    - AI is uncertain about accuracy or appropriateness
    """

    name = "escalate_to_human"
    aliases = ["转人工", "专家审核", "升级"]
    search_hint = "escalate human review expert approval flag"

    def is_read_only(self, input: dict | None = None) -> bool:
        return False  # Creates a review ticket

    def is_concurrency_safe(self, input: dict | None = None) -> bool:
        return True

    async def call(self, args: dict, context: Any) -> ToolResult:
        reason = args.get("reason", "other")
        priority = args.get("priority", "standard")
        ctx_text = args.get("context", "")
        draft = args.get("draft_response", "")

        ticket_id = f"REV-{uuid.uuid4().hex[:8].upper()}"

        # In production, this pushes to Redis queue and notifies reviewers.
        # For MVP, we return the ticket with instructions for manual handling.
        review_ticket = {
            "ticket_id": ticket_id,
            "reason": reason,
            "priority": priority,
            "sla_minutes": 5 if priority == "urgent" else 30,
            "context": ctx_text,
            "draft_response": draft,
            "status": "pending_review",
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "tenant_id": getattr(context, "tenant_id", "unknown"),
        }

        return ToolResult(data=review_ticket)

    async def description(self, input: dict, options: dict) -> str:
        reason = input.get("reason", "general")
        return f"Escalate to human review: {reason}"

    def input_schema(self) -> type[BaseModel]:
        return EscalateInput
