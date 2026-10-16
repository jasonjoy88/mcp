"""Assignee type resolution.

Mirrors ``resolveAssigneeType`` in the Go version's ``internal/app/assignee.go``.
"""

from __future__ import annotations

import logging

from ..domain import VALID_ASSIGNEE_TYPES, AssigneeType

logger = logging.getLogger(__name__)


async def resolve_assignee_type(
    client,
    assignee_id: str,
    explicit: str | None = None,
) -> str | None:
    """Resolve the assignee type for a given assignee ID.

    * If *explicit* is provided and non-empty, validate and return it.
    * Otherwise, try to find the ID in the workspace agents list.
    * Fall back to ``member`` if not found or the agent list can't be loaded.

    Returns ``None`` when *assignee_id* is empty (no assignee).
    """
    if explicit:
        if explicit not in VALID_ASSIGNEE_TYPES:
            raise ValueError(
                f"invalid assignee_type {explicit!r}; valid values: member, agent, squad"
            )
        return explicit

    if not assignee_id:
        return None

    try:
        agents = await client.list_agents()
    except Exception as exc:
        logger.debug("failed to list agents for assignee inference, defaulting to member",
                     exc_info=exc)
        return AssigneeType.MEMBER.value

    for agent in agents:
        if agent.id == assignee_id:
            return AssigneeType.AGENT.value

    return AssigneeType.MEMBER.value
