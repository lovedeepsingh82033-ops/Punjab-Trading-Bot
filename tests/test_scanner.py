import unittest
from unittest.mock import patch

import pandas as pd

import main


def item(tf, direction, adx=25):
    return {"symbol": "EUR/USD", "timeframe": tf, "direction": direction, "adx": adx}


class MTFTests(unittest.TestCase):
    def test_incomplete_timeframes_are_blocked(self):
        results = [item("M5", "BULLISH"), item("M15", "BULLISH"),
                   item("M30", "BULLISH")]
        decision = main.mtf_decision(results[0], results)
        self.assertFalse(decision["passed"])
        self.assertEqual(decision["cohort"], "INCOMPLETE")
        self.assertEqual(decision["missing_timeframes"], ["H1"])

    def test_three_of_four_with_h1_and_m30_strong_passes(self):
        results = [item("M5", "BULLISH"), item("M15", "BEARISH"),
                   item("M30", "BULLISH"), item("H1", "BULLISH")]
        decision = main.mtf_decision(results[0], results)
        self.assertTrue(decision["passed"])
        self.assertEqual(decision["votes"], 3)

    def test_weak_anchor_is_blocked(self):
        results = [item("M5", "BULLISH"), item("M15", "BULLISH"),
                   item("M30", "BULLISH", 15), item("H1", "BULLISH")]
        decision = main.mtf_decision(results[0], results)
        self.assertFalse(decision["passed"])
        self.assertEqual(decision["reason"], "H1_OR_M30_ADX_BELOW_20")

    def test_mtf_diagnostics_count_candidates(self):
        results = [item("M5", "BULLISH"), item("M15", "NEUTRAL"),
                   item("M30", "BULLISH"), item("H1", "BULLISH")]
        summary = main.mtf_diagnostic_summary(results)
        self.assertEqual(summary["candidates"], 3)
        self.assertEqual(summary["passed"], 3)

    def test_accuracy_summary_excludes_unverified_legacy_rows(self):
        history = pd.DataFrame([
            {"outcome_method": "EXACT_3_CANDLE", "outcome_status": "CORRECT"},
            {"outcome_method": "LEGACY", "outcome_status": "INCORRECT"},
            {"outcome_method": "EXACT_3_CANDLE", "outcome_status": "INCORRECT"},
        ])
        summary = main.accuracy_summary(history)
        self.assertEqual(summary["completed"], 2)
        self.assertAlmostEqual(summary["win_rate"], 50.0)

    def test_unreadable_history_fails_closed(self):
        with patch.object(main.os.path, "exists", return_value=True), \
             patch.object(main.pd, "read_csv", side_effect=OSError("disk error")):
            with self.assertRaises(RuntimeError):
                main.load_history()


if __name__ == "__main__":
    unittest.main()
