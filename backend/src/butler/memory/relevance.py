"""
Find relevant memories for a given query.
MVP: keyword match against memory descriptions + content.
Post-MVP: embedding-based semantic search (pgvector).
"""

from __future__ import annotations

import re

from butler.memory.memory_manager import MemoryEntry, MemoryManager


def _tokenize(text: str) -> set[str]:
    """Simple CJK + English tokenizer for keyword matching."""
    # Extract meaningful tokens: CJK bigrams + English words
    tokens: set[str] = set()
    # English words
    tokens.update(re.findall(r"[a-zA-Z]{2,}", text.lower()))
    # CJK character bigrams
    cjk = re.findall(r"[一-鿿]", text)
    for i in range(len(cjk) - 1):
        tokens.add(cjk[i] + cjk[i + 1])
    # CJK unigrams
    tokens.update(cjk)
    return tokens


async def find_relevant_memories(
    manager: MemoryManager,
    query: str,
    top_k: int = 5,
) -> list[tuple[MemoryEntry, float]]:
    """
    Find memories relevant to the current query.

    MVP: keyword intersection scoring.
    Each matching token between query and memory content adds 1 point.
    Matching the description or name adds bonus points.

    Returns list of (entry, score) sorted by score descending.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    scored: list[tuple[MemoryEntry, float]] = []
    for file_name in await manager.list_files():
        content = await manager.read(file_name)
        if not content:
            continue

        entry = MemoryManager._parse_frontmatter(content, file_name)
        if not entry:
            continue

        content_tokens = _tokenize(entry.content)
        desc_tokens = _tokenize(entry.description)
        name_tokens = _tokenize(entry.name)

        # Score: content matches (1pt) + description matches (2pt) + name matches (3pt)
        score = 0.0
        score += len(query_tokens & content_tokens) * 1.0
        score += len(query_tokens & desc_tokens) * 2.0
        score += len(query_tokens & name_tokens) * 3.0

        # Normalize by content length (favor concise, relevant memories)
        content_len = max(len(entry.content), 1)
        score = score / (1 + content_len / 500)

        if score > 0:
            scored.append((entry, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
