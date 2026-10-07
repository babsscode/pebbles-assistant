"""Telegram handlers: command routing, button callbacks, edit flow."""
import asyncio
import logging
import re

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import config as C
import dates
import formatting as fmt
import gcal_api
import keyboards as kb
import notion_api

log = logging.getLogger(__name__)
HTML = ParseMode.HTML

TASK_RE = re.compile(
    rf"^add\s+task\s+(.+?)\s+due\s+({dates.DATE_TOKEN})(?:\s+(\S+))?\s*$",
    re.IGNORECASE,
)
EVENT_RE = re.compile(
    rf"^add\s+(event|class)\s+(.+?)\s+on\s+({dates.DATE_TOKEN})"
    rf"(?:\s+({dates.TIME_TOKEN}))?(?:\s+at\s+(.+))?\s*$",
    re.IGNORECASE,
)


# ------------------------------------------------------------------ helpers
async def run(fn, *args, **kwargs):
    """Run blocking code (requests / Google client) off the event loop."""
    return await asyncio.to_thread(fn, *args, **kwargs)


def allowed(update: Update) -> bool:
    if not C.ALLOWED_USER_IDS:
        return True
    user = update.effective_user
    return bool(user and user.id in C.ALLOWED_USER_IDS)


async def send(update: Update, text: str, keyboard=None):
    """Edit the current message if triggered by a button, else reply."""
    text = fmt.fit(text)
    query = update.callback_query
    if query:
        try:
            await query.edit_message_text(text, parse_mode=HTML, reply_markup=keyboard)
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
    else:
        await update.effective_message.reply_text(
            text, parse_mode=HTML, reply_markup=keyboard
        )


def normalize(text: str) -> str:
    """'/agenda@MyBot week' -> 'agenda week'."""
    t = text.strip()
    if t.startswith("/"):
        first, _, rest = t[1:].partition(" ")
        t = f"{first.split('@')[0]} {rest}".strip()
    return re.sub(r"\s+", " ", t)


# -------------------------------------------------------------------- views
async def show_tasks(update: Update, scope: str):
    if scope == "o":
        start = dates.today()
        tasks = await run(notion_api.query_overdue, start)
    else:
        start, end = dates.scope_range(scope)
        tasks = await run(notion_api.query_tasks, start, end)
    await send(update, fmt.tasks_message(tasks, scope, start), kb.task_list(tasks, scope))


async def build_agenda_text(scope: str) -> str:
    start, end = dates.scope_range(scope)
    tasks, events, overdue = await asyncio.gather(
        run(notion_api.query_tasks, start, end),
        run(gcal_api.get_events, start, end),
        run(notion_api.query_overdue, dates.today())
        if scope == "t"
        else asyncio.sleep(0, result=[]),
        return_exceptions=True,
    )
    if isinstance(tasks, Exception):
        raise tasks

    calendar_error = isinstance(events, Exception)
    if calendar_error:
        log.error("Calendar error: %s", events)
        events = []
    overdue_count = 0 if isinstance(overdue, Exception) else len(overdue)

    return fmt.agenda_message(tasks, events, scope, start, overdue_count, calendar_error)


async def show_agenda(update: Update, scope: str):
    await send(update, await build_agenda_text(scope), kb.agenda(scope))


async def show_events(update: Update, scope: str):
    start, end = dates.scope_range(scope)
    events = await run(gcal_api.get_events, start, end)
    await send(update, fmt.events_message(events, scope, start), kb.events(scope))


async def show_task_detail(update: Update, page_id: str, scope: str, note: str = ""):
    task = await run(notion_api.get_page, page_id)
    text = fmt.task_detail(task) + (f"\n\n{note}" if note else "")
    await send(update, text, kb.task_detail(page_id, scope))


