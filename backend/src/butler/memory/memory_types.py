"""
Memory type taxonomy. Direct port of Claude Code's memoryTypes.ts.

Defines the types of memories the AI can create, what to save,
what NOT to save, and when to access memories.
"""

from enum import Enum


class MemoryType(str, Enum):
    USER = "user"           # About family members' roles, preferences, knowledge
    FEEDBACK = "feedback"   # Corrections or validations about the service
    PROJECT = "project"     # Ongoing matters, goals, deadlines
    REFERENCE = "reference" # Pointers to external contacts and resources


# Limits — port from Claude Code
MAX_ENTRYPOINT_LINES = 200
MAX_ENTRYPOINT_BYTES = 25_000
MEMORY_FILENAME = "MEMORY.md"


# ── Memory frontmatter template ──

MEMORY_FRONTMATTER_EXAMPLE = """---
name: {{name}}
description: {{one-line description}}
type: {{user|feedback|project|reference}}
---
"""


# ── When to save memories ──

TYPES_SECTION = """## Memory Types

There are several discrete types of memory:

- **user**: Information about family members' roles, preferences, and knowledge. Save when you learn a non-obvious preference or detail that will help personalize service.
- **feedback**: Guidance the family has given about how to approach things — both what to avoid and what to keep doing.
- **project**: Ongoing matters, goals, initiatives, deadlines. These change relatively quickly so keep them up to date.
- **reference**: Pointers to where information can be found in external systems (bank contacts, lawyer, accountant, etc.).
"""

WHEN_TO_SAVE = """## When to Save

Save a memory when:
- A family member explicitly asks you to remember something
- You learn a non-obvious preference (e.g., "I prefer reports on Monday morning")
- A family member confirms or corrects your approach
- A significant family event is mentioned (e.g., "Our daughter got into Harvard")
"""

WHAT_NOT_TO_SAVE = """## What NOT to Save

- One-time requests ("What's the weather?")
- Information already in the family profile
- Raw conversation transcripts — save the distilled insight, not the chat
- Temporary state, in-progress work, current conversation context
"""

WHEN_TO_ACCESS = """## When to Access Memories

- Before answering a question about the family, check relevant memories
- When the conversation references prior events or preferences
- If a memory conflicts with current information, trust what you observe now and update the stale memory
- Verify memories are still current before acting on them — a memory from 6 months ago may be outdated
"""

TRUSTING_RECALL = """## Trust but Verify

A memory that names a specific file, person, or fact is a claim that it existed when the memory was written.
It may have changed. Before recommending or acting on it, verify it against the current profile or available tools.

"The memory says X exists" is not the same as "X exists now."
"""
