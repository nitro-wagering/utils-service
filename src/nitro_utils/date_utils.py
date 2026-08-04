from datetime import date, datetime
from zoneinfo import ZoneInfo

BRISBANE_TZ = ZoneInfo("Australia/Brisbane")


def brisbane_today() -> date:
    """Current date in Brisbane timezone (UTC+10 AEST)."""
    return datetime.now(BRISBANE_TZ).date()


def utc_today() -> date:
    """Current date in UTC timezone."""
    from datetime import UTC
    return datetime.now(UTC).date()
