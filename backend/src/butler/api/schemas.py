"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message text")
    conversation_id: str | None = Field(None, description="Existing conversation ID to continue")
    agent_type: str = Field("butler", description="Agent type: butler, wealth_advisor, document_secretary, schedule_manager, education_advisor, health_advisor")
    tenant_id: str = Field("demo-001", description="Tenant identifier")


class ChatStreamEvent(BaseModel):
    type: str  # text_delta, tool_call, tool_result, error, done
    data: str | dict | None = None
    conversation_id: str | None = None


class HealthResponse(BaseModel):
    status: str
    app: str
