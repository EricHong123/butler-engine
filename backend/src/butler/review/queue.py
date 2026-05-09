"""
Human-in-the-loop review queue. Redis-backed priority queue for AI responses
that need expert review before being sent to the customer.

Queue design:
  - Two priority levels: urgent (5 min SLA) and standard (30 min SLA)
  - Ticket lifecycle: pending → claimed → approved/rejected → sent/discarded
  - In-memory fallback for MVP (no Redis dependency)
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TicketStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"
    EXPIRED = "expired"


class TicketPriority(str, Enum):
    URGENT = "urgent"    # 5 min SLA
    STANDARD = "standard"  # 30 min SLA


@dataclass
class ReviewTicket:
    """A single review ticket."""
    ticket_id: str
    tenant_id: str
    from_user: str
    to_user: str
    customer_query: str
    draft_response: str
    reason: str
    priority: TicketPriority
    status: TicketStatus = TicketStatus.PENDING
    claimed_by: str | None = None
    final_response: str | None = None
    reviewer_notes: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    claimed_at: datetime | None = None
    resolved_at: datetime | None = None
    sla_seconds: int = 300

    @property
    def is_overdue(self) -> bool:
        if self.status not in (TicketStatus.PENDING, TicketStatus.CLAIMED):
            return False
        now = datetime.now(tz=timezone.utc)
        elapsed = (now - self.created_at).total_seconds()
        return elapsed > self.sla_seconds

    @property
    def elapsed_seconds(self) -> float:
        return (datetime.now(tz=timezone.utc) - self.created_at).total_seconds()


class ReviewQueue:
    """
    Priority review queue. In-memory implementation for MVP.
    Post-MVP: Replace with Redis sorted sets (ZADD by priority + timestamp).
    """

    def __init__(self) -> None:
        self._tickets: dict[str, ReviewTicket] = {}
        self._pending_urgent: list[str] = []
        self._pending_standard: list[str] = []
        self._lock = asyncio.Lock()

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
        """Submit a new ticket for review."""
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

        async with self._lock:
            self._tickets[ticket.ticket_id] = ticket
            if priority == TicketPriority.URGENT:
                self._pending_urgent.append(ticket.ticket_id)
            else:
                self._pending_standard.append(ticket.ticket_id)

        return ticket

    async def list_pending(self, limit: int = 50) -> list[ReviewTicket]:
        """List pending tickets, urgent first."""
        async with self._lock:
            urgent = [self._tickets[tid] for tid in self._pending_urgent if tid in self._tickets]
            standard = [self._tickets[tid] for tid in self._pending_standard if tid in self._tickets]
            return (urgent + standard)[:limit]

    async def list_all(
        self, status: TicketStatus | None = None, limit: int = 50
    ) -> list[ReviewTicket]:
        """List tickets, optionally filtered by status."""
        tickets = list(self._tickets.values())
        if status:
            tickets = [t for t in tickets if t.status == status]
        tickets.sort(key=lambda t: t.created_at, reverse=True)
        return tickets[:limit]

    async def claim(self, ticket_id: str, reviewer: str) -> ReviewTicket | None:
        """Claim a ticket for review."""
        async with self._lock:
            ticket = self._tickets.get(ticket_id)
            if ticket is None or ticket.status != TicketStatus.PENDING:
                return None
            ticket.status = TicketStatus.CLAIMED
            ticket.claimed_by = reviewer
            ticket.claimed_at = datetime.now(tz=timezone.utc)

            # Remove from pending lists
            if ticket_id in self._pending_urgent:
                self._pending_urgent.remove(ticket_id)
            if ticket_id in self._pending_standard:
                self._pending_standard.remove(ticket_id)

            return ticket

    async def approve(
        self, ticket_id: str, final_response: str, reviewer_notes: str = ""
    ) -> ReviewTicket | None:
        """Approve a ticket with final response."""
        async with self._lock:
            ticket = self._tickets.get(ticket_id)
            if ticket is None or ticket.status != TicketStatus.CLAIMED:
                return None
            ticket.status = TicketStatus.APPROVED
            ticket.final_response = final_response
            ticket.reviewer_notes = reviewer_notes
            ticket.resolved_at = datetime.now(tz=timezone.utc)
            return ticket

    async def reject(
        self, ticket_id: str, reason: str, reviewer_notes: str = ""
    ) -> ReviewTicket | None:
        """Reject a ticket (draft needs rewrite)."""
        async with self._lock:
            ticket = self._tickets.get(ticket_id)
            if ticket is None or ticket.status != TicketStatus.CLAIMED:
                return None
            ticket.status = TicketStatus.REJECTED
            ticket.reviewer_notes = reviewer_notes
            ticket.resolved_at = datetime.now(tz=timezone.utc)
            return ticket

    async def mark_sent(self, ticket_id: str) -> ReviewTicket | None:
        """Mark a ticket as sent to the customer."""
        async with self._lock:
            ticket = self._tickets.get(ticket_id)
            if ticket is None or ticket.status != TicketStatus.APPROVED:
                return None
            ticket.status = TicketStatus.SENT
            return ticket

    async def get_ticket(self, ticket_id: str) -> ReviewTicket | None:
        """Get a single ticket by ID."""
        async with self._lock:
            return self._tickets.get(ticket_id)

    async def get_stats(self) -> dict[str, Any]:
        """Get queue statistics."""
        async with self._lock:
            all_tickets = list(self._tickets.values())
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


def _avg_resolution(tickets: list[ReviewTicket]) -> float:
    resolved = [
        t for t in tickets
        if t.resolved_at and t.status in (TicketStatus.APPROVED, TicketStatus.REJECTED)
    ]
    if not resolved:
        return 0.0
    return sum((t.resolved_at - t.created_at).total_seconds() for t in resolved) / len(resolved)


# Global singleton — auto-detects Redis, falls back to in-memory
_review_queue: ReviewQueue | None = None
_queue_type: str = ""


async def get_review_queue() -> tuple[ReviewQueue, str]:
    """Get review queue. Returns (queue, backend_type). backend_type is 'redis' or 'memory'."""
    global _review_queue, _queue_type
    if _review_queue is not None:
        return _review_queue, _queue_type
    try:
        from butler.services.redis_client import get_redis
        redis = await get_redis()
        if redis:
            from butler.review.redis_queue import RedisReviewQueue
            _review_queue = RedisReviewQueue(redis)
            _queue_type = "redis"
            return _review_queue, _queue_type
    except Exception:
        pass
    _review_queue = ReviewQueue()
    _queue_type = "memory"
    return _review_queue, _queue_type


def get_review_queue_sync() -> ReviewQueue:
    """Sync version — always returns in-memory queue (for imports)."""
    return ReviewQueue()
