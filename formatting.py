"""Builds the message text (Telegram HTML), tuned for phone screens."""
import html
from datetime import date, timedelta

import config as C
import dates

esc = html.escape
LINE = "━━━━━━━━━━━━━━━"


def fit(text: str, limit: int = 4000) -> str:
    """Telegram caps messages at 4096 chars. Cut on a line boundary."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit("\n", 1)[0] + "\n…<i>(too long, trimmed)</i>"


def progress_bar(done: int, total: int, width: int = 8) -> str:
    filled = round(width * done / total) if total else 0
    return "▰" * filled + "▱" * (width - filled)


def day_header(d: date) -> str:
    rel = dates.relative_label(d)
    tag = f" <i>· {rel}</i>" if rel else ""
    return f"<b>{esc(dates.fmt_date_short(d))}</b>{tag}"


# ------------------------------------------------------------------- lines
def task_lines(task: dict, number: int | None = None) -> list[str]:
    prefix = f"{number}. " if number else ""
    name = esc(task["name"])
    name = f"<s>{name}</s>" if task["done"] else f"<b>{name}</b>"
    lines = [f"{prefix}{task['icon']} {name}"]

    meta = []
    #if task["course"]:
    if False:
        meta.append(esc(task["course"]))
    #if task["time"]:
    if False:
        meta.append(f"⏰ {esc(task['time'])}")
    if meta:
        lines.append(f"      ↳ {' · '.join(meta)}")
    return lines


def event_lines(event: dict) -> list[str]:
    emoji = "" if event["all_day"] else C.EVENT_EMOJI.get(event["kind"], "▫️")
    when = "All day" if event["all_day"] else dates.fmt_range(event["start"], event["end"])
    lines = [f"{emoji} {esc(event['name'])}· {when}"]
    #if event.get("location"):
    if (False):
        lines.append(f"      ↳ 📍 {esc(event['location'])}")
    return lines


# --------------------------------------------------------------- tasks list
def tasks_message(tasks: list[dict], scope: str, start: date) -> str:
    lines = [f"📚 <b>Tasks · {esc(dates.scope_title(scope, start))}</b>", LINE]

    if not tasks:
        lines.append("🎉 No overdue tasks!" if scope == "o" else "🎉 Nothing due. You're all clear!")
        return "\n".join(lines)

    if scope != "o":
        done = sum(t["done"] for t in tasks)
        lines.append(f"{progress_bar(done, len(tasks))}  {done}/{len(tasks)} done")
    lines.append("")

    multi_day = scope in ("w", "o")
    current, n = None, 0
    for task in tasks:
        if multi_day and task["date"] != current:
            current = task["date"]
            if n:
                lines.append("")
            lines.append(day_header(current))
        n += 1
        lines.extend(task_lines(task, n))

    lines += ["", "👇 <i>Tap a number to open / edit</i>"]
    return "\n".join(lines)


# ------------------------------------------------------------------- agenda
def agenda_message(
    tasks: list[dict],
    events: list[dict],
    scope: str,
    start: date,
    overdue_count: int = 0,
    calendar_error: bool = False,
) -> str:
    lines = [f"📋 <b>Agenda · {esc(dates.scope_title(scope, start))}</b>", LINE]

    days = sorted({t["date"] for t in tasks} | {e["date"] for e in events})
    multi_day = scope == "w"

    if not days:
        lines.append("")
        lines.append("🎉 Nothing scheduled. Enjoy the free time!")
    for d in days:
        lines.append("")
        if multi_day:
            lines.append(day_header(d))
        day_events = [e for e in events if e["date"] == d]
        day_tasks = [t for t in tasks if t["date"] == d]

        if day_events:
            lines.append("<i>Schedule</i>")
            for e in day_events:
                lines.extend(event_lines(e))
        if day_tasks:
            if day_events:
                lines.append("")
            lines.append("📚 <i>Due</i>")
            for t in day_tasks:
                lines.extend(task_lines(t))

    if multi_day:
        free = [
            (start + timedelta(days=i)) for i in range(7)
            if (start + timedelta(days=i)) not in days
        ]
        if free:
            lines += ["", "😌 <i>Free: " + ", ".join(d.strftime("%a") for d in free) + "</i>"]

    if overdue_count:
        lines += ["", f"⚠️ <b>{overdue_count} overdue</b> — send <code>overdue</code> to see them"]
    if calendar_error:
        lines += ["", "⚠️ <i>Couldn't load calendar events.</i>"]

    return "\n".join(lines)


# ------------------------------------------------------------------- events
def events_message(events: list[dict], scope: str, start: date) -> str:
    lines = [f"📆 <b>Events · {esc(dates.scope_title(scope, start))}</b>", LINE]

    if not events:
        lines += ["", "No events. 🙌"]
        return "\n".join(lines)

    lines.append("🎓 classes   📅 other")
    multi_day = scope == "w"
    current = None
    for e in events:
        if multi_day and e["date"] != current:
            current = e["date"]
            lines += ["", day_header(current)]
        elif not multi_day and current is None:
            current = e["date"]
            lines.append("")
        lines.extend(event_lines(e))
    return "\n".join(lines)


# -------------------------------------------------------------- task detail
def task_detail(task: dict) -> str:
    lines = [f"📌 <b>{esc(task['name'])}</b>", LINE]
    if task["course"]:
        lines.append(f"📚 {esc(task['course'])}")
    if task["date"]:
        rel = dates.relative_label(task["date"])
        extra = f" <i>({rel})</i>" if rel else ""
        lines.append(f"📅 Due {esc(dates.fmt_date_short(task['date']))}{extra}")
    if task["time"]:
        lines.append(f"⏰ {esc(task['time'])}")
    lines.append(f"{task['icon']} {esc(task['status'].title())}")
    return "\n".join(lines)


# --------------------------------------------------------------------- help
def help_text() -> str:
    return (
        "👋 <b>Study Assistant</b>\n"
        f"{LINE}\n\n"
        "📋 <b>See your day</b>\n"
        "<code>agenda</code> · <code>agenda tomorrow</code> · <code>agenda week</code>\n"
        "<code>tasks</code> · <code>tasks tomorrow</code> · <code>tasks week</code>\n"
        "<code>events</code> · <code>events tomorrow</code> · <code>events week</code>\n"
        "<code>overdue</code> — what you're behind on\n"
        "Shortcuts: <code>today</code> <code>tomorrow</code> <code>week</code>\n\n"
        "➕ <b>Add a task</b>\n"
        "<code>add task Read ch 5 due 10/15 cs</code>\n"
        "<code>add task Quiz due fri math</code>\n"
        "<code>add task Lab report due tomorrow</code>\n\n"
        "➕ <b>Add an event</b>\n"
        "<code>add event Study group on fri 6pm at Library</code>\n"
        "<code>add class Exam on 10/15 2:30 pm at Klaus 2447</code> (🎓)\n\n"
        "💡 Dates: <code>10/15</code>, <code>today</code>, <code>tomorrow</code>, <code>fri</code>\n"
        "💡 Open a task from <code>tasks</code> to change status, edit or delete it.\n"
        "💡 Course shortcuts: "
        + ", ".join(f"<code>{k}</code>" for k in C.COURSE_ALIASES)
    )
