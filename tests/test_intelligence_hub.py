import unittest

from intelligence_hub import build_intelligence_hub, format_intelligence_hub


class IntelligenceHubTests(unittest.TestCase):
    def test_combines_health_quality_calendar_and_research(self):
        scan_results = [
            {
                "data_quality": {"status": "FAIL"},
                "market_regime": {"label": "RANGE / WEAK TREND"},
                "volatility": {"regime": "HIGH"},
                "anomaly_research": {"status": "UNUSUAL OBSERVATION"},
                "walk_forward": {"status": "INSUFFICIENT SAMPLE"},
            },
            {
                "data_quality": {"status": "WARNING"},
                "market_regime": {"label": "TRANSITION / MIXED"},
                "volatility": {"regime": "NORMAL"},
            },
        ]
        report = build_intelligence_hub(
            {"correlations": ["H1: Insufficient aligned history"],
             "calendar_status": "NOT CONFIGURED", "calendar_count": 0},
            scan_results,
            {"status": "DEGRADED", "completion_pct": 50.0},
            {"status": "NOT CONFIGURED", "count": 0},
        )
        self.assertEqual(report["analyses"], 2)
        self.assertEqual(report["anomaly_count"], 1)
        self.assertEqual(report["quality_counts"], {"FAIL": 1, "WARNING": 1})
        self.assertTrue(any("Scanner operations" in item for item in report["findings"]))
        self.assertTrue(any("calendar" in item.lower() for item in report["findings"]))
        rendered = format_intelligence_hub(report)
        self.assertIn("Punjab AI Intelligence Hub", rendered)
        self.assertIn("no forecasts", rendered.lower())

    def test_healthy_empty_input_does_not_crash(self):
        report = build_intelligence_hub(
            {"correlations": ["No correlation data"]}, [],
            {"status": "HEALTHY", "completion_pct": 100.0},
            {"status": "EVENTS FOUND", "count": 1},
        )
        self.assertEqual(report["analyses"], 0)
        self.assertEqual(report["anomaly_count"], 0)
        self.assertTrue(report["findings"])
        self.assertTrue(report["recommendations"])

    def test_missing_optional_sections_are_safe(self):
        report = build_intelligence_hub({}, [], {})
        self.assertEqual(report["scanner_health"], "UNKNOWN")
        self.assertEqual(report["calendar_status"], "UNKNOWN")
        self.assertIn("Punjab AI Intelligence Hub", format_intelligence_hub(report))


if __name__ == "__main__":
    unittest.main()
