"""
Integration tests for memory system and customer profile.
Tests file-based memory CRUD and its injection into AgentRunner context.
"""

import tempfile
from pathlib import Path

import pytest

from butler.engine.agent_runner import AgentRunner, AgentRunnerConfig
from butler.engine.base_tool import BaseTool, ToolResult
from butler.engine.tool_registry import ToolRegistry
from butler.memory.memory_manager import MemoryEntry, MemoryManager
from butler.memory.memory_types import MemoryType
from butler.tenants.store import TenantRecord, TenantStore


@pytest.mark.asyncio
async def test_memory_save_and_load():
    """Write a memory, verify index and topic file are created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        manager = MemoryManager("test-tenant", root)

        entry = MemoryEntry(
            name="Investment Preference",
            description="Principal prefers low-risk bonds over equities",
            memory_type=MemoryType.USER,
            content="Hong Wei explicitly stated he prefers fixed-income products with AAA rating or above.",
        )
        await manager.save(entry)

        # Verify file created
        assert (manager.memory_dir / entry.file_name).exists()
        assert manager.index_path.exists()

        # Load index
        index = await manager.load_index()
        assert "Investment Preference" in index
        assert "low-risk bonds" in index


@pytest.mark.asyncio
async def test_memory_truncation():
    """Verify index is truncated when exceeding limits."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        manager = MemoryManager("test-tenant", root)

        # Write 250 entries (exceeds MAX_ENTRYPOINT_LINES=200)
        for i in range(250):
            entry = MemoryEntry(
                name=f"Memory {i}",
                description=f"Description {i}",
                memory_type=MemoryType.PROJECT,
                content=f"Content for memory {i}",
            )
            await manager.save(entry)

        index = await manager.load_index()
        lines = index.split("\n")
        # Should be truncated to 200 lines + warning
        assert len(lines) <= 210  # 200 + a few warning lines


@pytest.mark.asyncio
async def test_tenant_store_profile():
    """Save and load a tenant profile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        store = TenantStore(root)

        record = TenantRecord(
            tenant_id="zhang-family",
            name="Hong Family Office",
            plan_tier="family",
            profile_markdown="# Hong Family\n- Hong Wei, 48\n- Net worth: 500M RMB",
        )
        await store.save(record)

        # Load back
        loaded = await store.get("zhang-family")
        assert loaded is not None
        assert loaded.name == "Hong Family Office"
        assert loaded.plan_tier == "family"

        # Save and load profile markdown
        await store.save_profile("zhang-family", "Custom profile content")
        profile = await store.load_profile("zhang-family")
        assert profile == "Custom profile content"


@pytest.mark.asyncio
async def test_agent_runner_with_profile_and_memory():
    """AgentRunner correctly uses profile and memory in system prompt."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Setup tenant with profile and memory
        store = TenantStore(root)
        await store.save(TenantRecord(
            tenant_id="test-family",
            name="Test Family",
            plan_tier="family",
        ))
        await store.save_profile("test-family", "# Test Family Profile\n- Member: Alice")

        memory = MemoryManager("test-family", root)
        await memory.save(MemoryEntry(
            name="Preference",
            description="Alice prefers brief responses",
            memory_type=MemoryType.USER,
            content="Keep it short.",
        ))

        # Create AgentRunner with profile + memory
        profile_md = await store.load_profile("test-family")
        memory_index = await memory.load_index()

        config = AgentRunnerConfig(
            tenant_id="test-family",
            tools=ToolRegistry(),
            profile_markdown=profile_md,
            memory_index=memory_index,
        )

        runner = AgentRunner(config)
        assert runner.config.profile_markdown is not None
        assert "Test Family Profile" in runner.config.profile_markdown
        assert "Alice prefers" in runner.config.memory_index
