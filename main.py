import asyncio
import logging
from telegram.ext import Application, CallbackQueryHandler

from config import BOT_TOKEN
from handlers.submit import build_submit_handler
from handlers.admin import build_admin_handler, handle_approve

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # הגשת כלי (ConversationHandler)
    app.add_handler(build_submit_handler())

    # אישור מאדמין
    app.add_handler(CallbackQueryHandler(handle_approve, pattern=r"^approve:\w+$"))

    # דחייה מאדמין (ConversationHandler — כולל קבלת סיבה)
    app.add_handler(build_admin_handler())

    logger.info("🤖 הבוט עלה ופועל")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    # Python 3.14 no longer implicitly creates an event loop in get_event_loop()
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    main()
