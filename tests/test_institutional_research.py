import unittest
import numpy as np
import pandas as pd

from institutional_research import (
    quantitative_research_context,
    risk_management_context,
    algorithmic_system_context,
    validation_context,
)


class InstitutionalResearchTests(unittest.TestCase):
    def frame(self):
        close = np.array([100.0, 102.0, 101.0, 104.0, 103.0, 105.0])
        return pd.DataFrame({
            "datetime": pd.date_range("2026-01-01", periods=len(close), freq="h", tz="UTC"),
            "open": close - 0.2, "high": close + 1.0, "low": close - 1.0, "close": close,
            "ema9": close, "ema21": close - 0.1, "ema50": close - 0.2,
            "rsi": 55.0, "macd": 0.2, "adx": 25.0, "atr": 1.0,
        })

    def test_quantitative_statistics_are_finite(self):
        result = quantitative_research_context(self.frame())
        self.assertEqual(result["sample_count"], 5)
        self.assertTrue(np.isfinite(result["return_volatility_pct"]))

    def test_historical_drawdown_is_descriptive(self):
        result = risk_management_context(self.frame())
        self.assertGreater(result["max_drawdown_pct"], 0)
        self.assertIn("not account or portfolio risk", result["scope"])

    def test_algorithmic_integrity_passes_valid_data(self):
        self.assertEqual(algorithmic_system_context(self.frame())["status"], "PASS")

    def test_algorithmic_integrity_flags_duplicate_times_by_name(self):
        df = self.frame()
        df.loc[1, "datetime"] = df.loc[0, "datetime"]
        result = algorithmic_system_context(df)
        self.assertEqual(result["status"], "WARNING")
        self.assertIn("Timestamps unique", result["failed_checks"])

    def test_algorithmic_integrity_flags_non_finite_indicator_by_name(self):
        df = self.frame()
        df.loc[2, "rsi"] = np.nan
        result = algorithmic_system_context(df)
        self.assertEqual(result["status"], "WARNING")
        self.assertIn("EMA/RSI/MACD/ADX/ATR values finite", result["failed_checks"])

    def test_algorithmic_integrity_flags_invalid_ohlc_by_name(self):
        df = self.frame()
        df.loc[2, "high"] = df.loc[2, "low"] - 1
        result = algorithmic_system_context(df)
        self.assertEqual(result["status"], "WARNING")
        self.assertIn("OHLC values positive and internally consistent", result["failed_checks"])

    def test_validation_requires_minimum_holdout_sample(self):
        self.assertEqual(validation_context({"samples": 5})["status"], "INSUFFICIENT SAMPLE")

    def test_validation_accepts_documented_holdout_metadata(self):
        result = validation_context({
            "samples": 35,
            "overlap_policy": "NON_OVERLAPPING_HORIZON",
            "entry_policy": "NEXT_CANDLE_OPEN_TO_HORIZON_CLOSE",
        })
        self.assertEqual(result["status"], "METHODOLOGY CHECK PASS")

    def test_invalid_inputs_rejected(self):
        with self.assertRaises(ValueError):
            quantitative_research_context(pd.DataFrame({"close": [1]}))
        with self.assertRaises(ValueError):
            validation_context({"samples": -1})


if __name__ == "__main__":
    unittest.main()
