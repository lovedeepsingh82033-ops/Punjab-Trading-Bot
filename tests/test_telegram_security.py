import importlib
import os
import unittest
from unittest.mock import patch


class TelegramAllowlistTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "TELEGRAM_TOKEN": "test-token-not-real",
            "CHAT_ID": "123456",
        })
        self.env.start()
        import telegram_bot
        self.bot = importlib.reload(telegram_bot)

    def tearDown(self):
        self.env.stop()
        import telegram_bot
        telegram_bot.TOKEN = ""
        telegram_bot.CHAT_ID = ""

    def test_error_logging_does_not_expose_request_url_or_token(self):
        secret_url = "https://api.telegram.org/bot-sensitive-token/getUpdates"
        error = self.bot.requests.ConnectionError(secret_url)
        with self.assertLogs(level="ERROR") as captured:
            self.bot.log_safe_error("Telegram connection failed", error)
        output = "\\n".join(captured.output)
        self.assertIn("ConnectionError", output)
        self.assertNotIn("sensitive-token", output)
        self.assertNotIn("api.telegram.org", output)

    def test_matching_chat_is_authorized(self):
        self.assertTrue(self.bot.is_authorized_chat(123456))

    def test_non_matching_chat_is_rejected(self):
        self.assertFalse(self.bot.is_authorized_chat(999999))

    def test_missing_allowlist_fails_closed(self):
        self.assertFalse(self.bot.is_authorized_chat(123456, ""))

    def test_unauthorized_message_is_ignored(self):
        with patch.object(self.bot, "send_message") as send:
            self.bot.handle_message({
                "chat": {"id": 999999},
                "text": "/status",
            })
        send.assert_not_called()

    def test_authorized_status_command_replies(self):
        with patch.object(self.bot, "send_message") as send:
            self.bot.handle_message({
                "chat": {"id": 123456},
                "text": "/status",
            })
        send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
