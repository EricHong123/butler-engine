"""
Unified audit logging. Provides a single entry point for all security-relevant
events across the agent pipeline.

Audit entries are append-only and include:
  - timestamp (automatic via model)
  - tenant_id (who's data)
  - agent_type (which persona)
  - user_id (which family member)
  - action (what happened)
  - tool_name (which tool, if any)
  - input_hash (SHA-256 of user/tool input, for privacy)
  - output_hash (SHA-256 of agent/tool output)
  - details (human-readable context)
"""

from __future__ import annotations

import hashlib
import json
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AuditEntry:
    """A single audit record. Mirrors AuditLog model structure."""
    tenant_id: str
    action: str
    actor: str = "system"
    agent_type: str = ""
    user_id: str = ""
    tool_name: str = ""
    input_hash: str = ""
    output_hash: str = ""
    details: str = ""
    turn_count: int = 0
    elapsed_ms: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def to_db_row(self) -> dict[str, Any]:
        """Convert to dict for DB insertion."""
        detail_parts = []
        if self.agent_type:
            detail_parts.append(f"agent={self.agent_type}")
        if self.user_id:
            detail_parts.append(f"user={self.user_id}")
        if self.tool_name:
            detail_parts.append(f"tool={self.tool_name}")
        if self.turn_count:
            detail_parts.append(f"turn={self.turn_count}")
        if self.elapsed_ms:
            detail_parts.append(f"elapsed={self.elapsed_ms:.0f}ms")
        if self.input_hash:
            detail_parts.append(f"in_hash={self.input_hash[:12]}")
        if self.output_hash:
            detail_parts.append(f"out_hash={self.output_hash[:12]}")
        if self.details:
            detail_parts.append(self.details)

        return {
            "tenant_id": self.tenant_id,
            "action": self.action,
            "actor": self.actor,
            "details": "; ".join(detail_parts)[:2000],  # Truncate for DB
        }


def hash_content(content: str) -> str:
    """Create a SHA-256 hash of content for audit (privacy-preserving)."""
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()


async def write_audit(entry: AuditEntry) -> None:
    """Persist an audit entry to the database. Non-blocking best-effort."""
    try:
        from butler.repositories.conversation_repo import AuditLogRepo
        from butler.services.database import get_sessionmaker
        row = entry.to_db_row()
        async with get_sessionmaker()() as s:
            repo = AuditLogRepo(s)
            await repo.log(
                tenant_id=row["tenant_id"],
                action=row["action"],
                actor=row["actor"],
                details=row["details"],
            )
            await s.commit()
    except Exception:
        pass  # Audit is best-effort — never crash the main flow


async def audit_conversation_start(
    tenant_id: str,
    agent_type: str,
    user_id: str = "",
    conversation_id: str = "",
) -> None:
    """Log conversation start."""
    await write_audit(AuditEntry(
        tenant_id=tenant_id,
        action="conversation_start",
        actor="customer",
        agent_type=agent_type,
        user_id=user_id,
        details=f"conv={conversation_id}" if conversation_id else "",
    ))


async def audit_conversation_end(
    tenant_id: str,
    agent_type: str,
    user_id: str = "",
    turn_count: int = 0,
    elapsed_ms: float = 0.0,
    conversation_id: str = "",
) -> None:
    """Log conversation end."""
    await write_audit(AuditEntry(
        tenant_id=tenant_id,
        action="conversation_end",
        actor="customer",
        agent_type=agent_type,
        user_id=user_id,
        turn_count=turn_count,
        elapsed_ms=elapsed_ms,
        details=f"conv={conversation_id}" if conversation_id else "",
    ))


async def audit_tool_call(
    tenant_id: str,
    tool_name: str,
    tool_input: dict,
    tool_output: str,
    agent_type: str = "",
    user_id: str = "",
) -> None:
    """Log a tool invocation."""
    input_str = json.dumps(tool_input, ensure_ascii=False, sort_keys=True)
    await write_audit(AuditEntry(
        tenant_id=tenant_id,
        action="tool_call",
        actor="system",
        agent_type=agent_type,
        user_id=user_id,
        tool_name=tool_name,
        input_hash=hash_content(input_str)[:16],
        output_hash=hash_content(tool_output)[:16],
        details=input_str[:200],
    ))


async def audit_turn(
    tenant_id: str,
    user_input: str = "",
    agent_output: str = "",
    agent_type: str = "",
    user_id: str = "",
    turn_count: int = 0,
) -> None:
    """Log a single conversation turn (user message → agent response)."""
    await write_audit(AuditEntry(
        tenant_id=tenant_id,
        action="chat_turn",
        actor="customer",
        agent_type=agent_type,
        user_id=user_id,
        turn_count=turn_count,
        input_hash=hash_content(user_input)[:16],
        output_hash=hash_content(agent_output)[:16],
    ))


async def audit_security_event(
    tenant_id: str,
    event_type: str,
    details: str = "",
    agent_type: str = "",
    user_id: str = "",
) -> None:
    """Log a security-relevant event (injection attempt, auth failure, etc.)."""
    await write_audit(AuditEntry(
        tenant_id=tenant_id,
        action=f"security.{event_type}",
        actor="system",
        agent_type=agent_type,
        user_id=user_id,
        details=details[:500],
    ))
