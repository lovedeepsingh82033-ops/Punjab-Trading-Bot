import unittest

import numpy as np
import pandas as pd

from advanced_research import (
    anomaly_research_context,
    cross_market_correlation_context,
)


class AdvancedResearchTests(unittest.TestCase):
    def test_anomaly_context_flags_large_outlier(self):
        close = [100.0]
        for _ in range(40):
            close.append(close[-1] * 1.001)
        close.append(close[-1] * 1.08)
        frame = pd.DataFrame({"close": close})
        result = anomaly_research_context(frame, window=40, minimum_samples=30)
        self.assertEqual(result["status"], "UNUSUAL OBSERVATION")
        self.assertGreater(result["latest_abs_return_pct"], 5.0)

    def test_anomaly_context_reports_insufficient_data(self):
        result = anomaly_research_context(
            pd.DataFrame({"close": [100.0, 101.0, 102.0]}),
            minimum_samples=10,
        )
        self.assertEqual(result["status"], "INSUFFICIENT DATA")

    def test_correlation_finds_identical_return_series(self):
        dates = pd.date_range("2026-01-01", periods=50, freq="h", tz="UTC")
        close = 100 * np.cumprod(1 + np.linspace(-0.002, 0.003, 50))
        frame_a = pd.DataFrame({"datetime": dates, "close": close})
        frame_b = pd.DataFrame({"datetime": dates, "close": close * 2})
        result = cross_market_correlation_context(
            {"AAA": frame_a, "BBB": frame_b},
            minimum_samples=30,
        )
        self.assertEqual(result["pairs_calculated"], 1)
        self.assertAlmostEqual(result["pairs"][0]["correlation"], 1.0)

    def test_correlation_skips_insufficient_overlap(self):
        dates = pd.date_range("2026-01-01", periods=10, freq="h", tz="UTC")
        frame = pd.DataFrame({"datetime": dates, "close": np.arange(10) + 100})
        result = cross_market_correlation_context(
            {"AAA": frame, "BBB": frame},
            minimum_samples=30,
        )
        self.assertEqual(result["pairs"], [])

    def test_invalid_parameters_rejected(self):
        with self.assertRaises(ValueError):
            anomaly_research_context(pd.DataFrame({"close": [1, 2]}), window=1)
        with self.assertRaises(ValueError):
            cross_market_correlation_context({}, minimum_samples=1)


if __name__ == "__main__":
    unittest.main()
