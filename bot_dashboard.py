import os
import time
import logging
import requests

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()

if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is missing")

API = f"https://api.telegram.org/bot{TOKEN}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


def send_message(chat_id, text):
    response = requests.post(
        f"{API}/sendMessage",
        data={
            "chat_id": chat_id,
            "text": text
        },
        timeout=20
    )
    response.raise_for_status()


def handle_message(message):
    chat_id = str(message.get("chat", {}).get("id", ""))

    if not chat_id:
        return

    if CHAT_ID and chat_id != CHAT_ID:
        return

    text = message.get("text", "").strip().lower()
    command = text.split("@")[0].split()[0] if text else ""

    if command == "/start":
        send_message(
            chat_id,
            "Welcome to Punjab Bot!\n\n"
            "Your Telegram dashboard is ready.\n\n"
            "Use /help to see commands."
        )

    elif command == "/help":
        send_message(
            chat_id,
            "PUNJAB BOT MENU\n\n"
            "/start - Start dashboard\n"
            "/status - Bot status\n"
            "/report - Scan report information\n"
            "/signals - Market information\n"
            "/help - Help menu"
        )

    elif command == "/status":
        send_message(
            chat_id,
            "PUNJAB BOT STATUS\n\n"
            "Command service: Running\n"
            "Telegram API: Connected\n"
            "Dashboard: Active"
        )

    elif command == "/report":
        send_message(
            chat_id,
            "PUNJAB SCAN REPORT\n\n"
            "This dashboard does not yet read scan history.\n"
            "No new report is available here."
        )

    elif command == "/signals":
        send_message(
            chat_id,
            "MARKET INFORMATION\n\n"
            "Educational market information only.\n"
            "No BUY/SELL instructions or trading advice."
        )


def main():
    logging.info("Punjab dashboard started")
    offset = None

    while True:
        try:
            params = {
                "timeout": 25,
                "allowed_updates": ["message"]
            }

            if offset is not None:
                params["offset"] = offset

            response = requests.get(
                f"{API}/getUpdates",
                params=params,
                timeout=35
            )
            response.raise_for_status()

            data = response.json()

            if not data.get("ok"):
                raise RuntimeError("Telegram API error")

            for update in data.get("result", []):
                offset = update["update_id"] + 1

                message = update.get("message")
                if message:
                    handle_message(message)

        except Exception:
            logging.exception("Dashboard error")
            time.sleep(5)


if __name__ == "__main__":
    main()