# ---------------------------------------------------------------- callbacks
EDIT_PROMPTS = {
    "n": "✏️ <b>Rename task</b>\n\nSend the new name.",
    "c": (
        "📚 <b>Change course</b>\n\nSend the course name or a shortcut.\n"
        + "Shortcuts: "
        + ", ".join(f"<code>{k}</code>" for k in C.COURSE_ALIASES)
    ),
    "d": (
        "📅 <b>Change due date</b>\n\nSend the new date:\n"
        "<code>10/20</code> · <code>fri</code> · <code>tomorrow</code>"
    ),
    "t": (
        "⏰ <b>Change due time</b>\n\nSend the new time:\n"
        "<code>5pm</code> · <code>11:59 pm</code> · <code>14:30</code>"
    ),
}


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    if not allowed(update):
        return

    parts = (query.data or "").split(":")
    action = parts[0]

    try:
        if action == "ls":
            context.user_data.pop("edit", None)
            await show_tasks(update, parts[1])

        elif action == "ag":
            await show_agenda(update, parts[1])

        elif action == "ev":
            await show_events(update, parts[1])

        elif action == "sel":
            context.user_data.pop("edit", None)
            await show_task_detail(update, parts[1], parts[2])

        elif action == "st":
            _, page_id, code, scope = parts
            await run(notion_api.update_task, page_id, status=C.STATUS_CODES[code])
            await show_task_detail(update, page_id, scope, "✅ <i>Status updated</i>")

        elif action == "ed":
            _, page_id, scope = parts
            await send(update, "✏️ <b>Edit task</b>\n\nWhat do you want to change?",
                       kb.edit_menu(page_id, scope))

        elif action == "ef":
            _, field, page_id, scope = parts
            context.user_data["edit"] = {
                "id": page_id,
                "field": field,
                "scope": scope,
                "chat_id": query.message.chat_id,
                "msg_id": query.message.message_id,
            }
            await send(update, EDIT_PROMPTS[field], kb.cancel_edit(page_id, scope))

        elif action == "cx":
            context.user_data.pop("edit", None)
            await show_task_detail(update, parts[1], parts[2])

        elif action == "dl":
            _, page_id, scope = parts
            task = await run(notion_api.get_page, page_id)
            await send(
                update,
                f"🗑 Delete <b>{fmt.esc(task['name'])}</b>?\n\n"
                "<i>It moves to Notion's trash, so you can restore it there.</i>",
                kb.confirm_delete(page_id, scope),
            )

        elif action == "dy":
            _, page_id, scope = parts
            await run(notion_api.archive_task, page_id)
            await show_tasks(update, scope)

    except Exception:
        log.exception("Callback failed: %s", query.data)
        await query.message.reply_text("❌ Something went wrong. Please try again.")


# --------------------------------------------------------------- edit flow
async def handle_edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    edit = context.user_data.get("edit")
    if not edit:
        return False

    msg = update.effective_message
    value = msg.text.strip()
    page_id, field = edit["id"], edit["field"]

    try:
        if field == "n":
            await run(notion_api.update_task, page_id, name=value)
        elif field == "c":
            await run(notion_api.update_task, page_id, course=value)
        elif field == "d":
            try:
                due = dates.parse_date_input(value)
            except ValueError:
                await msg.reply_text(
                    "🤔 I couldn't read that date. Try <code>10/20</code>, "
                    "<code>fri</code> or <code>tomorrow</code>.",
                    parse_mode=HTML,
                )
                return True
            await run(notion_api.update_task, page_id, due=due)
        elif field == "t":
            try:
                t = dates.parse_time_input(value)
            except ValueError:
                await msg.reply_text(
                    "🤔 I couldn't read that time. Try <code>5pm</code> or "
                    "<code>11:59 pm</code>.",
                    parse_mode=HTML,
                )
                return True
            await run(notion_api.update_task, page_id, time_text=dates.fmt_time(t))
        else:
            return False
    except Exception:
        log.exception("Edit failed")
        await msg.reply_text("❌ Couldn't update that. Check the value and try again.")
        return True

    context.user_data.pop("edit", None)

    task = await run(notion_api.get_page, page_id)
    text = fmt.task_detail(task) + "\n\n✅ <i>Updated</i>"
    keyboard = kb.task_detail(page_id, edit["scope"])
    try:  # turn the prompt message into the updated task
        await context.bot.edit_message_text(
            text,
            chat_id=edit["chat_id"],
            message_id=edit["msg_id"],
            parse_mode=HTML,
            reply_markup=keyboard,
        )
    except BadRequest:
        await msg.reply_text(text, parse_mode=HTML, reply_markup=keyboard)
    try:  # keep the chat tidy
        await msg.delete()
    except BadRequest:
        pass
    return True


# ------------------------------------------------------------ add commands
async def add_task(update: Update, text: str):
    msg = update.effective_message
    m = TASK_RE.match(text)
    if not m:
        await msg.reply_text(
            "❌ Try:\n<code>add task Read ch 5 due 10/15 cs</code>\n"
            "<code>add task Quiz due fri</code>",
            parse_mode=HTML,
        )
        return

    name, date_str, course = m.group(1).strip(), m.group(2), m.group(3)
    try:
        due = dates.parse_date_input(date_str)
    except ValueError:
        await msg.reply_text("❌ That date isn't valid.")
        return

    task = await run(notion_api.create_task, name, due, course)
    lines = ["✅ <b>Task added</b>", fmt.LINE, f"📌 {fmt.esc(task['name'])}"]
    if task["course"]:
        lines.append(f"📚 {fmt.esc(task['course'])}")
    lines.append(f"📅 {fmt.esc(dates.fmt_date_short(due))}")
    lines.append(f"⏰ {C.DEFAULT_DUE_TIME}")
    await msg.reply_text("\n".join(lines), parse_mode=HTML, reply_markup=kb.after_add_task())


