"""
Prompt injection and content safety guard.

Provides lightweight, regex-based scanning for prompt injection attempts
at system boundaries: WeChat messages, PDF text extraction, memory writes.

Design: fast, no ML dependency, low false-positive rate. Returns a score
(0-100) rather than binary yes/no so callers can decide thresholds.
"""

from __future__ import annotations

import re as _re
from dataclasses import dataclass, field

# ── Injection patterns ──
# Each pattern has a regex and a severity weight (1-10)

_INJECTION_PATTERNS: list[tuple[_re.Pattern, int, str]] = [
    # Direct instruction override (weight: 15 — a single match = suspicious)
    (_re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|rules?|constraints?)", _re.IGNORECASE), 15, "ignore_previous_instructions"),
    (_re.compile(r"(forget|disregard|override)\s+(your|all)\s+(instructions?|rules?|programming)", _re.IGNORECASE), 15, "forget_instructions"),
    (_re.compile(r"you\s+are\s+now\s+(a\s+)?(different|new|another)", _re.IGNORECASE), 14, "you_are_now"),
    (_re.compile(r"(from\s+now\s+on|starting\s+now)\s*,?\s*(you\s+(are|will|should))", _re.IGNORECASE), 14, "from_now_on"),

    # Role/identity manipulation (weight: 8)
    (_re.compile(r"(you\s+are|act\s+as|pretend\s+to\s+be)\s+(a\s+)?(hacker|attacker|evil|malicious|unrestricted|unlimited|god)", _re.IGNORECASE), 8, "malicious_role"),
    (_re.compile(r"<system[>\s]", _re.IGNORECASE), 8, "system_tag_injection"),
    (_re.compile(r"<system_guard[>\s]", _re.IGNORECASE), 8, "system_guard_injection"),
    (_re.compile(r"</system_guard>", _re.IGNORECASE), 7, "close_guard_tag"),
    (_re.compile(r"</?system>", _re.IGNORECASE), 7, "system_tag"),

    # Prompt leaking (weight: 7)
    (_re.compile(r"(reveal|show|print|output|display|repeat)\s+(your\s+)?(system\s+)?(prompt|instructions?|rules?)", _re.IGNORECASE), 7, "reveal_prompt"),
    (_re.compile(r"(what\s+are\s+your|tell\s+me\s+your)\s+(instructions?|rules?|prompt)", _re.IGNORECASE), 7, "ask_instructions"),

    # Delimiter/DAN/jailbreak (weight: 6)
    (_re.compile(r"\bDAN\b.*\b(do\s+anything\s+now|jailbreak)\b", _re.IGNORECASE), 6, "dan_jailbreak"),
    (_re.compile(r"(ignore|bypass|disable)\s+(all\s+)?(safety|security|ethical|content)\s+(filters?|restrictions?|guidelines?)", _re.IGNORECASE), 6, "bypass_safety"),

    # Cross-tenant data access attempt (weight: 15)
    (_re.compile(r"(other|another|different)\s+(famil|tenant|customer|client|household)", _re.IGNORECASE), 15, "cross_tenant"),
    (_re.compile(r"(list|show|get|query|read)\s+(all|every)\s+(other|another)\s+(famil|tenant|customer)", _re.IGNORECASE), 15, "list_all_tenants"),

    # Embedded instruction in data (weight: 5)
    (_re.compile(r"<\|.*\|>", _re.IGNORECASE), 5, "special_delimiter"),
    (_re.compile(r"\[system\]\([^)]+\)", _re.IGNORECASE), 4, "markdown_system_link"),
]

# Normalization: collapse repeated whitespace for matching
_NORMALIZE_RE = _re.compile(r"\s+")


@dataclass
class GuardResult:
    """Result of a content safety scan."""
    score: int = 0              # 0-100 (0 = clean, 100 = definite attack)
    is_suspicious: bool = False  # score >= threshold
    matches: list[dict] = field(default_factory=list)  # [{pattern, weight, match_snippet}]
    threshold: int = 30          # Default suspicion threshold

    @property
    def is_blocked(self) -> bool:
        return self.score >= 70  # Hard block threshold


def scan_content(content: str, threshold: int = 30) -> GuardResult:
    """
    Scan content for prompt injection patterns.

    Returns a GuardResult with score (0-100) and match details.
    Score is capped at 100. Each matching pattern adds its weight.
    """
    if not content or not content.strip():
        return GuardResult(score=0, threshold=threshold)

    normalized = _NORMALIZE_RE.sub(" ", content)
    total_score = 0
    matches: list[dict] = []

    for pattern, weight, name in _INJECTION_PATTERNS:
        found = pattern.findall(normalized)
        if found:
            total_score += weight
            # Get a snippet for the first match
            snippet = ""
            m = pattern.search(normalized)
            if m:
                start = max(0, m.start() - 20)
                end = min(len(normalized), m.end() + 20)
                snippet = normalized[start:end]
            matches.append({
                "pattern": name,
                "weight": weight,
                "snippet": snippet,
            })

    total_score = min(total_score, 100)

    return GuardResult(
        score=total_score,
        is_suspicious=total_score >= threshold,
        matches=matches,
        threshold=threshold,
    )


def is_injection_attempt(content: str) -> bool:
    """Quick check: is this content likely a prompt injection attempt?"""
    return scan_content(content, threshold=20).is_suspicious


def is_blocked_content(content: str) -> bool:
    """Hard block check: should this content be rejected entirely?"""
    return scan_content(content, threshold=70).is_blocked


def scan_with_context(user_content: str, previous_content: str = "") -> GuardResult:
    """
    Scan user content considering previous conversation context.
    Higher threshold when combined with suspicious prior messages.
    """
    result = scan_content(user_content)

    # If previous turn was also suspicious, lower the threshold
    if previous_content:
        prev_result = scan_content(previous_content)
        if prev_result.is_suspicious:
            result.threshold = max(15, result.threshold - 10)
            result.is_suspicious = result.score >= result.threshold

    return result
