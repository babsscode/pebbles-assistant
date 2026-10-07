"""Date/time parsing and formatting (all in the configured timezone)."""
import re
from datetime import date, datetime, time, timedelta

from config import TZ

WEEKDAYS = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}

_weekday_alt = "|".join(sorted(WEEKDAYS, key=len, reverse=True))

# Regex fragments reused by the command parsers
DATE_TOKEN = (
    r"(?:\d{1,2}/\d{1,2}(?:/\d{2,4})?"
    rf"|tomorrow|tmrw|tom|today|{_weekday_alt})(?=\s|$)"
)
TIME_TOKEN = r"(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)|\d{1,2}:\d{2})"


def now() -> datetime:
    return datetime.now(TZ)


def today() -> date:
    return now().date()


# ----------------------------------------------------------------- parsing
def parse_date_input(text: str) -> date:
    """'10/15', '10/15/27', 'today', 'tomorrow', 'fri' -> date."""
    s = text.strip().lower()
    t = today()

    if s == "today":
        return t
    if s in ("tomorrow", "tmrw", "tom"):
        return t + timedelta(days=1)
    if s in WEEKDAYS:
        return t + timedelta(days=(WEEKDAYS[s] - t.weekday()) % 7)

    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", s)
    if not m:
        raise ValueError("Unrecognized date")

    month, day, year = int(m.group(1)), int(m.group(2)), m.group(3)
    if year:
        y = int(year)
        return date(y + 2000 if y < 100 else y, month, day)

    d = date(t.year, month, day)
    if d < t:  # already passed -> next year
        d = date(t.year + 1, month, day)
    return d


def parse_time_input(text: str) -> time:
    """'2:30 pm', '2pm', '14:30' -> time."""
    m = re.fullmatch(
        r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text.strip().lower()
    )
    if not m:
        raise ValueError("Unrecognized time")

    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)

    if not ampm and m.group(2) is None:
        raise ValueError("Add am/pm")
    if minute > 59:
        raise ValueError("Bad minute")

    if ampm:
        if not 1 <= hour <= 12:
            raise ValueError("Bad hour")
        hour = hour % 12 + (12 if ampm == "pm" else 0)
    elif hour > 23:
        raise ValueError("Bad hour")

    return time(hour, minute)


# -------------------------------------------------------------- formatting
def fmt_time(t: time) -> str:
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def fmt_range(start: time, end: time | None) -> str:
    if not end:
        return fmt_time(start)
    if (start.hour < 12) == (end.hour < 12):
        ap = "AM" if start.hour < 12 else "PM"
        return (
            f"{start.hour % 12 or 12}:{start.minute:02d}–"
            f"{end.hour % 12 or 12}:{end.minute:02d} {ap}"
        )
    return f"{fmt_time(start)}–{fmt_time(end)}"


def fmt_date_short(d: date) -> str:
    return f"{d.strftime('%a')}, {d.strftime('%b')} {d.day}"


def relative_label(d: date) -> str | None:
    delta = (d - today()).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if delta == -1:
        return "yesterday"
    if delta < -1:
        return f"{-delta} days ago"
    return None


# ------------------------------------------------------------------ scopes
# t = today, m = tomorrow, w = this week (Mon-Sun), o = overdue
def scope_range(scope: str) -> tuple[date, date]:
    """Returns (start, end_exclusive)."""
    t = today()
    if scope == "m":
        s = t + timedelta(days=1)
        return s, s + timedelta(days=1)
    if scope == "w":
        monday = t - timedelta(days=t.weekday())
        return monday, monday + timedelta(days=7)
    return t, t + timedelta(days=1)


def scope_title(scope: str, start: date) -> str:
    if scope == "w":
        return f"Week of {start.strftime('%b')} {start.day}"
    if scope == "o":
        return "Overdue"
    label = "Tomorrow" if scope == "m" else "Today"
    return f"{label} · {fmt_date_short(start)}"


def parse_scope(args: list[str]) -> str | None:
    if not args:
        return "t"
    a = args[0]
    if a in ("today", "now", "t"):
        return "t"
    if a in ("tomorrow", "tmrw", "tom", "m"):
        return "m"
    if a in ("week", "wk", "w"):
        return "w"
    if a in ("overdue", "late", "o"):
        return "o"
    return None
