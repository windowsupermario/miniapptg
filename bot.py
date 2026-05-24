import os
import threading
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")
ADMIN_ID = 7153815329

_app = None
_stop_event = threading.Event()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    ref_text = ""
    if args and args[0].startswith("ref_"):
        ref_id = args[0][4:]
        ref_text = f"\n\n👋 Вас пригласил пользователь {ref_id}!"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть Mini App", web_app={"url": APP_URL + (f"?ref={ref_id}" if ref_id else "")})]
        ]
    )
    await update.message.reply_text(
        "Добро пожаловать! Нажми кнопку, чтобы открыть Mini App:" + ref_text,
        reply_markup=keyboard,
    )


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Доступ запрещён")
        return

    if not context.args:
        await update.message.reply_text("Использование: /broadcast <текст>")
        return

    text = " ".join(context.args)
    from database import get_all_user_ids
    user_ids = await get_all_user_ids()
    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=int(uid), text=text)
            sent += 1
        except:
            failed += 1
    await update.message.reply_text(f"✅ Рассылка завершена\nОтправлено: {sent}\nОшибок: {failed}")


def start_bot():
    global _app
    _app = Application.builder().token(BOT_TOKEN).build()
    _app.add_handler(CommandHandler("start", start))
    _app.add_handler(CommandHandler("broadcast", broadcast))
    _app.run_polling(allowed_updates=Update.ALL_TYPES)


def stop_bot():
    if _app:
        _app.stop_running()


if __name__ == "__main__":
    start_bot()
