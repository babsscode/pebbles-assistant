"""Inline keyboards.

Callback data (Telegram limit: 64 bytes). IDs are Notion page IDs without
dashes (32 chars). 'scope' is where the user came from: t / m / w / o.

  ls:{scope}                 task list          ag:{scope}  agenda
  ev:{scope}                 events             sel:{id}:{scope}  open task
  st:{id}:{code}:{scope}     set status         ed:{id}:{scope}   edit menu
  ef:{field}:{id}:{scope}    edit a field       cx:{id}:{scope}   cancel edit
  dl:{id}:{scope}            ask delete         dy:{id}:{scope}   confirm delete
"""
from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Markup


def sid(page_id: str) -> str:
    return page_id.replace("-", "")


def nav_row(prefix: str, current: str, with_overdue: bool = False):
    items = [("t", "Today"), ("m", "Tmrw"), ("w", "Week")]
    if with_overdue:
        items.append(("o", "⚠️ Late"))
    return [
        Btn(("• " if key == current else "") + label, callback_data=f"{prefix}:{key}")
        for key, label in items
    ]


def _agenda_scope(scope: str) -> str:
    return "t" if scope == "o" else scope


def task_list(tasks: list[dict], scope: str) -> Markup:
    rows, row = [], []
    for i, task in enumerate(tasks, start=1):
        row.append(Btn(str(i), callback_data=f"sel:{sid(task['id'])}:{scope}"))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append(nav_row("ls", scope, with_overdue=True))
    rows.append([Btn("📋 Agenda", callback_data=f"ag:{_agenda_scope(scope)}")])
    return Markup(rows)


def agenda(scope: str) -> Markup:
    return Markup(
        [
            nav_row("ag", scope),
            [
                Btn("📚 Tasks", callback_data=f"ls:{scope}"),
                Btn("📆 Events", callback_data=f"ev:{scope}"),
            ],
        ]
    )


def events(scope: str) -> Markup:
    return Markup(
        [
            nav_row("ev", scope),
            [
                Btn("📋 Agenda", callback_data=f"ag:{scope}"),
                Btn("📚 Tasks", callback_data=f"ls:{scope}"),
            ],
        ]
    )


def task_detail(page_id: str, scope: str) -> Markup:
    i = sid(page_id)
    return Markup(
        [
            [
                Btn("🟡 In Progress", callback_data=f"st:{i}:p:{scope}"),
                Btn("✅ Done", callback_data=f"st:{i}:d:{scope}"),
            ],
            [
                Btn("▫️ Not Started", callback_data=f"st:{i}:n:{scope}"),
                Btn("✏️ Edit", callback_data=f"ed:{i}:{scope}"),
            ],
            [
                Btn("🗑 Delete", callback_data=f"dl:{i}:{scope}"),
                Btn("◀️ Back to list", callback_data=f"ls:{scope}"),
            ],
        ]
    )


def edit_menu(page_id: str, scope: str) -> Markup:
    i = sid(page_id)
    return Markup(
        [
            [
                Btn("✏️ Name", callback_data=f"ef:n:{i}:{scope}"),
                Btn("📚 Course", callback_data=f"ef:c:{i}:{scope}"),
            ],
            [
                Btn("📅 Due date", callback_data=f"ef:d:{i}:{scope}"),
                Btn("⏰ Time", callback_data=f"ef:t:{i}:{scope}"),
            ],
            [Btn("◀️ Back", callback_data=f"sel:{i}:{scope}")],
        ]
    )


def cancel_edit(page_id: str, scope: str) -> Markup:
    return Markup([[Btn("✖️ Cancel", callback_data=f"cx:{sid(page_id)}:{scope}")]])


def confirm_delete(page_id: str, scope: str) -> Markup:
    i = sid(page_id)
    return Markup(
        [
            [
                Btn("🗑 Yes, delete", callback_data=f"dy:{i}:{scope}"),
                Btn("◀️ No", callback_data=f"sel:{i}:{scope}"),
            ]
        ]
    )


def after_add_task() -> Markup:
    return Markup(
        [
            [
                Btn("📚 Tasks this week", callback_data="ls:w"),
                Btn("📋 Agenda", callback_data="ag:t"),
            ]
        ]
    )
