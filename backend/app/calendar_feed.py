"""EUR and USD calendar.

Dates are a working schedule so the dashboard can show the next release
and the high-impact warning. They are not a live ForexFactory scrape.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SAST = ZoneInfo("Africa/Johannesburg")


def _at(day: datetime, hour: int, minute: int) -> datetime:
    local = day.astimezone(SAST).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return local.astimezone(timezone.utc)


def _next_weekday(now: datetime, weekday: int, hour: int, minute: int) -> datetime:
    local = now.astimezone(SAST)
    days = (weekday - local.weekday()) % 7
    candidate = _at(local + timedelta(days=days), hour, minute)
    if candidate <= now:
        candidate = _at(local + timedelta(days=days + 7), hour, minute)
    return candidate


def _first_friday(now: datetime, hour: int, minute: int) -> datetime:
    local = now.astimezone(SAST).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while local.weekday() != 4:
        local += timedelta(days=1)
    candidate = _at(local, hour, minute)
    if candidate <= now:
        month = local.month + 1
        year = local.year
        if month == 13:
            month = 1
            year += 1
        cursor = local.replace(year=year, month=month, day=1)
        while cursor.weekday() != 4:
            cursor += timedelta(days=1)
        candidate = _at(cursor, hour, minute)
    return candidate


def upcoming_events(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(SAST)
    events = [
        {
            "time": _next_weekday(now, local.weekday(), 15, 30)
            if _at(local, 15, 30) > now
            else _at(local + timedelta(days=1), 15, 30),
            "event": "US Retail Sales",
            "currency": "USD",
            "forecast": "0.3%",
            "previous": "0.1%",
            "impact": "High",
        },
        {
            "time": _next_weekday(now, 2, 11, 0),  # Wednesday
            "event": "Eurozone PMI",
            "currency": "EUR",
            "forecast": "49.8",
            "previous": "49.6",
            "impact": "Medium",
        },
        {
            "time": _next_weekday(now, 3, 14, 15),  # Thursday
            "event": "ECB Rate Decision",
            "currency": "EUR",
            "forecast": "3.15%",
            "previous": "3.15%",
            "impact": "High",
        },
        {
            "time": _first_friday(now, 15, 30),
            "event": "US Non-Farm Payrolls",
            "currency": "USD",
            "forecast": "160K",
            "previous": "142K",
            "impact": "High",
        },
        {
            "time": _next_weekday(now, 1, 16, 0),
            "event": "Fed Rate Decision",
            "currency": "USD",
            "forecast": "4.00%",
            "previous": "4.25%",
            "impact": "High",
        },
        {
            "time": _next_weekday(now, 4, 11, 0),
            "event": "German CPI",
            "currency": "EUR",
            "forecast": "0.2%",
            "previous": "0.3%",
            "impact": "High",
        },
        {
            "time": _next_weekday(now, 0, 9, 0),
            "event": "ECB President Speech",
            "currency": "EUR",
            "forecast": "—",
            "previous": "—",
            "impact": "Low",
        },
    ]
    # The Fed decision above can land on the same week as something else.
    # Keep the soonest future copy of each name.
    events = [event for event in events if event["time"] > now - timedelta(minutes=1)]
    events.sort(key=lambda event: event["time"])
    unique = []
    seen = set()
    for event in events:
        if event["event"] in seen:
            continue
        seen.add(event["event"])
        unique.append(event)
    return unique


def filter_events(events: list[dict], currency: str) -> list[dict]:
    if currency == "EUR":
        return [event for event in events if event["currency"] == "EUR"]
    if currency == "USD":
        return [event for event in events if event["currency"] == "USD"]
    return list(events)
