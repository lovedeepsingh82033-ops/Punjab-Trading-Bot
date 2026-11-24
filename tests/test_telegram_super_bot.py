import json
import tempfile
import unittest
from pathlib import Path

from bot_state import write_bot_snapshot
from telegram_super_bot import render


class SuperBotTests(unittest.TestCase):
    def test_snapshot_schema_and_compact_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            write_bot_snapshot(scan_cutoff="2026-11-25T10:00:00Z",
                scanner_health={"status": "HEALTHY"}, dashboard={},
                intelligence={"findings": []}, calendar_context={},
                scan_results=[{"symbol": "EUR/USD", "timeframe": "H1", "_candles": "excluded"}],
                path=path)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["schema_version"], 1)
            self.assertEqual(data["observations"][0]["symbol"], "EUR/USD")
            self.assertNotIn("_candles", data["observations"][0])

    def test_help_is_available_without_snapshot(self):
        self.assertIn("/research", render("/help"))


if __name__ == "__main__":
    unittest.main()
