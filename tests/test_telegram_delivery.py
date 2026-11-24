import unittest
from unittest.mock import patch

import main


class TelegramDeliveryTests(unittest.TestCase):
    def test_html_report_becomes_readable_plain_text(self):
        report = '<b>Scanner</b>\n<a href="https://example.com">Open report</a>'
        result = main.telegram_plain_text(report)
        self.assertIn("Scanner", result)
        self.assertIn("Open report (https://example.com)", result)
        self.assertNotIn("<b>", result)
        self.assertNotIn("<a ", result)

    def test_long_messages_are_split_under_telegram_limit(self):
        chunks = main.split_telegram_text(("line\n" * 1200), limit=3900)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 3900 for chunk in chunks))
        self.assertEqual("".join(chunks).replace("\n", ""), ("line\n" * 1200).replace("\n", ""))

    def test_telegram_sends_plain_text_without_html_parse_mode(self):
        response = type("Response", (), {
            "raise_for_status": lambda self: None,
            "json": lambda self: {"ok": True},
        })()
        with patch.object(main, "TOKEN", "test-token"), patch.object(
            main, "CHAT_ID", "123"
        ), patch.object(main.session, "post", return_value=response) as post:
            self.assertTrue(main.telegram("<b>Scanner</b>"))
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["text"], "Scanner")
        self.assertNotIn("parse_mode", payload)


if __name__ == "__main__":
    unittest.main()
