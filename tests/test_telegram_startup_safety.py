import importlib
import os
import unittest
from unittest.mock import patch

import requests


class TelegramStartupSafetyTests(unittest.TestCase):
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

    def test_initial_connection_failure_is_handled_without_traceback(self):
        error = requests.ConnectionError(
            "https://api.telegram.org/bot-sensitive-token/getUpdates"
        )
        with patch.object(self.bot, "get_updates", side_effect=error), patch.object(
            self.bot.time, "sleep"
        ) as sleep, self.assertLogs(level="ERROR") as captured:
            offset = self.bot.get_initial_offset()

        self.assertIsNone(offset)
        sleep.assert_called_once_with(5)
        output = "\\n".join(captured.output)
        self.assertIn("ConnectionError", output)
        self.assertNotIn("sensitive-token", output)
        self.assertNotIn("api.telegram.org", output)

    def test_initial_offset_uses_latest_update_id(self):
        with patch.object(
            self.bot, "get_updates",
            return_value=[{"update_id": 10}, {"update_id": 14}],
        ):
            self.assertEqual(self.bot.get_initial_offset(), 15)


if __name__ == "__main__":
    unittest.main()
