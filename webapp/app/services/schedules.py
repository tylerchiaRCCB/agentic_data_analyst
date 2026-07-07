from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

from app.models import Schedule, utcnow


class CronValidationError(ValueError):
    pass


def validate_cron(cron_expr: str, tz_name: str) -> None:
    if not croniter.is_valid(cron_expr):
        raise CronValidationError(f"Invalid cron expression: {cron_expr!r}")
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise CronValidationError(f"Unknown timezone: {tz_name!r}")


def next_fire_utc(cron_expr: str, tz_name: str, after: datetime | None = None) -> datetime:
    """Next fire time computed in the schedule's timezone, returned as UTC."""
    tz = ZoneInfo(tz_name)
    base = (after or utcnow()).astimezone(tz)
    nxt = croniter(cron_expr, base).get_next(datetime)
    return nxt.astimezone(timezone.utc)


def preview_fire_times(cron_expr: str, tz_name: str, count: int = 5) -> list[datetime]:
    """Next N fire times in the schedule's local timezone (for display)."""
    tz = ZoneInfo(tz_name)
    it = croniter(cron_expr, utcnow().astimezone(tz))
    return [it.get_next(datetime) for _ in range(count)]


def reschedule(schedule: Schedule, fired_at: datetime | None = None) -> None:
    schedule.last_run_at = fired_at or utcnow()
    schedule.next_run_at = next_fire_utc(schedule.cron_expr, schedule.timezone)
