"""
Agent type authorization. Maps user roles to allowed agent types.

Roles:
  - principal: family head, full access
  - spouse:     family co-head, most access
  - child:      family member, limited access
  - admin:      system reviewer/admin, full access
  - guest:      read-only (future)
"""

from __future__ import annotations

from typing import FrozenSet

# Agent types each role can use
ROLE_AGENT_ALLOWLIST: dict[str, frozenset[str]] = {
    "principal": frozenset({
        "butler",
        "wealth_advisor",
        "tax_strategist",
        "document_secretary",
        "schedule_manager",
        "education_advisor",
        "health_advisor",
    }),
    "spouse": frozenset({
        "butler",
        "document_secretary",
        "schedule_manager",
        "education_advisor",
        "health_advisor",
    }),
    "child": frozenset({
        "butler",
        "schedule_manager",
        "education_advisor",
    }),
    "admin": frozenset({
        "butler",
        "wealth_advisor",
        "tax_strategist",
        "document_secretary",
        "schedule_manager",
        "education_advisor",
        "health_advisor",
    }),
}

# Sensitive agents — additional restrictions beyond role
SENSITIVE_AGENTS: FrozenSet[str] = frozenset({
    "wealth_advisor",
    "tax_strategist",
})

# Default role for unauthenticated or unknown
DEFAULT_ROLE = "principal"


def get_allowed_agents(role: str | None) -> frozenset[str]:
    """Return the set of agent types allowed for a given role."""
    if not role:
        role = DEFAULT_ROLE
    return ROLE_AGENT_ALLOWLIST.get(role, ROLE_AGENT_ALLOWLIST[DEFAULT_ROLE])


def can_use_agent(role: str | None, agent_type: str) -> bool:
    """Check if a role can use a specific agent type."""
    allowed = get_allowed_agents(role)
    return agent_type in allowed


def is_sensitive_agent(agent_type: str) -> bool:
    """Check if an agent type requires elevated privileges."""
    return agent_type in SENSITIVE_AGENTS
