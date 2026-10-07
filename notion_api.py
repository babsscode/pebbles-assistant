"""Everything that talks to Notion."""
from datetime import date

import requests

import config as C


class NotionError(Exception):
    pass


# ----------------------------------------------------------------- plumbing
def _headers():
    return {
        "Authorization": f"Bearer {C.NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": C.NOTION_VERSION,
    }


def _call(method: str, url: str, **kwargs) -> dict:
    r = requests.request(method, url, headers=_headers(), timeout=15, **kwargs)
    if not r.ok:
        print("Notion error:", r.status_code, r.text)
        raise NotionError(f"Notion API error {r.status_code}")
    return r.json()


def resolve_course(course: str) -> str:
    return C.COURSE_ALIASES.get(course.strip().lower(), course.strip())


# ------------------------------------------------------ property builders
def _title(v):
    return {"title": [{"text": {"content": v}}]}


def _select(v):
    return {"select": {"name": v}}


def _rich(v):
    return {"rich_text": [{"text": {"content": v}}]}


def _date(d: date):
    return {"date": {"start": d.isoformat()}}


# ----------------------------------------------------------------- parsing
def _text(prop) -> str:
    if not prop:
        return ""
    kind = prop.get("type")
    if kind in ("title", "rich_text"):
        return "".join(i.get("plain_text", "") for i in prop.get(kind, []))
    if kind in ("select", "status"):
        v = prop.get(kind)
        return v.get("name", "") if v else ""
    if kind == "number":
        return "" if prop.get("number") is None else str(prop["number"])
    return ""


def _date_of(prop) -> date | None:
    if not prop or prop.get("type") != "date" or not prop.get("date"):
        return None
    start = prop["date"].get("start")
    return date.fromisoformat(start[:10]) if start else None


def is_done(status: str) -> bool:
    return (status or "").strip().lower() in C.DONE_WORDS


def status_icon(status: str) -> str:
    s = (status or "").strip().lower()
    if s in C.DONE_WORDS:
        return "✅"
    if s in C.PROGRESS_WORDS:
        return "🟡"
    return "▫️"


def parse_task(page: dict) -> dict:
    p = page.get("properties", {})
    status = _text(p.get(C.STATUS_PROPERTY)) or "not started"
    return {
        "id": page["id"],
        "name": _text(p.get(C.NAME_PROPERTY)) or "Unnamed task",
        "course": _text(p.get(C.COURSE_PROPERTY)),
        "status": status,
        "icon": status_icon(status),
        "done": is_done(status),
        "time": _text(p.get(C.TIME_PROPERTY)),
        "date": _date_of(p.get(C.DUE_DATE_PROPERTY)),
    }


def _sorted(tasks):
    return sorted(
        tasks, key=lambda t: (t["date"] or date.max, t["name"].lower())
    )


# ----------------------------------------------------------------- queries
def _query(filter_obj: dict) -> list[dict]:
    url = f"https://api.notion.com/v1/databases/{C.NOTION_DATABASE_ID}/query"
    results, cursor = [], None
    while True:
        payload = {"page_size": 100, "filter": filter_obj}
        if cursor:
            payload["start_cursor"] = cursor
        data = _call("POST", url, json=payload)
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            return results
        cursor = data.get("next_cursor")


def query_tasks(start: date, end_exclusive: date) -> list[dict]:
    pages = _query(
        {
            "and": [
                {
                    "property": C.DUE_DATE_PROPERTY,
                    "date": {"on_or_after": start.isoformat()},
                },
                {
                    "property": C.DUE_DATE_PROPERTY,
                    "date": {"before": end_exclusive.isoformat()},
                },
            ]
        }
    )
    tasks = [parse_task(p) for p in pages]
    # Safety net: only keep tasks that really fall in the range
    tasks = [t for t in tasks if t["date"] and start <= t["date"] < end_exclusive]
    return _sorted(tasks)


def query_overdue(today: date) -> list[dict]:
    pages = _query(
        {
            "property": C.DUE_DATE_PROPERTY,
            "date": {"before": today.isoformat()},
        }
    )
    tasks = [parse_task(p) for p in pages]
    tasks = [t for t in tasks if t["date"] and t["date"] < today and not t["done"]]
    return _sorted(tasks)


def get_page(page_id: str) -> dict:
    return parse_task(_call("GET", f"https://api.notion.com/v1/pages/{page_id}"))


# ---------------------------------------------------------------- mutations
def create_task(
    name: str,
    due: date,
    course: str | None = None,
    time_text: str = C.DEFAULT_DUE_TIME,
) -> dict:
    props = {
        C.NAME_PROPERTY: _title(name),
        C.STATUS_PROPERTY: _select("not started"),
        C.DUE_DATE_PROPERTY: _date(due),
        C.DO_DATE_PROPERTY: _date(due),
        C.TIME_PROPERTY: _rich(time_text),
    }
    if course:
        props[C.COURSE_PROPERTY] = _select(resolve_course(course))

    page = _call(
        "POST",
        "https://api.notion.com/v1/pages",
        json={"parent": {"database_id": C.NOTION_DATABASE_ID}, "properties": props},
    )
    return parse_task(page)


def update_task(
    page_id: str,
    name: str | None = None,
    course: str | None = None,
    due: date | None = None,
    time_text: str | None = None,
    status: str | None = None,
) -> dict | None:
    props = {}
    if name is not None:
        props[C.NAME_PROPERTY] = _title(name)
    if course is not None:
        props[C.COURSE_PROPERTY] = _select(resolve_course(course))
    if due is not None:
        props[C.DUE_DATE_PROPERTY] = _date(due)
        props[C.DO_DATE_PROPERTY] = _date(due)
    if time_text is not None:
        props[C.TIME_PROPERTY] = _rich(time_text)
    if status is not None:
        props[C.STATUS_PROPERTY] = _select(status)
    if not props:
        return None

    return parse_task(
        _call(
            "PATCH",
            f"https://api.notion.com/v1/pages/{page_id}",
            json={"properties": props},
        )
    )


def archive_task(page_id: str) -> None:
    _call(
        "PATCH",
        f"https://api.notion.com/v1/pages/{page_id}",
        json={"archived": True},
    )
