import json
import os
import time
import logging
from pathlib import Path

import requests

from snapshot_bridge import download_snapshot

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
STATE_PATH = Path(os.getenv("BOT_STATE_PATH", "bot_state.json"))

if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is missing.")

API_URL = f"https://api.telegram.org/bot{TOKEN}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


def log_safe_error(context, exc):
    """Log only the exception type; request URLs may contain the bot token."""
    logging.error("%s: %s", context, type(exc).__name__)


def get_updates(offset=None):
    params = {
        "timeout": 25,
        "allowed_updates": ["message"]
    }

    if offset is not None:
        params["offset"] = offset

    response = requests.get(
        f"{API_URL}/getUpdates",
        params=params,
        timeout=35
    )
    response.raise_for_status()

    data = response.json()

    if not data.get("ok"):
        raise RuntimeError("Telegram API returned an error.")

    return data.get("result", [])


def send_message(chat_id, message):
    response = requests.post(
        f"{API_URL}/sendMessage",
        data={
            "chat_id": chat_id,
            "text": message
        },
        timeout=20
    )
    response.raise_for_status()


def is_authorized_chat(chat_id, allowed_chat_id=CHAT_ID):
    """Fail closed unless the incoming chat matches the configured allowlist."""
    return bool(allowed_chat_id) and str(chat_id) == str(allowed_chat_id)


def load_scanner_state():
    """Load the latest private scanner snapshot without starting another poller."""
    try:
        shared_state = download_snapshot()
        if shared_state is not None:
            return shared_state
    except (requests.RequestException, ValueError) as exc:
        logging.warning("Shared scanner snapshot unavailable (%s).", type(exc).__name__)

    try:
        with STATE_PATH.open(encoding="utf-8") as stream:
            state = json.load(stream)
        return state if isinstance(state, dict) and state.get("schema_version") == 1 else None
    except (OSError, ValueError, TypeError):
        return None


def compact(value, limit=2400):
    rendered = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return rendered if len(rendered) <= limit else rendered[:limit - 20] + "\\n…(trimmed)"


def render_research_command(command):
    if command in ("/start", "/help"):
        return (
            "🤖 Punjab AI Super Bot\\n\\n"
            "/status — latest scan\\n/health — scanner health\\n"
            "/research — Intelligence Hub\\n/calendar — economic calendar\\n"
            "/history — latest observations\\n/help — commands\\n\\n"
            "Research-only. No orders are placed."
        )

    state = load_scanner_state()
    if state is None:
        return (
            "Scanner snapshot is not available yet. "
            "The scanner must complete a run and publish its BOT_STATE_PATH snapshot."
        )

    if command == "/status":
        health = state.get("scanner_health", {})
        return (
            f"📊 Punjab Scanner Status\\nLast snapshot: {state.get('generated_at', 'unknown')}"
            f"\\nObservations: {state.get('observation_count', 0)}"
            f"\\nHealth: {health.get('status', 'unknown')}"
        )
    if command == "/health":
        return "🩺 Scanner Health\\n" + compact(state.get("scanner_health", {}))
    if command == "/research":
        return "🧠 Intelligence Hub\\n" + compact(state.get("intelligence", {}))
    if command == "/calendar":
        return "🗓 Economic Calendar\\n" + compact(state.get("calendar", {}))
    if command == "/history":
        return "📚 Latest Research Observations\\n" + compact(state.get("observations", []))
    return "Unknown command. Send /help."


def handle_message(message):
    chat = message.get("chat", {})
    chat_id = chat.get("id")

    if not is_authorized_chat(chat_id):
        return

    text = message.get("text", "").strip()
    command = text.split()[0].split("@")[0].lower() if text else ""

    if command in {"/start", "/help"}:
        send_message(chat_id, render_research_command(command))
    elif command == "/status":
        send_message(
            chat_id,
            "Bot process: Running\\nTelegram connection: Working\\n\\n"
            + render_research_command(command)
        )
    elif command in {"/health", "/research", "/calendar", "/history"}:
        send_message(chat_id, render_research_command(command))
    elif command.startswith("/"):
        send_message(chat_id, "Unknown command. Send /help.")


def get_initial_offset():
    """Fetch the initial update offset without exposing token-bearing request URLs."""
    try:
        updates = get_updates()
    except requests.RequestException as exc:
        log_safe_error("Telegram startup connection failed", exc)
        time.sleep(5)
        return None

    return max(
        (item["update_id"] for item in updates),
        default=0
    ) + 1


def main():
    logging.info("Telegram command bot started.")
    offset = get_initial_offset()

    while True:
        try:
            updates = get_updates(offset)

            for update in updates:
                offset = update["update_id"] + 1

                message = update.get("message")
                if message:
                    handle_message(message)

        except requests.RequestException as exc:
            log_safe_error("Telegram connection failed", exc)
            time.sleep(5)

        except Exception as exc:
            log_safe_error("Unexpected bot error", exc)
            time.sleep(5)


if __name__ == "__main__":
    main()
