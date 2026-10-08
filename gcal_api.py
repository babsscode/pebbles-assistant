"""Everything that talks to Google Calendar (classes + personal calendars)."""
import json
import os
from datetime import date, datetime, time, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import config as C

_calendars_cache: list[dict] | None = None


# -------------------------------------------------------------------- authimport json
import os
import threading

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import config as C

_calendars_cache: list[dict] | None = None
_creds = None
_lock = threading.Lock()


def _credentials():
    global _creds
    with _lock:
        if _creds is None:
            raw = os.environ.get("GOOGLE_TOKEN")
            if not raw:
                raise RuntimeError("GOOGLE_TOKEN is not set.")
            _creds = Credentials.from_authorized_user_info(
                json.loads(raw), C.GOOGLE_SCOPES
            )
        if not _creds.valid:
            if _creds.refresh_token:
                _creds.refresh(Request())
            else:
                raise RuntimeError("GOOGLE_TOKEN has no refresh_token.")
        return _creds


def _service():
    return build("calendar", "v3", credentials=_credentials(), cache_discovery=False)


def _service():
    return build(
        "calendar", "v3", credentials=_credentials(), cache_discovery=False
    )


# --------------------------------------------------------------- calendars
def get_calendars() -> list[dict]:
    """[{'id':..., 'kind': 'classes'|'personal'}], discovered once by name."""
    global _calendars_cache
    if _calendars_cache is not None:
        return _calendars_cache

    items = _service().calendarList().list().execute().get("items", [])
    by_name = {}
    for c in items:
        for key in (c.get("summary"), c.get("summaryOverride")):
            if key:
                by_name[key.strip().lower()] = c["id"]

    classes_id = C.CLASSES_CALENDAR_ID or by_name.get(
        C.CLASSES_CALENDAR_NAME.lower()
    )
    personal_id = C.PERSONAL_CALENDAR_ID
    if not personal_id or personal_id == classes_id:
        personal_id = by_name.get(C.PERSONAL_CALENDAR_NAME.lower())

    cals = []
    if classes_id:
        cals.append({"id": classes_id, "kind": "classes"})
    if personal_id:
        cals.append({"id": personal_id, "kind": "personal"})
    if not cals:
        raise RuntimeError("No calendars found. Check calendar names / IDs.")

    _calendars_cache = cals
    return cals


def _calendar_id(kind: str) -> str:
    for c in get_calendars():
        if c["kind"] == kind:
            return c["id"]
    raise RuntimeError(f"No '{kind}' calendar found.")


# ------------------------------------------------------------------ reading
def _expand(raw: dict, kind: str, start_d: date, end_d: date) -> list[dict]:
    """Turn one raw Google event into 0+ per-day entries inside the range."""
    base = {
        "id": raw.get("id"),
        "name": raw.get("summary", "Untitled event"),
        "location": raw.get("location"),
        "kind": kind,
    }
    start, end = raw.get("start", {}), raw.get("end", {})
    out = []

    if "date" in start:  # all-day (end date is exclusive)
        s = date.fromisoformat(start["date"])
        e = date.fromisoformat(end.get("date", start["date"]))
        d = max(s, start_d)
        while d < min(max(e, s + timedelta(days=1)), end_d):
            out.append({**base, "date": d, "start": None, "end": None, "all_day": True})
            d += timedelta(days=1)
        return out

    if "dateTime" in start:
        sdt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00")).astimezone(C.TZ)
        edt = None
        if "dateTime" in end:
            edt = datetime.fromisoformat(end["dateTime"].replace("Z", "+00:00")).astimezone(C.TZ)
        if start_d <= sdt.date() < end_d:  # by START date only
            out.append(
                {
                    **base,
                    "date": sdt.date(),
                    "start": sdt.time(),
                    "end": edt.time() if edt and edt.date() == sdt.date() else None,
                    "all_day": False,
                }
            )
    return out


def get_events(start_d: date, end_exclusive: date) -> list[dict]:
    service = _service()
    time_min = datetime.combine(start_d, time.min, tzinfo=C.TZ).isoformat()
    time_max = datetime.combine(end_exclusive, time.min, tzinfo=C.TZ).isoformat()

    events = []
    for cal in get_calendars():
        token = None
        while True:
            resp = (
                service.events()
                .list(
                    calendarId=cal["id"],
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                    pageToken=token,
                )
                .execute()
            )
            for raw in resp.get("items", []):
                events.extend(_expand(raw, cal["kind"], start_d, end_exclusive))
            token = resp.get("nextPageToken")
            if not token:
                break

    events.sort(
        key=lambda e: (
            e["date"],
            0 if e["all_day"] else 1,
            e["start"] or time.min,
            e["name"].lower(),
        )
    )
    return events


# ------------------------------------------------------------------ writing
def add_event(
    name: str,
    day: date,
    start: time | None = None,
    location: str | None = None,
    kind: str = "personal",
    duration_minutes: int = 60,
) -> str | None:
    if start is None:
        body = {
            "summary": name,
            "location": location or "",
            "start": {"date": day.isoformat()},
            "end": {"date": (day + timedelta(days=1)).isoformat()},
        }
    else:
        begin = datetime.combine(day, start, tzinfo=C.TZ)
        finish = begin + timedelta(minutes=duration_minutes)
        body = {
            "summary": name,
            "location": location or "",
            "start": {"dateTime": begin.isoformat(), "timeZone": C.TIMEZONE_NAME},
            "end": {"dateTime": finish.isoformat(), "timeZone": C.TIMEZONE_NAME},
        }

    event = (
        _service()
        .events()
        .insert(calendarId=_calendar_id(kind), body=body)
        .execute()
    )
    return event.get("htmlLink")
