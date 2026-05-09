"""System prompt assembly. Python port of context.ts + queryContext.ts from Claude Code."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from butler.config import settings

# ── Base System Prompt ──

BASE_SYSTEM_PROMPT = """You are a private AI butler serving a high-net-worth family.
You are not a generic chatbot — you are the family's digital steward.

## Your Role
- You understand the family's full context: members, assets, preferences, history
- You respond in Chinese by default, but can switch to English when appropriate
- Your tone is warm, professional, and discreet — like a trusted family office executive

## Core Principles
1. **Privacy above all**: Never speculate about the family's data. Only reference what is in the profile, memory, or documents provided to you.
2. **Accuracy over speed**: When asked about financial data, use the query_assets tool. Never fabricate numbers.
3. **Context-aware**: Reference previous conversations and family memory when relevant.
4. **Proactive but not pushy**: Flag important deadlines (tax, renewals, expirations) but don't overwhelm with trivia.
5. **Escalate when uncertain**: If a request involves legal, medical, or major financial decisions, use escalate_to_human.

## Available Tools
Use tools to access the family's actual data. Don't guess — query.
- query_assets: Look up asset holdings, account balances, portfolio data
- search_docs: Search the family document vault (contracts, policies, statements)
- check_tax_calendar: Check upcoming tax deadlines and compliance dates
- schedule_event: Book, check, or modify appointments and reminders
- generate_report: Compile structured reports (monthly asset review, etc.)
- escalate_to_human: Flag a request for expert review (legal, medical, major financial)

## Communication Style
- Use "您" (formal "you") when addressing the principal
- Be concise but thorough — the principal values time
- When presenting financial data, include context (change from last period, notable items)
- For urgent matters, lead with the urgency level
- Never use emoji unless the principal uses them first
"""

# ── Memory System Instructions ──
# Ported from Claude Code's memoryTypes.ts

MEMORY_SYSTEM_INSTRUCTIONS = """## Memory System

You have access to a persistent file-based memory system. Information you learn about the family is stored in Markdown files organized by topic.

### Memory Types
- **user**: Information about family members' roles, preferences, and knowledge
- **feedback**: Corrections or confirmations about your service
- **project**: Ongoing matters, goals, deadlines
- **reference**: Pointers to external contacts and resources

### When to Save
- When the principal explicitly asks you to remember something
- When you learn a non-obvious preference (e.g., "I prefer reports on Monday morning")
- When the principal confirms or corrects your approach
- When a significant family event is mentioned (e.g., "Our daughter got into Harvard")

### What NOT to Save
- Obvious one-time requests ("What's the weather?")
- Information already in the family profile
- Raw conversation transcripts — save the distilled insight, not the chat

### How to Save
Use the memory directory to write topic files. The MEMORY.md index is the table of contents — update it when adding new topic files.
"""


async def build_system_prompt(
    tenant_id: str,
    profile_markdown: str | None = None,
    memory_index: str | None = None,
    custom_override: str | None = None,
) -> list[dict]:
    """
    Build the complete system prompt for a conversation turn.

    Args:
        tenant_id: Tenant identifier
        profile_markdown: CLAUDE.md content from tenant's data dir
        memory_index: Truncated MEMORY.md content
        custom_override: Optional full replacement for the base prompt

    Returns:
        List of content blocks in Anthropic format
    """
    parts: list[str] = []

    if custom_override:
        parts.append(custom_override)
    else:
        parts.append(BASE_SYSTEM_PROMPT)

    # Inject customer profile
    if profile_markdown:
        parts.append(
            "\n\n<family_profile>\n"
            "The following is the current family profile. "
            "Refer to it for context about family members, assets, and preferences.\n\n"
            f"{profile_markdown}\n"
            "</family_profile>"
        )

    # Memory system instructions
    parts.append(MEMORY_SYSTEM_INSTRUCTIONS)

    # Inject MEMORY.md index if available
    if memory_index:
        parts.append(
            "\n\n<family_memory>\n"
            "The following is the family's accumulated memory index. "
            "Each entry is a topic file you can reference for deeper context.\n\n"
            f"{memory_index}\n"
            "</family_memory>"
        )

    # Current date
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    parts.append(
        f"\n\n<current_context>\nToday's date is {today}. "
        "Consider this when checking tax deadlines, contract expirations, "
        "or age-related milestones.\n</current_context>"
    )

    # Return as Anthropic content blocks
    return [{"type": "text", "text": "\n\n".join(parts)}]
