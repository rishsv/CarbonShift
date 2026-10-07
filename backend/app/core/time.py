"""Time utilities — IST/UTC handling for CarbonShift AI.

Rules:
- Store everything in UTC internally (DB, Parquet)
- API emits ISO-8601 with offset (+05:30 for IST)
- UI displays IST with literal "IST" label
- India does NOT observe DST (UTC+5:30 always)
- Slot boundaries are always on whole-hour (or 30-min) marks in IST
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytz

IST = pytz.timezone("Asia/Kolkata")
UTC = timezone.utc
IST_OFFSET = timedelta(hours=5, minutes=30)


def now_utc() -> datetime:
    """Current time in UTC (timezone-aware)."""
    return datetime.now(UTC)


def now_ist() -> datetime:
    """Current time in IST (timezone-aware)."""
    return datetime.now(IST)


def to_utc(dt: datetime) -> datetime:
    """Convert any tz-aware datetime to UTC. Naive datetimes are assumed IST."""
    if dt.tzinfo is None:
        dt = IST.localize(dt)
    return dt.astimezone(UTC)


def to_ist(dt: datetime) -> datetime:
    """Convert any tz-aware datetime to IST. Naive datetimes are assumed UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST)


def floor_hour_utc(dt: datetime) -> datetime:
    """Floor a datetime to the nearest whole hour in UTC."""
    dt_utc = to_utc(dt)
    return dt_utc.replace(minute=0, second=0, microsecond=0)


def floor_slot_utc(dt: datetime, slot_minutes: int = 60) -> datetime:
    """Floor a datetime to the nearest slot boundary in UTC."""
    dt_utc = to_utc(dt)
    total_minutes = dt_utc.hour * 60 + dt_utc.minute
    floored_minutes = (total_minutes // slot_minutes) * slot_minutes
    return dt_utc.replace(
        hour=floored_minutes // 60,
        minute=floored_minutes % 60,
        second=0,
        microsecond=0,
    )


def slot_index(ts: datetime, horizon_start: datetime, slot_minutes: int = 60) -> int:
    """Return the 0-based slot index of ts relative to horizon_start."""
    ts_utc = to_utc(ts)
    start_utc = to_utc(horizon_start)
    delta_minutes = (ts_utc - start_utc).total_seconds() / 60
    return int(delta_minutes // slot_minutes)


def slot_to_ts(index: int, horizon_start: datetime, slot_minutes: int = 60) -> datetime:
    """Convert a slot index back to a UTC datetime."""
    start_utc = to_utc(horizon_start)
    return start_utc + timedelta(minutes=index * slot_minutes)


def ist_day_start(dt: datetime) -> datetime:
    """Return 00:00 IST on the same calendar day as dt (in UTC)."""
    dt_ist = to_ist(dt)
    day_start_ist = dt_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    return to_utc(day_start_ist)


def ist_day_end(dt: datetime) -> datetime:
    """Return 23:59:59 IST on the same calendar day as dt (in UTC)."""
    dt_ist = to_ist(dt)
    day_end_ist = dt_ist.replace(hour=23, minute=59, second=59, microsecond=0)
    return to_utc(day_end_ist)


def ist_date_str(dt: datetime) -> str:
    """Return an IST date string like '2026-10-07 IST'."""
    return to_ist(dt).strftime("%Y-%m-%d IST")


def ist_datetime_str(dt: datetime) -> str:
    """Return an IST datetime string like '2026-10-07 14:30 IST'."""
    return to_ist(dt).strftime("%Y-%m-%d %H:%M IST")


def slots_in_day(slot_minutes: int = 60) -> int:
    """Number of slots in 24 hours."""
    return 24 * 60 // slot_minutes


def duration_to_slots(duration_h: float, slot_minutes: int = 60) -> int:
    """Convert a duration in hours to an integer number of slots (ceiling)."""
    return math.ceil(duration_h * 60 / slot_minutes)


def slots_to_hours(slots: int, slot_minutes: int = 60) -> float:
    """Convert slot count to hours."""
    return slots * slot_minutes / 60


def generate_hourly_range(start: datetime, end: datetime) -> list[datetime]:
    """Generate a list of UTC datetimes, one per hour, from start (inclusive) to end (exclusive)."""
    start_utc = floor_hour_utc(start)
    end_utc = to_utc(end)
    result = []
    current = start_utc
    while current < end_utc:
        result.append(current)
        current += timedelta(hours=1)
    return result


def ist_hour(dt: datetime) -> int:
    """Return the IST hour (0-23) of a datetime."""
    return to_ist(dt).hour


def ist_month(dt: datetime) -> int:
    """Return the IST month (1-12) of a datetime."""
    return to_ist(dt).month


def ist_weekday(dt: datetime) -> int:
    """Return the IST weekday (0=Monday, 6=Sunday) of a datetime."""
    return to_ist(dt).weekday()


def is_weekend_ist(dt: datetime) -> bool:
    """Return True if the IST date is Saturday or Sunday."""
    return ist_weekday(dt) >= 5


# ── IST daily budget day boundary ────────────────────────────────────────────

def ist_day_index(ts: datetime, horizon_start: datetime) -> int:
    """Return the 0-based IST calendar day index of ts relative to horizon_start."""
    ts_ist = to_ist(ts)
    start_ist = to_ist(horizon_start)
    start_day = start_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    ts_day = ts_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    return (ts_day - start_day).days
