import unittest
from unittest.mock import patch

import requests

import main


class RequestLogRedactionTests(unittest.TestCase):
    def assert_log_is_redacted(self, logger_name, call):
        with self.assertLogs(logger_name, level="ERROR") as captured:
            self.assertFalse(call())

        output = "\n".join(captured.output)
        self.assertNotIn("TEST_BOT_TOKEN", output)
        self.assertNotIn("discord-test-token", output)
        self.assertNotIn("discord.com", output)
        self.assertNotIn("secret-query-value", output)
        self.assertNotIn("api.telegram.org", output)
        self.assertNotIn("private response body", output)
        self.assertIn("RequestException", output)

    def test_telegram_request_error_does_not_log_url_or_response_body(self):
        error = requests.RequestException(
            "https://api.telegram.org/botTEST_BOT_TOKEN/sendMessage"
            "?key=secret-query-value"
        )
        response = requests.Response()
        response.status_code = 400
        response._content = b"private response body"
        error.response = response

        with patch.object(main, "TOKEN", "TEST_BOT_TOKEN"), patch.object(
            main, "CHAT_ID", "123"
        ), patch.object(main.session, "post", side_effect=error):
            self.assert_log_is_redacted(
                "root",
                lambda: main.telegram("test message"),
            )

    def test_telegram_api_error_description_is_not_logged(self):
        secret_description = "sensitive server detail with token-like-value"
        with patch.object(main, "TOKEN", "TEST_BOT_TOKEN"), patch.object(
            main, "CHAT_ID", "123"
        ), patch.object(
            main.session, "post",
            return_value=type("Response", (), {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"ok": False, "description": secret_description},
            })(),
        ), self.assertLogs("root", level="ERROR") as captured:
            self.assertFalse(main.telegram("test message"))

        output = "\\n".join(captured.output)
        self.assertIn("Telegram API rejected the message", output)
        self.assertNotIn(secret_description, output)
        self.assertNotIn("TEST_BOT_TOKEN", output)

    def test_discord_request_error_does_not_log_sensitive_details(self):
        error = requests.RequestException(
            "https://discord.com/api/v10/channels/456/messages"
            "?key=secret-query-value"
        )
        response = requests.Response()
        response.status_code = 400
        response._content = b"private response body"
        error.response = response

        with patch.object(main, "DISCORD_TOKEN", "discord-test-token"), patch.object(
            main, "DISCORD_CHANNEL_ID", "456"
        ), patch.object(main, "DISCORD_ACCESS_BLOCKED", False), patch.object(
            main.session, "post", side_effect=error
        ):
            self.assert_log_is_redacted(
                "root",
                lambda: main.discord("test message"),
            )


if __name__ == "__main__":
    unittest.main()
