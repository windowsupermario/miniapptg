import os
import threading
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")

_app = None
_stop_event = threading.Event()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть Mini App", web_app={"url": APP_URL})]
        ]
    )
    await update.message.reply_text(
        "Добро пожаловать! Нажми кнопку, чтобы открыть Mini App:",
        reply_markup=keyboard,
    )


def start_bot():
    global _app
    _app = Application.builder().token(BOT_TOKEN).build()
    _app.add_handler(CommandHandler("start", start))
    _app.run_polling(allowed_updates=Update.ALL_TYPES)


def stop_bot():
    if _app:
        _app.stop_running()


if __name__ == "__main__":
    start_bot()
