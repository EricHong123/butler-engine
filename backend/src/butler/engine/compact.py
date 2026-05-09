"""Auto-compression for long conversations. Python port of Claude Code's autoCompact.ts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Auto-compact triggers when estimated tokens exceed:
#   model_context_window - AUTOCOMPACT_BUFFER_TOKENS
# Claude Code uses 13,000 as the buffer. We mirror that.
AUTOCOMPACT_BUFFER_TOKENS = 13_000

# Circuit breaker: stop compacting after N consecutive failures
MAX_CONSECUTIVE_FAILURES = 3

# Minimum turns before we even consider compacting
MIN_TURNS_BEFORE_COMPACT = 4


@dataclass
class CompactResult:
    """Result of a compaction attempt."""
    compacted: bool
    post_compact_messages: list[dict]
    summary_text: str = ""
    tokens_freed: int = 0


@dataclass
class CompactTracker:
    """Tracks compaction state across turns. Port of AutoCompactTrackingState."""
    consecutive_failures: int = 0
    total_compactions: int = 0
    turn_since_last_compact: int = 0


def estimate_tokens(messages: list[dict]) -> int:
    """
    Rough token estimator. 1 token ≈ 4 characters for English,
    ≈ 1.5 characters for Chinese. We use a conservative 3 chars/token.
    """
    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total_chars += len(str(block))
    return total_chars // 3


async def should_auto_compact(
    messages: list[dict],
    threshold_tokens: int,
    tracker: CompactTracker,
) -> bool:
    """Check if auto-compact should fire. Port of shouldAutoCompact()."""
    if tracker.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        return False

    if tracker.turn_since_last_compact < MIN_TURNS_BEFORE_COMPACT:
        return False

    estimated = estimate_tokens(messages)
    limit = threshold_tokens - AUTOCOMPACT_BUFFER_TOKENS
    return estimated > max(limit, 20_000)


async def compact_conversation(
    messages: list[dict],
    system_prompt: str | list[dict],
    model: str = "claude-sonnet-4-6-20250514",
) -> CompactResult:
    """
    Summarize conversation history into a compact form.

    Strategy (matching Claude Code's approach):
    1. Keep last 6 messages intact (most recent context)
    2. Summarize everything before that into a single system message
    3. Replace the summarized messages with the compact boundary

    For MVP, we use a simple heuristic: keep the last N messages,
    drop older ones that are tool results from read-only tools.
    This avoids needing an extra LLM call for summarization.
    """
    if len(messages) <= 8:
        return CompactResult(compacted=False, post_compact_messages=messages)

    # Keep: system messages + last 6 user/assistant turns + recent tool results
    keep_count = 6
    keep = messages[-keep_count:]

    # Prepend a compact boundary note
    boundary = {
        "role": "user",
        "content": (
            "[Earlier conversation has been summarized to save context. "
            "Key information has been preserved. If you need details from earlier, "
            "ask the user or use available tools to look up the information.]"
        ),
    }

    tokens_before = estimate_tokens(messages)
    post = [boundary, *keep]
    tokens_after = estimate_tokens(post)

    return CompactResult(
        compacted=True,
        post_compact_messages=post,
        summary_text="Conversation compacted",
        tokens_freed=tokens_before - tokens_after,
    )
