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
