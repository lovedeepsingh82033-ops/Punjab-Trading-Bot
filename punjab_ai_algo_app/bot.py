"""PUNJAB AI ALGO Telegram companion — educational demo only."""
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("punjab-ai-algo")

DASHBOARD_URL = "https://punjab-ai-algo.streamlit.app/"
DISCLAIMER = (
    "Educational research / paper demo only. No live prices, "
    "trade recommendations, or order execution."
)


def dashboard_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            text="🌐 Open PUNJAB AI ALGO Dashboard",
            web_app=WebAppInfo(url=DASHBOARD_URL),
        )]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ PUNJAB AI ALGO\n\nWelcome!\n"
        + DISCLAIMER
        + "\n\nOpen the dashboard below or use /status, /research, /markets, /app, /help.",
        reply_markup=dashboard_keyboard(),
    )


async def app_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Open the educational research dashboard:",
        reply_markup=dashboard_keyboard(),
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🟢 BOT CODE: READY WHEN HOSTED\n"
        "📊 DATA: DEMO ONLY\n"
        "🔒 ORDER EXECUTION: DISABLED\n"
        "📡 LIVE FEED: NOT CONFIGURED"
    )


async def research(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 Research modules include educational market concepts, "
        "chart terminology, and hypothetical paper-journal notes. "
        "No BUY/SELL instructions are generated.\n" + DISCLAIMER
    )


async def markets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌍 Planned coverage: FX majors, selected FX crosses, "
        "and educational commodities/crypto examples. "
        "Current quotes are unavailable; no live market feed is configured."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start — welcome and dashboard\n"
        "/app — open dashboard\n"
        "/status — bot configuration status\n"
        "/research — educational research info\n"
        "/markets — planned market coverage\n"
        "/help — commands"
    )


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Set TELEGRAM_BOT_TOKEN in hosting secrets. Never commit or share it."
        )

    app = Application.builder().token(token).build()
    for command, handler in [
        ("start", start),
        ("app", app_command),
        ("status", status),
        ("research", research),
        ("markets", markets),
        ("help", help_command),
    ]:
        app.add_handler(CommandHandler(command, handler))

    log.info("Starting PUNJAB AI ALGO educational demo bot")
    app.run_polling()


if __name__ == "__main__":
    main()
