"""Entry point:  python bot.py"""
import logging
from datetime import time as dtime

from telegram import BotCommand
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters

import config as C
import handlers

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bot")


async def post_init(app: Application):
    await app.bot.set_my_commands(
        [
            BotCommand("agenda", "Today's schedule + due tasks"),
            BotCommand("tasks", "Today's tasks (tap to edit)"),
            BotCommand("events", "Today's calendar events"),
            BotCommand("tomorrow", "Tomorrow's agenda"),
            BotCommand("week", "This week's agenda"),
            BotCommand("overdue", "Tasks you're behind on"),
            BotCommand("help", "How to add tasks & events"),
        ]
    )


async def on_error(update, context):
    log.error("Unhandled error", exc_info=context.error)


def main():
    C.validate()

    app = Application.builder().token(C.TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # TEXT includes /commands, so both "agenda week" and "/agenda week" work.
    app.add_handler(MessageHandler(filters.TEXT, handlers.on_message))
    app.add_handler(CallbackQueryHandler(handlers.on_callback))
    app.add_error_handler(on_error)

    if C.DIGEST_CHAT_ID:
        if app.job_queue is None:
            log.warning(
                "Morning digest needs: pip install 'python-telegram-bot[job-queue]'"
            )
        else:
            hour, minute = map(int, C.DIGEST_TIME.split(":"))
            app.job_queue.run_daily(
                handlers.send_digest, time=dtime(hour, minute, tzinfo=C.TZ)
            )
            log.info("Morning digest scheduled for %s %s", C.DIGEST_TIME, C.TIMEZONE_NAME)

    log.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
