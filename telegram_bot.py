
import os
import time
import logging
import requests

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()

if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is missing.")

API_URL = f"https://api.telegram.org/bot{TOKEN}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

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


def handle_message(message):
    chat = message.get("chat", {})
    chat_id = chat.get("id")

    if not is_authorized_chat(chat_id):
        return

    command = message.get("text", "").strip().split("@")[0].lower()

    if command == "/start":
        send_message(
            chat_id,
            "Welcome to Punjab Bot!\n\n"
            "Bot is ready to receive commands.\n"
            "Use /help to see available commands."
        )

    elif command == "/help":
        send_message(
            chat_id,
            "Available commands:\n\n"
            "/start - Start the bot\n"
            "/help - Show help\n"
            "/status - Check bot status"
        )

    elif command == "/status":
        send_message(
            chat_id,
            "Bot process: Running\n"
            "Telegram connection: Working"
        )


def main():
    logging.info("Telegram command bot started.")

    updates = get_updates()
    offset = max(
        (item["update_id"] for item in updates),
        default=0
    ) + 1

    while True:
        try:
            updates = get_updates(offset)

            for update in updates:
                offset = update["update_id"] + 1

                message = update.get("message")
                if message:
                    handle_message(message)

        except requests.RequestException:
            logging.exception("Telegram connection error.")
            time.sleep(5)

        except Exception:
            logging.exception("Unexpected bot error.")
            time.sleep(5)


if __name__ == "__main__":
    main()
