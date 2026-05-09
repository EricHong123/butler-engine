"""
Tests for Phase 4: Review queue, encryption, budget enforcement, and audit logging.
"""

import pytest

from butler.review.queue import ReviewQueue, ReviewTicket, TicketPriority, TicketStatus
from butler.tenants.encryption import TenantEncryption


class TestReviewQueue:
    @pytest.mark.asyncio
    async def test_submit_and_list(self):
        queue = ReviewQueue()
        ticket = await queue.submit(
            tenant_id="test-tenant",
            from_user="user_001",
            to_user="agent_001",
            customer_query="我该不该卖掉北京的房产？",
            draft_response="建议您根据市场情况...",
            reason="major_financial",
            priority=TicketPriority.URGENT,
        )

        assert ticket.ticket_id.startswith("REV-")
        assert ticket.status == TicketStatus.PENDING
        assert ticket.sla_seconds == 300

        pending = await queue.list_pending()
        assert len(pending) == 1
        assert pending[0].ticket_id == ticket.ticket_id

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        queue = ReviewQueue()

        # Submit standard first, then urgent
        await queue.submit("t", "u1", "a1", "query1", "draft1", priority=TicketPriority.STANDARD)
        await queue.submit("t", "u2", "a1", "query2", "draft2", priority=TicketPriority.URGENT)
        await queue.submit("t", "u3", "a1", "query3", "draft3", priority=TicketPriority.STANDARD)

        pending = await queue.list_pending()
        # Urgent should be first
        assert pending[0].priority == TicketPriority.URGENT
        assert len(pending) == 3

    @pytest.mark.asyncio
    async def test_claim_and_approve(self):
        queue = ReviewQueue()
        ticket = await queue.submit("t", "u1", "a1", "query", "draft")

        # Claim
        claimed = await queue.claim(ticket.ticket_id, "reviewer_zhang")
        assert claimed is not None
        assert claimed.status == TicketStatus.CLAIMED
        assert claimed.claimed_by == "reviewer_zhang"

        # Cannot claim again
        claimed2 = await queue.claim(ticket.ticket_id, "reviewer_li")
        assert claimed2 is None

        # Approve
        approved = await queue.approve(ticket.ticket_id, "最终回复：建议您联系陈律师。", "已修改措辞")
        assert approved is not None
        assert approved.status == TicketStatus.APPROVED
        assert "陈律师" in approved.final_response or "陈律师" in str(approved.final_response)
        assert approved.reviewer_notes == "已修改措辞"

    @pytest.mark.asyncio
    async def test_reject_workflow(self):
        queue = ReviewQueue()
        ticket = await queue.submit("t", "u1", "a1", "query", "draft")
        await queue.claim(ticket.ticket_id, "reviewer_zhang")
        rejected = await queue.reject(ticket.ticket_id, "需要更详细的税务分析")

        assert rejected is not None
        assert rejected.status == TicketStatus.REJECTED

    @pytest.mark.asyncio
    async def test_overdue_detection(self):
        queue = ReviewQueue()
        ticket = await queue.submit(
            "t", "u1", "a1", "query", "draft",
            priority=TicketPriority.URGENT,
        )
        # SLA is 300 seconds, just created should not be overdue
        assert not ticket.is_overdue

        # Manually backdate to trigger overdue
        from datetime import datetime, timedelta, timezone
        ticket.created_at = datetime.now(tz=timezone.utc) - timedelta(seconds=600)
        assert ticket.is_overdue

    @pytest.mark.asyncio
    async def test_mark_sent(self):
        queue = ReviewQueue()
        ticket = await queue.submit("t", "u1", "a1", "query", "draft")
        await queue.claim(ticket.ticket_id, "reviewer")
        await queue.approve(ticket.ticket_id, "final response")
        sent = await queue.mark_sent(ticket.ticket_id)

        assert sent is not None
        assert sent.status == TicketStatus.SENT

    @pytest.mark.asyncio
    async def test_stats(self):
        queue = ReviewQueue()
        await queue.submit("t", "u1", "a1", "q", "d", priority=TicketPriority.URGENT)
        await queue.submit("t", "u2", "a1", "q", "d", priority=TicketPriority.STANDARD)
        await queue.submit("t", "u3", "a1", "q", "d", priority=TicketPriority.STANDARD)

        stats = await queue.get_stats()
        assert stats["total_pending"] == 3
        assert stats["urgent_pending"] == 1
        assert stats["standard_pending"] == 2
        assert stats["total_claimed"] == 0


