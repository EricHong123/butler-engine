"""
Review dashboard API. REST endpoints for the human review workflow.

Endpoints:
  GET  /review/tickets         — list pending tickets
  GET  /review/tickets/{id}    — get ticket details
  POST /review/tickets/{id}/claim    — claim a ticket
  POST /review/tickets/{id}/approve  — approve with final response
  POST /review/tickets/{id}/reject   — reject with reason
  GET  /review/stats           — queue statistics
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from butler.review.queue import TicketPriority, TicketStatus, get_review_queue, get_review_queue_sync
from butler.wechat.client import WeChatAPIClient

router = APIRouter(prefix="/review", tags=["review"])

# Sync fallback for module load; endpoints use async get_review_queue()
_queue_sync = get_review_queue_sync()


async def _get_queue():
    queue, _ = await get_review_queue()
    return queue


@router.get("/tickets")
async def list_tickets(
    status: str | None = Query(None, description="Filter by status: pending, claimed, approved, rejected"),
    limit: int = Query(50, ge=1, le=200),
):
    """List review tickets, sorted by priority then creation time."""
    ticket_status = TicketStatus(status) if status else None
    q = await _get_queue()
    tickets = await q.list_all(status=ticket_status, limit=limit)

    return {
        "tickets": [
            {
                "ticket_id": t.ticket_id,
                "tenant_id": t.tenant_id,
                "from_user": t.from_user,
                "customer_query": t.customer_query[:200],
                "reason": t.reason,
                "priority": t.priority.value,
                "status": t.status.value,
                "claimed_by": t.claimed_by,
                "created_at": t.created_at.isoformat(),
                "elapsed_seconds": int(t.elapsed_seconds),
                "is_overdue": t.is_overdue,
            }
            for t in tickets
        ],
        "total": len(tickets),
    }


@router.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: str):
    """Get full details of a single ticket."""
    q = await _get_queue()
    ticket = await q.get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return {
        "ticket_id": ticket.ticket_id,
        "tenant_id": ticket.tenant_id,
        "from_user": ticket.from_user,
        "to_user": ticket.to_user,
        "customer_query": ticket.customer_query,
        "draft_response": ticket.draft_response,
        "final_response": ticket.final_response,
        "reason": ticket.reason,
        "priority": ticket.priority.value,
        "status": ticket.status.value,
        "claimed_by": ticket.claimed_by,
        "reviewer_notes": ticket.reviewer_notes,
        "created_at": ticket.created_at.isoformat(),
        "claimed_at": ticket.claimed_at.isoformat() if ticket.claimed_at else None,
        "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
        "elapsed_seconds": int(ticket.elapsed_seconds),
        "is_overdue": ticket.is_overdue,
    }


@router.post("/tickets/{ticket_id}/claim")
async def claim_ticket(ticket_id: str, reviewer: str = Query(..., description="Reviewer name or ID")):
    """Claim a ticket for review."""
    q = await _get_queue()
    ticket = await q.claim(ticket_id, reviewer)
    if ticket is None:
        raise HTTPException(status_code=409, detail="Ticket already claimed or not found")
    return {"status": "claimed", "ticket_id": ticket_id, "claimed_by": reviewer}


@router.post("/tickets/{ticket_id}/approve")
async def approve_ticket(
    ticket_id: str,
    final_response: str | None = None,
    reviewer_notes: str = "",
    send_to_customer: bool = False,
):
    """
    Approve a ticket. If final_response is provided, it overrides the draft.
    If send_to_customer is True, sends the approved response via WeChat.
    """
    q = await _get_queue()
    ticket = await q.get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    response_text = final_response or ticket.draft_response
    ticket = await q.approve(ticket_id, response_text, reviewer_notes)
    if ticket is None:
        raise HTTPException(status_code=409, detail="Ticket not in claimable state")

    if send_to_customer and response_text:
        try:
            client = WeChatAPIClient()
            result = await client.send_text_message(
                user_id=ticket.from_user,
                content=response_text,
            )
            if result.get("errcode") == 0:
                await q.mark_sent(ticket_id)
                return {"status": "sent", "ticket_id": ticket_id}
            else:
                return {
                    "status": "approved_not_sent",
                    "ticket_id": ticket_id,
                    "wechat_error": result,
                }
        except Exception as exc:
            return {
                "status": "approved_not_sent",
                "ticket_id": ticket_id,
                "error": str(exc),
            }

    return {"status": "approved", "ticket_id": ticket_id}


@router.post("/tickets/{ticket_id}/reject")
async def reject_ticket(
    ticket_id: str,
    reason: str = Query(..., description="Rejection reason for the AI to re-draft"),
    reviewer_notes: str = "",
):
    """Reject a ticket — the AI draft needs revision."""
    q = await _get_queue()
    ticket = await q.reject(ticket_id, reason, reviewer_notes)
    if ticket is None:
        raise HTTPException(status_code=409, detail="Ticket not in claimable state")
    return {"status": "rejected", "ticket_id": ticket_id, "reason": reason}


@router.get("/stats")
async def get_stats():
    """Get review queue statistics."""
    q = await _get_queue()
    return await q.get_stats()
