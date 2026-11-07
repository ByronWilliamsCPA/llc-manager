"""Compute the read-only compliance summary served on entity responses.

The summary is derived from records the entity already carries (state
registrations, tax filings, registered agents). Nothing is stored and nothing
is invented: when no outstanding obligation has a date, the summary says
``unknown`` with a null date.

Rules, in one place:

* "Today" is a UTC calendar date passed in by the caller (see
  :func:`llc_manager.core.clock.get_today`); dates are date-only, so there is
  no time-of-day or time-zone arithmetic.
* Soft-deleted records are ignored. An inactive entity has no applicable
  obligations.
* Registrations in a terminal status (expired, withdrawn, revoked) are
  ignored. For the others, ``annual_report_due`` counts unless the last
  filed annual report is dated no earlier than ``EARLY_FILING_DAYS`` before
  it (so a report filed early, or late, satisfies that cycle);
  ``next_renewal_date`` and ``expiration_date`` always count.
* A tax filing counts while it has no ``filed_date`` and its status is not
  ``filed`` or ``not_required``. Its date is ``due_date`` while that date is
  not yet past (due today is not past); once ``due_date`` is past, the
  ``extended_due_date`` replaces it when one exists. A filing with status
  ``extended`` uses its ``extended_due_date`` immediately, even before the
  original date. A filing with only an extended date uses that date.
* ``next_due_date`` is the earliest outstanding date, which is in the past
  when something is overdue. The status is the worst across obligations; as
  the worst status always belongs to the earliest date, it is derived from
  that date.
* The registered agent is the active, non-deleted agent, preferring the one
  in the entity's formation state (compared ignoring case and padding), then
  the lowest state code, then name.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from llc_manager.models.state_registration import RegistrationStatus
from llc_manager.models.tax_filing import FilingStatus
from llc_manager.schemas.compliance import ComplianceStatus, EntityCompliance

if TYPE_CHECKING:
    from collections.abc import Iterator

    from llc_manager.models.entity import Entity
    from llc_manager.models.state_registration import StateRegistration
    from llc_manager.models.tax_filing import TaxFiling

# #ASSUME: Product - 60 days is the "due soon" window and the status
# vocabulary (current, due_soon, overdue, unknown) is the one the read-only
# consumer expects. Neither has been confirmed with the product owner.
# #VERIFY: confirm the window and vocabulary before this leaves draft; the
# window changes only this constant.
DUE_SOON_DAYS = 60

# #ASSUME: Data integrity - the models do not link a filed annual report to
# the due date it satisfies. A report dated within this many days before
# ``annual_report_due`` (or after it) is treated as satisfying that due date.
# The window is deliberately short: a late filing for the previous cycle would
# have to be more than nine months late to hide the current one, so a genuinely
# overdue report is not masked, at the cost of not recognising filings made
# earlier than this.
# #VERIFY: confirm with the data owners how far ahead of the due date reports
# are filed and whether annual_report_due is rolled forward after filing.
EARLY_FILING_DAYS = 90

_TERMINAL_REGISTRATION_STATUSES = frozenset(
    {
        RegistrationStatus.EXPIRED,
        RegistrationStatus.WITHDRAWN,
        RegistrationStatus.REVOKED,
    }
)
_CLOSED_FILING_STATUSES = frozenset({FilingStatus.FILED, FilingStatus.NOT_REQUIRED})


def _registration_dates(registration: StateRegistration) -> Iterator[date]:
    """Yield the outstanding dates of one registration.

    Args:
        registration (StateRegistration): A non-deleted registration.

    Yields:
        date: Each date that still needs action.
    """
    if registration.status in _TERMINAL_REGISTRATION_STATUSES:
        return
    due = registration.annual_report_due
    last_filed = registration.last_annual_report
    if due is not None and (
        last_filed is None or last_filed < due - timedelta(days=EARLY_FILING_DAYS)
    ):
        yield due
    if registration.next_renewal_date is not None:
        yield registration.next_renewal_date
    if registration.expiration_date is not None:
        yield registration.expiration_date


def _filing_date(filing: TaxFiling, today: date) -> date | None:
    """Return the date an open tax filing is currently due, if any.

    Args:
        filing (TaxFiling): A non-deleted tax filing.
        today (date): The injected UTC date.

    Returns:
        date | None: The effective due date, or None when the filing is closed
        or carries no date.
    """
    if filing.filed_date is not None or filing.status in _CLOSED_FILING_STATUSES:
        return None
    due, extended = filing.due_date, filing.extended_due_date
    if due is None or (filing.status == FilingStatus.EXTENDED and extended is not None):
        return extended
    if due < today and extended is not None:
        return extended
    return due


def _outstanding_dates(entity: Entity, today: date) -> Iterator[date]:
    """Yield every outstanding compliance date of an entity.

    Args:
        entity (Entity): Entity with its collections already loaded.
        today (date): The injected UTC date.

    Yields:
        date: Each outstanding date.
    """
    if not entity.is_active:
        return
    for registration in entity.state_registrations:
        if registration.deleted_at is None:
            yield from _registration_dates(registration)
    for filing in entity.tax_filings:
        if filing.deleted_at is None:
            filing_date = _filing_date(filing, today)
            if filing_date is not None:
                yield filing_date


def _status_for(due: date | None, today: date) -> ComplianceStatus:
    """Classify the earliest outstanding date.

    Args:
        due (date | None): Earliest outstanding date, or None.
        today (date): The injected UTC date.

    Returns:
        ComplianceStatus: ``overdue`` before today, ``due_soon`` from today
        through ``DUE_SOON_DAYS`` days ahead, ``current`` beyond that, and
        ``unknown`` when there is no date.
    """
    if due is None:
        return ComplianceStatus.UNKNOWN
    if due < today:
        return ComplianceStatus.OVERDUE
    if due <= today + timedelta(days=DUE_SOON_DAYS):
        return ComplianceStatus.DUE_SOON
    return ComplianceStatus.CURRENT


def _same_state(state: str, formation_state: str | None) -> bool:
    """Compare two state codes ignoring case and surrounding whitespace.

    Args:
        state (str): An agent's state code.
        formation_state (str | None): The entity's formation state, if any.

    Returns:
        bool: True when both are non-empty and equal once normalised.
    """
    wanted = (formation_state or "").strip().upper()
    return bool(wanted) and state.strip().upper() == wanted


def _agent_display_name(entity: Entity) -> str | None:
    """Return the display name of the entity's current registered agent.

    Args:
        entity (Entity): Entity with its collections already loaded.

    Returns:
        str | None: Service company name when recorded, else the agent name;
        None when no agent is active.
    """
    candidates = (
        agent
        for agent in entity.registered_agents
        if agent.is_active and agent.deleted_at is None
    )
    chosen = min(
        candidates,
        key=lambda agent: (
            not _same_state(agent.state, entity.formation_state),
            agent.state,
            agent.agent_name,
        ),
        default=None,
    )
    if chosen is None:
        return None
    company = (chosen.agent_company or "").strip()
    return company or chosen.agent_name


def summarize_compliance(entity: Entity, today: date) -> EntityCompliance:
    """Build the compliance summary for one entity.

    Reads only collections that are already loaded on the entity (the entity
    relationships use ``selectin`` loading), so it issues no queries.

    Args:
        entity (Entity): Entity with registrations, filings and agents loaded.
        today (date): The UTC calendar date to judge against.

    Returns:
        EntityCompliance: Next due date, status, and registered agent name.
    """
    next_due = min(_outstanding_dates(entity, today), default=None)
    return EntityCompliance(
        next_due_date=next_due,
        status=_status_for(next_due, today),
        registered_agent_name=_agent_display_name(entity),
    )
