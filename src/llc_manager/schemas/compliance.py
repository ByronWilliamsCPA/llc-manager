"""Compliance summary schema embedded in entity responses."""

from datetime import date
from enum import StrEnum

from pydantic import Field

from llc_manager.schemas.base import BaseSchema


class ComplianceStatus(StrEnum):
    """Overall compliance standing derived from outstanding due dates.

    Attributes:
        CURRENT: Every outstanding obligation is more than the due-soon window away.
        DUE_SOON: The earliest outstanding obligation is due today or within the window.
        OVERDUE: At least one outstanding obligation is past its due date.
        UNKNOWN: No outstanding obligation with a date exists, so nothing is claimed.
    """

    CURRENT = "current"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    UNKNOWN = "unknown"


class EntityCompliance(BaseSchema):
    """Read-only compliance summary computed from an entity's records.

    Never fabricated: an entity with no outstanding dated obligation returns a
    null date and the ``unknown`` status.
    """

    next_due_date: date | None = Field(
        default=None,
        description=(
            "Earliest outstanding compliance date (UTC calendar date) across "
            "state registrations and tax filings. It is in the past when an "
            "obligation is overdue. Null when no outstanding obligation has a date."
        ),
        examples=["2026-04-01"],
    )
    status: ComplianceStatus = Field(
        default=ComplianceStatus.UNKNOWN,
        description=(
            "Worst status across outstanding obligations: `overdue` beats "
            "`due_soon` (due today or within 60 days) beats `current`. "
            "`unknown` when there is nothing outstanding to judge."
        ),
        examples=["due_soon"],
    )
    registered_agent_name: str | None = Field(
        default=None,
        description=(
            "Display name of the current registered agent (service company "
            "when recorded, otherwise the agent name). Null when none is active."
        ),
        examples=["Example Registered Agents Inc"],
    )


def unknown_compliance() -> EntityCompliance:
    """Return the summary used when none has been computed.

    Returns:
        EntityCompliance: Null date, ``unknown`` status, no agent.
    """
    return EntityCompliance()
