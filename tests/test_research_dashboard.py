import unittest

from research_dashboard import advanced_research_dashboard, format_research_dashboard


class ResearchDashboardTests(unittest.TestCase):
    def test_dashboard_aggregates_scan_context(self):
        results = [
            {"symbol": "EUR/USD", "timeframe": "H1",
             "market_regime": {"label": "TRENDING UP"},
             "volatility": {"regime": "NORMAL"},
             "data_quality": {"status": "PASS"},
             "anomaly_research": {"status": "WITHIN BASELINE"}},
            {"symbol": "XAU/USD", "timeframe": "M15",
             "market_regime": {"label": "RANGE"},
             "volatility": {"regime": "HIGH"},
             "data_quality": {"status": "WARNING"},
             "anomaly_research": {"status": "UNUSUAL OBSERVATION"}},
        ]
        dashboard = advanced_research_dashboard(
            results, {"H1": {"pairs": [{
                "symbol_a": "EUR/USD", "symbol_b": "XAU/USD",
                "correlation": 0.42, "samples": 35,
            }]}},
            calendar_context={"status": "EVENTS FOUND", "count": 1,
                              "events": [{"event_time_utc": "2026-11-25T13:00:00Z",
                                          "currency": "USD", "impact": "HIGH",
                                          "event": "Example", "source": "Official"}]},
            scanner_health={"status": "HEALTHY", "completion_pct": 100},
        )
        self.assertEqual(dashboard["analyses"], 2)
        self.assertEqual(dashboard["anomalies"], 1)
        self.assertIn("TRENDING UP: 1", dashboard["regimes"])
        self.assertEqual(dashboard["calendar_count"], 1)
        report = format_research_dashboard(dashboard)
        self.assertIn("Advanced Research Dashboard", report)
        self.assertIn("EUR/USD/XAU/USD", report)

    def test_empty_dashboard_is_safe(self):
        dashboard = advanced_research_dashboard([], {})
        report = format_research_dashboard(dashboard)
        self.assertEqual(dashboard["analyses"], 0)
        self.assertIn("No data", report)


if __name__ == "__main__":
    unittest.main()
