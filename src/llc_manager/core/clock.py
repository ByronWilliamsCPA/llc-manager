"""Injectable clock for date-only business rules.

Route handlers that need "today" take it from :func:`get_today` as a FastAPI
dependency, so tests override it instead of patching the wall clock.
"""

from datetime import UTC, date, datetime


def get_today() -> date:
    """Return today's date in UTC.

    Date-only columns (due dates, filing dates) carry no time zone, so every
    comparison uses the UTC calendar date. This keeps the result identical on
    every host regardless of its local time zone.

    Returns:
        date: The current UTC calendar date.
    """
    return datetime.now(UTC).date()