class TestEncryption:
    def test_encrypt_decrypt_field(self):
        enc = TenantEncryption("ab" * 32)  # Deterministic test key
        plaintext = "张伟"

        encrypted = enc.encrypt_field("tenant-001", plaintext)
        assert encrypted != plaintext
        assert len(encrypted) > 0

        decrypted = enc.decrypt_field("tenant-001", encrypted)
        assert decrypted == plaintext

    def test_different_tenants_different_keys(self):
        enc = TenantEncryption("ab" * 32)

        encrypted_a = enc.encrypt_field("tenant-A", "test")
        encrypted_b = enc.encrypt_field("tenant-B", "test")

        # Same plaintext, different ciphertexts (different keys)
        assert encrypted_a != encrypted_b

        # Each tenant decrypts correctly
        assert enc.decrypt_field("tenant-A", encrypted_a) == "test"
        assert enc.decrypt_field("tenant-B", encrypted_b) == "test"

        # Cross-tenant decryption should fail
        assert enc.decrypt_field("tenant-A", encrypted_b) == ""

    def test_encrypt_empty_string(self):
        enc = TenantEncryption("ab" * 32)
        assert enc.encrypt_field("t", "") == ""
        assert enc.decrypt_field("t", "") == ""

    def test_encrypt_dict(self):
        enc = TenantEncryption("ab" * 32)
        data = {
            "name": "张伟",
            "wechat_id": "zhang_wei_001",
            "phone": "13800138000",
            "email": "zhang@example.com",
            "preference": "morning reports",
        }

        encrypted = enc.encrypt_dict(
            "t", data, sensitive_keys={"name", "phone", "email"}
        )

        # Sensitive fields should be encrypted
        assert encrypted["name"] != "张伟"
        assert encrypted["phone"] != "13800138000"
        assert encrypted["email"] != "zhang@example.com"
        # Non-sensitive fields should be untouched
        assert encrypted["wechat_id"] == "zhang_wei_001"
        assert encrypted["preference"] == "morning reports"

        # Decrypt back
        decrypted = enc.decrypt_dict(
            "t", encrypted, sensitive_keys={"name", "phone", "email"}
        )
        assert decrypted["name"] == "张伟"
        assert decrypted["phone"] == "13800138000"
        assert decrypted["email"] == "zhang@example.com"

    def test_key_rotation(self):
        enc = TenantEncryption("ab" * 32)

        # Encrypt with first key
        encrypted = enc.encrypt_field("tenant-001", "original data")

        # Create a second key
        from butler.tenants.encryption import DataKey
        import os
        new_key = DataKey(
            key_id="dk-tenant-001-2",
            key_material=os.urandom(32),
        )
        enc._data_keys["tenant-001"].append(new_key)

        # Old data still decrypts with old key (both keys stored)
        decrypted = enc.decrypt_field("tenant-001", encrypted)
        assert decrypted == "original data"

        # New encryption uses active key (still the first one since we didn't deactivate)
        new_encrypted = enc.encrypt_field("tenant-001", "new data")
        assert enc.decrypt_field("tenant-001", new_encrypted) == "new data"


class TestBudgetEnforcement:
    """Verify AgentRunner budget tracking."""

    def test_initial_under_budget(self):
        from butler.engine.agent_runner import AgentRunner, AgentRunnerConfig
        from butler.engine.tool_registry import ToolRegistry

        config = AgentRunnerConfig(
            tenant_id="test",
            tools=ToolRegistry(),
            max_budget_usd=5.0,
        )
        runner = AgentRunner(config)
        assert not runner.is_over_budget
        assert runner.estimated_cost_usd == 0.0

    def test_over_budget_after_heavy_usage(self):
        from butler.engine.agent_runner import AgentRunner, AgentRunnerConfig
        from butler.engine.tool_registry import ToolRegistry

        config = AgentRunnerConfig(
            tenant_id="test",
            tools=ToolRegistry(),
            max_budget_usd=0.01,  # Very low budget
        )
        runner = AgentRunner(config)
        # Simulate heavy token usage
        runner._token_input = 500_000   # ~$1.50
        runner._token_output = 500_000  # ~$7.50
        # Total: ~$9.00

        assert runner.is_over_budget
        assert runner.estimated_cost_usd > 0.01
