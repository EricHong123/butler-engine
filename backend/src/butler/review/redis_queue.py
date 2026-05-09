"""
Redis-backed review queue. Same API as ReviewQueue,
but stores tickets in Redis for persistence across restarts.

Data model:
  HSET butler:review:ticket:{id}  → JSON of ReviewTicket
  ZSET butler:review:pending      → {ticket_id: score}  (urgent=0, standard=1 by timestamp)
  ZSET butler:review:pending:urgent → {ticket_id: timestamp}
  ZSET butler:review:pending:std   → {ticket_id: timestamp}
"""

from __future__ import annotations

import json
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

from butler.review.queue import (
    ReviewTicket,
    TicketPriority,
    TicketStatus,
    _avg_resolution,
)


class RedisReviewQueue:
    """Redis-backed priority review queue. Drop-in replacement for ReviewQueue."""

    PREFIX = "butler:review"
    TICKET_KEY = f"{PREFIX}:ticket:{{id}}"
    PENDING_ZSET = f"{PREFIX}:pending"
    URGENT_ZSET = f"{PREFIX}:pending:urgent"
    STANDARD_ZSET = f"{PREFIX}:pending:std"

    def __init__(self, redis: Redis):
        self._redis = redis

    # ── Serialization ──

    def _serialize(self, ticket: ReviewTicket) -> dict:
        return {
            "ticket_id": ticket.ticket_id,
            "tenant_id": ticket.tenant_id,
            "from_user": ticket.from_user,
            "to_user": ticket.to_user,
            "customer_query": ticket.customer_query,
            "draft_response": ticket.draft_response,
            "reason": ticket.reason,
            "priority": ticket.priority.value,
            "status": ticket.status.value,
            "claimed_by": ticket.claimed_by or "",
            "final_response": ticket.final_response or "",
            "reviewer_notes": ticket.reviewer_notes or "",
            "created_at": ticket.created_at.isoformat(),
            "claimed_at": ticket.claimed_at.isoformat() if ticket.claimed_at else "",
            "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else "",
            "sla_seconds": str(ticket.sla_seconds),
        }

    def _deserialize(self, data: dict) -> ReviewTicket:
        def _dt(s: str) -> datetime | None:
            return datetime.fromisoformat(s) if s else None

        return ReviewTicket(
            ticket_id=data["ticket_id"],
            tenant_id=data["tenant_id"],
            from_user=data["from_user"],
            to_user=data["to_user"],
            customer_query=data["customer_query"],
            draft_response=data["draft_response"],
            reason=data["reason"],
            priority=TicketPriority(data["priority"]),
            status=TicketStatus(data.get("status", "pending")),
            claimed_by=data.get("claimed_by") or None,
            final_response=data.get("final_response") or None,
            reviewer_notes=data.get("reviewer_notes") or None,
            created_at=_dt(data["created_at"]) or datetime.now(tz=timezone.utc),
            claimed_at=_dt(data.get("claimed_at", "")),
            resolved_at=_dt(data.get("resolved_at", "")),
            sla_seconds=int(data.get("sla_seconds", 300)),
        )

    async def _save(self, ticket: ReviewTicket) -> None:
        key = self.TICKET_KEY.format(id=ticket.ticket_id)
        await self._redis.hset(key, mapping=self._serialize(ticket))

    async def _load(self, ticket_id: str) -> ReviewTicket | None:
        key = self.TICKET_KEY.format(id=ticket_id)
        data = await self._redis.hgetall(key)
        if not data:
            return None
        return self._deserialize(data)

    # ── Public API ──

    async def submit(
        self,
        tenant_id: str,
        from_user: str,
        to_user: str,
        customer_query: str,
        draft_response: str,
        reason: str = "general",
        priority: TicketPriority = TicketPriority.STANDARD,
    ) -> ReviewTicket:
        ticket = ReviewTicket(
            ticket_id=f"REV-{uuid.uuid4().hex[:8].upper()}",
            tenant_id=tenant_id,
            from_user=from_user,
            to_user=to_user,
            customer_query=customer_query,
            draft_response=draft_response,
            reason=reason,
            priority=priority,
            sla_seconds=300 if priority == TicketPriority.URGENT else 1800,
        )

        await self._save(ticket)

        # Add to pending sets with score = timestamp
        score = ticket.created_at.timestamp()
        await self._redis.zadd(self.PENDING_ZSET, {ticket.ticket_id: score})
        if priority == TicketPriority.URGENT:
            await self._redis.zadd(self.URGENT_ZSET, {ticket.ticket_id: score})
        else:
            await self._redis.zadd(self.STANDARD_ZSET, {ticket.ticket_id: score})

        return ticket

    async def list_pending(self, limit: int = 50) -> list[ReviewTicket]:
        # Urgent first (lowest score), then standard
        urgent_ids = await self._redis.zrange(self.URGENT_ZSET, 0, limit - 1)
        std_ids = await self._redis.zrange(self.STANDARD_ZSET, 0, limit - len(urgent_ids) - 1)

        tickets = []
        for tid in urgent_ids + std_ids:
            t = await self._load(tid)
            if t and t.status == TicketStatus.PENDING:
                tickets.append(t)
        return tickets[:limit]

    async def list_all(
        self, status: TicketStatus | None = None, limit: int = 50
    ) -> list[ReviewTicket]:
        # Scan all ticket keys
        pattern = self.TICKET_KEY.format(id="*")
        tickets = []
        async for key in self._redis.scan_iter(match=pattern, count=100):
            tid = key.split(":")[-1]
            t = await self._load(tid)
            if t:
                if status and t.status != status:
                    continue
                tickets.append(t)
            if len(tickets) >= limit:
                break

        tickets.sort(key=lambda t: t.created_at, reverse=True)
        return tickets[:limit]

    async def claim(self, ticket_id: str, reviewer: str) -> ReviewTicket | None:
        ticket = await self._load(ticket_id)
        if ticket is None or ticket.status != TicketStatus.PENDING:
            return None

        ticket.status = TicketStatus.CLAIMED
        ticket.claimed_by = reviewer
        ticket.claimed_at = datetime.now(tz=timezone.utc)
        await self._save(ticket)

        # Remove from pending sets
        await self._redis.zrem(self.PENDING_ZSET, ticket_id)
        await self._redis.zrem(self.URGENT_ZSET, ticket_id)
        await self._redis.zrem(self.STANDARD_ZSET, ticket_id)

        return ticket

    async def approve(
        self, ticket_id: str, final_response: str, reviewer_notes: str = ""
    ) -> ReviewTicket | None:
        ticket = await self._load(ticket_id)
        if ticket is None or ticket.status != TicketStatus.CLAIMED:
            return None

        ticket.status = TicketStatus.APPROVED
        ticket.final_response = final_response
        ticket.reviewer_notes = reviewer_notes
        ticket.resolved_at = datetime.now(tz=timezone.utc)
        await self._save(ticket)
        return ticket

    async def reject(
        self, ticket_id: str, reason: str, reviewer_notes: str = ""
    ) -> ReviewTicket | None:
        ticket = await self._load(ticket_id)
        if ticket is None or ticket.status != TicketStatus.CLAIMED:
            return None

        ticket.status = TicketStatus.REJECTED
        ticket.reviewer_notes = reviewer_notes
        ticket.resolved_at = datetime.now(tz=timezone.utc)
        await self._save(ticket)
        return ticket

    async def mark_sent(self, ticket_id: str) -> ReviewTicket | None:
        ticket = await self._load(ticket_id)
        if ticket is None or ticket.status != TicketStatus.APPROVED:
            return None

        ticket.status = TicketStatus.SENT
        await self._save(ticket)
        return ticket

    async def get_ticket(self, ticket_id: str) -> ReviewTicket | None:
        """Get a single ticket by ID."""
        return await self._load(ticket_id)

    async def get_stats(self) -> dict[str, Any]:
        pattern = self.TICKET_KEY.format(id="*")
        all_tickets = []
        async for key in self._redis.scan_iter(match=pattern, count=100):
            tid = key.split(":")[-1]
            t = await self._load(tid)
            if t:
                all_tickets.append(t)

        pending = [t for t in all_tickets if t.status == TicketStatus.PENDING]
        claimed = [t for t in all_tickets if t.status == TicketStatus.CLAIMED]
        overdue = [t for t in all_tickets if t.is_overdue]

        return {
            "total_pending": len(pending),
            "total_claimed": len(claimed),
            "urgent_pending": len([t for t in pending if t.priority == TicketPriority.URGENT]),
            "standard_pending": len([t for t in pending if t.priority == TicketPriority.STANDARD]),
            "overdue": len(overdue),
            "approved_today": len([
                t for t in all_tickets
                if t.status == TicketStatus.APPROVED
                and t.resolved_at
                and t.resolved_at.date() == datetime.now(tz=timezone.utc).date()
            ]),
            "avg_resolution_seconds": _avg_resolution(all_tickets),
        }

    # Access for router compatibility
    @property
    def _tickets(self):
        """Compatibility property for router that accesses queue._tickets directly."""
        return self
