"""PUNJAB AI ALGO Telegram companion — educational demo only."""
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
logging.basicConfig(level=logging.INFO)
log=logging.getLogger("punjab-ai-algo")
DISCLAIMER="Educational research / paper demo only. No live prices, trade recommendations, or order execution."
async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
 await update.message.reply_text("🟠 PUNJAB AI ALGO\n\nWelcome!\n"+DISCLAIMER+"\n\nCommands: /status /research /markets /help")
async def status(update:Update,context:ContextTypes.DEFAULT_TYPE):
 await update.message.reply_text("🟢 SERVICE: ONLINE\n📊 DATA: DEMO ONLY\n🔒 ORDER EXECUTION: DISABLED\n📡 LIVE FEED: NOT CONFIGURED")
async def research(update:Update,context:ContextTypes.DEFAULT_TYPE):
 await update.message.reply_text("📚 Research modules are under development. No BUY/SELL instructions are generated.\n"+DISCLAIMER)
async def markets(update:Update,context:ContextTypes.DEFAULT_TYPE):
 await update.message.reply_text("🌍 Planned watchlist: FX majors, selected FX crosses, and XAU/USD. Current quotes are unavailable until a verified data source is configured.")
async def help_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
 await update.message.reply_text("/start — welcome\n/status — service status\n/research — research info\n/markets — watchlist info\n/help — commands")
def main():
 token=os.getenv("TELEGRAM_BOT_TOKEN")
 if not token: raise RuntimeError("Set TELEGRAM_BOT_TOKEN in hosting secrets. Never commit or share it.")
 app=Application.builder().token(token).build()
 for command,handler in [("start",start),("status",status),("research",research),("markets",markets),("help",help_command)]:
  app.add_handler(CommandHandler(command,handler))
 log.info("Starting PUNJAB AI ALGO demo bot")
 app.run_polling()
if __name__=="__main__": main()
