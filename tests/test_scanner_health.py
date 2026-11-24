import unittest

from scanner_health import scanner_health_context


class ScannerHealthTests(unittest.TestCase):
    def test_complete_scan_is_healthy(self):
        result = scanner_health_context(28, 28, 0)
        self.assertEqual(result["status"], "HEALTHY")
        self.assertEqual(result["completion_pct"], 100.0)

    def test_incomplete_scan_is_partial(self):
        result = scanner_health_context(28, 21, 0)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["completion_pct"], 75.0)

    def test_processing_error_degrades_scan(self):
        result = scanner_health_context(28, 27, 1)
        self.assertEqual(result["status"], "DEGRADED")

    def test_api_rate_limit_degrades_scan(self):
        result = scanner_health_context(28, 14, 0, api_rate_limited=True)
        self.assertEqual(result["status"], "DEGRADED")

    def test_zero_completed_analyses_reports_no_data(self):
        result = scanner_health_context(28, 0, 0)
        self.assertEqual(result["status"], "NO DATA")

    def test_zero_expected_analyses_reports_no_targets(self):
        result = scanner_health_context(0, 0, 0)
        self.assertEqual(result["status"], "NO TARGETS")
        self.assertEqual(result["completion_pct"], 0.0)

    def test_notification_deliveries_are_reported_as_success_counts(self):
        result = scanner_health_context(
            28, 28, 0, telegram_deliveries=3, discord_deliveries=2
        )
        self.assertEqual(result["telegram_deliveries"], 3)
        self.assertEqual(result["discord_deliveries"], 2)

    def test_invalid_counters_are_rejected(self):
        with self.assertRaises(ValueError):
            scanner_health_context(28, -1, 0)
        with self.assertRaises(ValueError):
            scanner_health_context(28, 29, 0)
        with self.assertRaises(ValueError):
            scanner_health_context(True, 1, 0)

    def test_invalid_rate_limit_flag_is_rejected(self):
        with self.assertRaises(ValueError):
            scanner_health_context(28, 28, 0, api_rate_limited=1)


if __name__ == "__main__":
    unittest.main()
