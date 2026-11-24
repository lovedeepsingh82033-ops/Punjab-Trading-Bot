import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from economic_calendar import economic_calendar_context


class EconomicCalendarTests(unittest.TestCase):
    def write_calendar(self, rows):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "calendar.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=[
                "event_time_utc", "currency", "impact", "event", "source"
            ])
            writer.writeheader()
            writer.writerows(rows)
        return str(path)

    def test_filters_by_currency_and_time_window(self):
        path = self.write_calendar([
            {"event_time_utc": "2026-11-25T13:00:00Z", "currency": "USD", "impact": "HIGH", "event": "Example release", "source": "Official source"},
            {"event_time_utc": "2026-11-25T13:00:00Z", "currency": "EUR", "impact": "LOW", "event": "Other release", "source": "Official source"},
            {"event_time_utc": "2026-11-27T13:00:00Z", "currency": "USD", "impact": "HIGH", "event": "Outside window", "source": "Official source"},
        ])
        result = economic_calendar_context(
            path, as_of=datetime(2026, 11, 25, 12, tzinfo=timezone.utc),
            symbols=["EUR/USD"], lookahead_hours=24,
        )
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["events"][0]["currency"], "USD")
        self.assertEqual(result["high_impact_count"], 1)

    def test_invalid_rows_are_skipped_and_counted(self):
        path = self.write_calendar([
            {"event_time_utc": "not-a-date", "currency": "USD", "impact": "HIGH", "event": "Bad row", "source": "Source"}
        ])
        result = economic_calendar_context(
            path, as_of=datetime(2026, 11, 25, 12, tzinfo=timezone.utc),
            symbols=["USD/JPY"],
        )
        self.assertEqual(result["invalid_rows"], 1)
        self.assertEqual(result["count"], 0)

    def test_missing_file_is_not_configured(self):
        result = economic_calendar_context(
            "/path/that/does/not/exist.csv",
            as_of=datetime(2026, 11, 25, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(result["status"], "NOT CONFIGURED")

    def test_naive_as_of_is_rejected(self):
        with self.assertRaises(ValueError):
            economic_calendar_context(
                "unused.csv", as_of=datetime(2026, 11, 25, 12)
            )


if __name__ == "__main__":
    unittest.main()