async def add_event(update: Update, text: str):
    msg = update.effective_message
    m = EVENT_RE.match(text)
    if not m:
        await msg.reply_text(
            "❌ Try:\n<code>add event Study group on fri 6pm at Library</code>\n"
            "<code>add class Exam on 10/15 2:30 pm at Klaus 2447</code>",
            parse_mode=HTML,
        )
        return

    kind = "classes" if m.group(1).lower() == "class" else "personal"
    name, date_str, time_str, location = (
        m.group(2).strip(), m.group(3), m.group(4), m.group(5),
    )
    try:
        day = dates.parse_date_input(date_str)
        start = dates.parse_time_input(time_str) if time_str else None
    except ValueError:
        await msg.reply_text("❌ That date or time isn't valid.")
        return

    link = await run(
        gcal_api.add_event, name, day, start, location.strip() if location else None, kind
    )
    emoji = C.EVENT_EMOJI[kind]
    lines = ["✅ <b>Event added</b>", fmt.LINE, f"{emoji} {fmt.esc(name)}",
             f"📅 {fmt.esc(dates.fmt_date_short(day))}"]
    if start:
        lines.append(f"⏰ {dates.fmt_time(start)} (1 hour)")
    if location:
        lines.append(f"📍 {fmt.esc(location.strip())}")
    if link:
        lines.append(f'🔗 <a href="{fmt.esc(link)}">Open in Google Calendar</a>')
    await msg.reply_text("\n".join(lines), parse_mode=HTML)


# --------------------------------------------------------- message routing
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text or not allowed(update):
        return

    raw = msg.text.strip()
    text = normalize(raw)
    low = text.lower()

    if raw.startswith("/") or low == "cancel":
        cancelled = context.user_data.pop("edit", None)
        if low == "cancel":
            await msg.reply_text("👍 Cancelled." if cancelled else "Nothing to cancel.")
            return
    elif await handle_edit_text(update, context):
        return

    words = low.split()
    cmd, args = (words[0] if words else ""), words[1:]

    try:
        if cmd in ("start", "help", "menu"):
            await msg.reply_text(fmt.help_text(), parse_mode=HTML)

        elif cmd in ("agenda", "today", "tomorrow", "week"):
            scope = {"today": "t", "tomorrow": "m", "week": "w"}.get(cmd) or dates.parse_scope(args)
            if scope == "o":
                await show_tasks(update, "o")
            elif scope:
                await show_agenda(update, scope)
            else:
                await msg.reply_text("Try <code>agenda</code>, <code>agenda tomorrow</code> or <code>agenda week</code>.", parse_mode=HTML)

        elif cmd == "tasks":
            scope = dates.parse_scope(args)
            if scope:
                await show_tasks(update, scope)
            else:
                await msg.reply_text("Try <code>tasks</code>, <code>tasks tomorrow</code>, <code>tasks week</code> or <code>tasks overdue</code>.", parse_mode=HTML)

        elif cmd == "events":
            scope = dates.parse_scope(args)
            if scope and scope != "o":
                await show_events(update, scope)
            else:
                await msg.reply_text("Try <code>events</code>, <code>events tomorrow</code> or <code>events week</code>.", parse_mode=HTML)

        elif cmd in ("overdue", "late"):
            await show_tasks(update, "o")

        elif cmd == "add" and args[:1] == ["task"]:
            await add_task(update, text)

        elif cmd == "add" and args[:1] in (["event"], ["class"]):
            await add_event(update, text)

        else:
            await msg.reply_text(
                "🤔 I didn't get that. Send <code>help</code> to see what I can do.",
                parse_mode=HTML,
            )
    except Exception:
        log.exception("Message handler failed: %s", raw)
        await msg.reply_text("❌ Something went wrong. Please try again.")


# ------------------------------------------------------------ morning digest
async def send_digest(context: ContextTypes.DEFAULT_TYPE):
    try:
        text = await build_agenda_text("t")
        await context.bot.send_message(
            chat_id=int(C.DIGEST_CHAT_ID),
            text="☀️ <b>Good morning!</b>\n\n" + fmt.fit(text),
            parse_mode=HTML,
        )
    except Exception:
        log.exception("Digest failed")
