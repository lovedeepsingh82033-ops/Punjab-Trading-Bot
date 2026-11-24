"""Read-only Telegram command worker for Punjab AI Super Bot."""
import json
import logging
import os
import time
from pathlib import Path

import requests

TOKEN = os.getenv("SUPER_BOT_TOKEN", "").strip()
ALLOWED_IDS = {x.strip() for x in os.getenv("SUPER_BOT_ALLOWED_USER_IDS", "").split(",") if x.strip()}
STATE_PATH = Path(os.getenv("BOT_STATE_PATH", "bot_state.json"))
API = "https://api.telegram.org/bot" + TOKEN
session = requests.Session()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def load_state():
    try:
        with STATE_PATH.open(encoding="utf-8") as stream:
            state = json.load(stream)
        return state if state.get("schema_version") == 1 else None
    except (OSError, ValueError, TypeError):
        return None


def compact(value, limit=2400):
    rendered = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return rendered if len(rendered) <= limit else rendered[:limit - 20] + "\n…(trimmed)"


def render(command):
    if command in ("/start", "/help"):
        return ("🤖 Punjab AI Super Bot\n\n/status — latest scan\n/health — scanner health"
                "\n/research — Intelligence Hub\n/calendar — economic calendar"
                "\n/history — latest observations\n/help — commands\n\n"
                "Research-only. No orders are placed.")
    state = load_state()
    if state is None:
        return "Scanner snapshot is not available yet. The bot needs the scanner's refreshed BOT_STATE_PATH."
    if command == "/status":
        health = state.get("scanner_health", {})
        return (f"📊 Punjab Scanner Status\nLast snapshot: {state.get('generated_at', 'unknown')}"
                f"\nObservations: {state.get('observation_count', 0)}"
                f"\nHealth: {health.get('status', 'unknown')}")
    if command == "/health":
        return "🩺 Scanner Health\n" + compact(state.get("scanner_health", {}))
    if command == "/research":
        return "🧠 Intelligence Hub\n" + compact(state.get("intelligence", {}))
    if command == "/calendar":
        return "🗓 Economic Calendar\n" + compact(state.get("calendar", {}))
    if command == "/history":
        return "📚 Latest Research Observations\n" + compact(state.get("observations", []))
    return "Unknown command. Send /help."


def send_message(chat_id, message):
    for start in range(0, len(message), 3900):
        response = session.post(API + "/sendMessage",
            json={"chat_id": chat_id, "text": message[start:start + 3900],
                  "disable_web_page_preview": True}, timeout=20)
        response.raise_for_status()
        if not response.json().get("ok"):
            raise RuntimeError("Telegram rejected sendMessage.")


def main():
    if not TOKEN:
        raise RuntimeError("SUPER_BOT_TOKEN is not configured.")
    if not ALLOWED_IDS:
        raise RuntimeError("SUPER_BOT_ALLOWED_USER_IDS must be configured; refusing public access.")
    offset = None
    logging.info("Punjab AI Super Bot polling worker started.")
    while True:
        try:
            params = {"timeout": 25}
            if offset is not None:
                params["offset"] = offset
            response = session.get(API + "/getUpdates", params=params, timeout=35)
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok"):
                raise RuntimeError("Telegram getUpdates returned ok=false.")
            for update in payload.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message") or {}
                sender, chat = message.get("from") or {}, message.get("chat") or {}
                text = (message.get("text") or "").strip()
                if chat.get("type") != "private" or str(sender.get("id", "")) not in ALLOWED_IDS:
                    continue
                if not text.startswith("/"):
                    continue
                command = text.split()[0].split("@")[0].lower()
                if command not in {"/start", "/help", "/status", "/health", "/research", "/calendar", "/history"}:
                    answer = "Unknown command. Send /help."
                else:
                    answer = render(command)
                send_message(chat["id"], answer)
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            logging.warning("Polling cycle failed (%s); retrying.", type(exc).__name__)
            time.sleep(5)


if __name__ == "__main__":
    main()
