import unittest

from quant_intelligence import build_quant_intelligence, format_quant_intelligence


class QuantIntelligenceTests(unittest.TestCase):
    def test_aggregates_existing_diagnostics(self):
        report = build_quant_intelligence([
            {
                "data_quality": {"status": "FAIL"},
                "market_regime": {"label": "RANGE"},
                "volatility": {"regime": "HIGH"},
                "algorithmic_system": {"status": "WARNING"},
                "validation": {"status": "INSUFFICIENT SAMPLE"},
                "walk_forward": {"status": "COMPLETED"},
                "risk_context": {"max_drawdown_pct": 4.25},
                "anomaly_research": {"status": "UNUSUAL OBSERVATION"},
            },
            {
                "data_quality": {"status": "PASS"},
                "market_regime": {"label": "TRENDING UP"},
                "volatility": {"regime": "NORMAL"},
                "algorithmic_system": {"status": "PASS"},
                "validation": {"status": "METHODOLOGY CHECK PASS"},
                "walk_forward": {"status": "INSUFFICIENT SAMPLE"},
                "risk_context": {"max_drawdown_pct": 2.0},
            },
        ])
        self.assertEqual(report["markets_reviewed"], 2)
        self.assertEqual(report["data_quality"], {"FAIL": 1, "PASS": 1})
        self.assertEqual(report["worst_historical_drawdown_pct"], 4.25)
        self.assertEqual(report["unusual_observations"], 1)
        self.assertTrue(any("Data-quality failures" in x for x in report["findings"]))
        rendered = format_quant_intelligence(report)
        self.assertIn("Punjab Quant Intelligence", rendered)
        self.assertIn("not a forecast", rendered.lower())
        self.assertNotIn("BUY", rendered)
        self.assertNotIn("SELL", rendered)

    def test_empty_input_is_safe(self):
        report = build_quant_intelligence([])
        self.assertEqual(report["markets_reviewed"], 0)
        self.assertIsNone(report["worst_historical_drawdown_pct"])
        self.assertTrue(report["findings"])
        self.assertIn("No data", format_quant_intelligence(report))


if __name__ == "__main__":
    unittest.main()
