"""
Anomaly detection for agent behavior.

Rule-based detection of suspicious patterns:
  1. High-frequency tool usage (potential data exfiltration)
  2. First-query bulk access (new session asking for "all" data)
  3. Cross-family-member data probing

Detections trigger audit events and escalate_to_human recommendations.
"""

from __future__ import annotations

import time as _time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnomalySignal:
    """A detected anomaly."""
    rule: str           # Rule identifier
    severity: str       # "low", "medium", "high", "critical"
    tenant_id: str
    details: str
    recommended_action: str = "audit_log"
    timestamp: float = field(default_factory=_time.time)


# ── Rule 1: High-frequency tool usage ──

class ToolFrequencyTracker:
    """
    Tracks tool invocation frequency per tenant.
    Flags when a tenant makes too many calls to sensitive tools.
    """

    def __init__(self, window_seconds: float = 60.0, threshold: int = 20):
        self._window = window_seconds
        self._threshold = threshold
        # {tenant_id: [(timestamp, tool_name), ...]}
        self._history: dict[str, list[tuple[float, str]]] = defaultdict(list)

    def record(self, tenant_id: str, tool_name: str) -> AnomalySignal | None:
        """Record a tool call. Returns an AnomalySignal if threshold exceeded."""
        now = _time.time()
        cutoff = now - self._window

        # Slide window
        self._history[tenant_id] = [
            (ts, tn) for ts, tn in self._history[tenant_id]
            if ts > cutoff
        ]
        self._history[tenant_id].append((now, tool_name))

        count = len(self._history[tenant_id])
        if count > self._threshold:
            # Count by tool type
            tool_counts: dict[str, int] = defaultdict(int)
            for _, tn in self._history[tenant_id]:
                tool_counts[tn] += 1

            top_tool = max(tool_counts, key=tool_counts.get)
            return AnomalySignal(
                rule="high_frequency_tool_use",
                severity="high",
                tenant_id=tenant_id,
                details=(
                    f"Tenant {tenant_id} made {count} tool calls in {self._window}s "
                    f"(limit: {self._threshold}). Top tool: {top_tool} ({tool_counts[top_tool]}x)"
                ),
                recommended_action="escalate_to_human",
            )

        return None


# ── Rule 2: First-query bulk access ──

class FirstQueryBulkDetector:
    """
    Detects when a new session's first query requests all data.
    Pattern: first message contains "全部" or "所有" + targets query_assets.
    """

    _BULK_KEYWORDS = ["全部", "所有", "all", "全量", "整个", "全部资产", "所有账户"]

    def __init__(self):
        # {tenant_id: first_query_text}
        self._first_queries: dict[str, str] = {}

    def check_first_query(self, tenant_id: str, message: str, tool_name: str) -> AnomalySignal | None:
        """Check if this is a first query requesting bulk data."""
        if tenant_id in self._first_queries:
            return None  # Not first query

        self._first_queries[tenant_id] = message

        msg_lower = message.lower()
        has_bulk = any(kw in msg_lower for kw in self._BULK_KEYWORDS)
        is_sensitive_tool = tool_name in ("query_assets", "search_docs")

        if has_bulk and is_sensitive_tool:
            return AnomalySignal(
                rule="first_query_bulk_access",
                severity="medium",
                tenant_id=tenant_id,
                details=f"First query from tenant {tenant_id} requests bulk data via {tool_name}: {message[:100]}",
                recommended_action="audit_log",
            )

        return None


# ── Rule 3: Cross-family-member probing ──

class CrossMemberDetector:
    """
    Detects when queries reference family members not in the current context.
    For MVP, checks if the query mentions names not matching the requesting user.
    """

    # Names that might appear in queries (family-specific)
    _FAMILY_NAME_PATTERNS = [
        "洪伟", "洪先生", "洪太太", "张丽", "洪明", "洪悦",
        "太太", "先生", "儿子", "女儿", "孩子",
    ]

    def __init__(self):
        # {tenant_id: user_role}
        self._user_roles: dict[str, str] = {}

    def set_user_context(self, tenant_id: str, role: str) -> None:
        """Set the current user's role for context."""
        self._user_roles[tenant_id] = role

    def check(self, tenant_id: str, message: str, user_id: str = "") -> AnomalySignal | None:
        """
        Check if a non-principal user is querying data about other family members.
        """
        role = self._user_roles.get(tenant_id, "principal")
        if role in ("principal", "admin", "spouse"):
            return None

        # For child role: flag queries about parents
        if role == "child":
            parent_keywords = ["洪伟", "洪先生", "洪太太", "张丽", "父亲", "母亲", "爸爸", "妈妈"]
            found = [kw for kw in parent_keywords if kw in message]
            if found:
                return AnomalySignal(
                    rule="child_querying_parent_data",
                    severity="medium",
                    tenant_id=tenant_id,
                    details=f"Child role querying parent info: keywords={found}",
                    recommended_action="audit_log",
                )

        return None


# ── Unified Detector ──

class AnomalyDetector:
    """Unified anomaly detection for the agent pipeline."""

    def __init__(self):
        self.frequency = ToolFrequencyTracker()
        self.first_query = FirstQueryBulkDetector()
        self.cross_member = CrossMemberDetector()

    def record_tool_call(
        self,
        tenant_id: str,
        tool_name: str,
        user_message: str = "",
        user_id: str = "",
    ) -> list[AnomalySignal]:
        """
        Record a tool call and return any anomaly signals detected.
        Callers should audit log these and potentially escalate.
        """
        signals: list[AnomalySignal] = []

        # Rule 1: frequency
        sig = self.frequency.record(tenant_id, tool_name)
        if sig:
            signals.append(sig)

        # Rule 2: first query bulk
        sig = self.first_query.check_first_query(tenant_id, user_message, tool_name)
        if sig:
            signals.append(sig)

        # Rule 3: cross-member
        sig = self.cross_member.check(tenant_id, user_message, user_id)
        if sig:
            signals.append(sig)

        return signals

    def set_user_role(self, tenant_id: str, role: str) -> None:
        self.cross_member.set_user_context(tenant_id, role)


# Global singleton
_detector: AnomalyDetector | None = None


def get_anomaly_detector() -> AnomalyDetector:
    global _detector
    if _detector is None:
        _detector = AnomalyDetector()
    return _detector
