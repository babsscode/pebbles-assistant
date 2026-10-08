"""Central configuration: env vars, property names, aliases."""
import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------- Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Optional: comma separated Telegram user IDs allowed to use the bot.
# Leave empty to allow everyone (not recommended).
ALLOWED_USER_IDS = {
    int(x)
    for x in os.getenv("ALLOWED_USER_IDS", "").replace(" ", "").split(",")
    if x
}

# Optional morning digest (needs python-telegram-bot[job-queue])
DIGEST_CHAT_ID = os.getenv("DIGEST_CHAT_ID")
DIGEST_TIME = os.getenv("DIGEST_TIME", "07:30")  # HH:MM in your timezone

# ------------------------------------------------------------------ Notion
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
NOTION_VERSION = "2022-06-28"

NAME_PROPERTY = "name"
COURSE_PROPERTY = "course"
DUE_DATE_PROPERTY = "due"
STATUS_PROPERTY = "status"
TIME_PROPERTY = "time"
DO_DATE_PROPERTY = "do"

DEFAULT_DUE_TIME = "11:59 PM"

STATUS_CODES = {
    "n": "not started",
    "p": "in progress",
    "d": "done",
}
DONE_WORDS = {"done", "completed", "complete", "finished"}
PROGRESS_WORDS = {"in progress", "in-progress", "inprogress", "doing"}

COURSE_ALIASES = {
    "cs": "CS 1100",
    "dsa": "CS 1331",
    "gc": "PUBP 1142",
    "phys": "PHYS 2211",
    "math": "MATH 1554",
}

# --------------------------------------------------------- Google Calendar
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar"]

# "myCalendar" (your other events). Auto-discovered by name if not set.
PERSONAL_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
# "classes" calendar. Optional ID, otherwise found by its name.
CLASSES_CALENDAR_ID = os.getenv("CLASSES_CALENDAR_ID")
CLASSES_CALENDAR_NAME = os.getenv("CLASSES_CALENDAR_NAME", "classes")
PERSONAL_CALENDAR_NAME = os.getenv("PERSONAL_CALENDAR_NAME", "myCalendar")

EVENT_EMOJI = {"classes": "🎓", "personal": "▫️"}

# ---------------------------------------------------------------- Timezone
TIMEZONE_NAME = os.getenv("TIMEZONE", "America/New_York")
TZ = ZoneInfo(TIMEZONE_NAME)


def validate():
    missing = [
        name
        for name, value in [
            ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
            ("NOTION_TOKEN", NOTION_TOKEN),
            ("NOTION_DATABASE_ID", NOTION_DATABASE_ID),
        ]
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")
