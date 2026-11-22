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

    def test_duplicate_timeframe_is_incomplete(self):
        results = [item("M5", "BULLISH"), item("M15", "BULLISH"),
                   item("M30", "BULLISH"), item("H1", "BULLISH"),
                   item("H1", "BULLISH")]
        decision = main.mtf_decision(results[0], results)
        self.assertFalse(decision["passed"])
        self.assertEqual(decision["cohort"], "INCOMPLETE")
        self.assertEqual(decision["reason"], "DUPLICATE_TIMEFRAMES")
        self.assertEqual(decision["duplicate_timeframes"], ["H1"])

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
            {"symbol": "EUR/USD", "timeframe": "M5", "signal_time": "2026-11-22T10:00:00Z", "outcome_method": "EXACT_3_CANDLE", "outcome_status": "CORRECT"},
            {"symbol": "EUR/USD", "timeframe": "M5", "signal_time": "2026-11-22T10:05:00Z", "outcome_method": "LEGACY", "outcome_status": "INCORRECT"},
            {"symbol": "EUR/USD", "timeframe": "M5", "signal_time": "2026-11-22T10:10:00Z", "outcome_method": "EXACT_3_CANDLE", "outcome_status": "INCORRECT"},
        ])
        summary = main.accuracy_summary(history)
        self.assertEqual(summary["completed"], 2)
        self.assertAlmostEqual(summary["win_rate"], 50.0)

    def test_blank_signal_key_is_excluded_from_accuracy(self):
        history = pd.DataFrame([{
            "symbol": "EUR/USD",
            "timeframe": "M5",
            "signal_time": "   ",
            "outcome_method": "EXACT_3_CANDLE",
            "outcome_status": "CORRECT",
        }])
        self.assertEqual(main.accuracy_summary(history)["completed"], 0)
        integrity = main.accuracy_integrity_summary(history)
        self.assertEqual(integrity["missing_keys"], 1)
        self.assertEqual(integrity["status"], "WARNING")

    def test_unreadable_history_fails_closed(self):
        with patch.object(main.os.path, "exists", return_value=True), \
             patch.object(main.pd, "read_csv", side_effect=OSError("disk error")):
            with self.assertRaises(RuntimeError):
                main.load_history()


class AccuracyIntegrityTests(unittest.TestCase):
    def make_history(self):
        rows = []
        statuses = (["CORRECT"] * 144) + (["INCORRECT"] * 167) + (["FLAT"] * 10)
        markets = ["AUD/USD", "EUR/USD", "GBP/USD", "NZD/USD", "USD/CAD", "USD/JPY", "XAU/USD"]
        timeframes = ["M5", "M15", "M30", "H1"]
        for i, status in enumerate(statuses):
            rows.append({
                "symbol": markets[i % len(markets)],
                "timeframe": timeframes[i % len(timeframes)],
                "signal_time": f"2026-11-22T{i:04d}:00Z",
                "outcome_method": "EXACT_3_CANDLE",
                "outcome_status": status,
            })
        return pd.DataFrame(rows)

    def test_report_counts_reconcile_for_321_observations(self):
        history = self.make_history()
        integrity = main.accuracy_integrity_summary(history)
        accuracy = main.accuracy_summary(history)
        self.assertEqual(integrity["status"], "OK")
        self.assertEqual(integrity["completed"], 321)
        self.assertEqual(integrity["correct"], 144)
        self.assertEqual(integrity["incorrect"], 167)
        self.assertEqual(integrity["flat"], 10)
        self.assertEqual(integrity["market_rows"], 321)
        self.assertEqual(integrity["timeframe_rows"], 321)
        self.assertAlmostEqual(accuracy["win_rate"], 46.3, places=1)

    def test_duplicate_signal_keys_raise_integrity_warning(self):
        history = self.make_history()
        history = pd.concat([history, history.iloc[[0]]], ignore_index=True)
        integrity = main.accuracy_integrity_summary(history)
        self.assertEqual(integrity["status"], "WARNING")
        self.assertEqual(integrity["duplicate_keys"], 1)
        self.assertEqual(main.accuracy_summary(history)["completed"], 320)

    def test_invalid_exact_outcome_is_reported_not_counted(self):
        history = self.make_history()
        history.loc[0, "outcome_status"] = "PENDING"
        integrity = main.accuracy_integrity_summary(history)
        self.assertEqual(integrity["completed"], 320)
        self.assertEqual(integrity["invalid_exact_status"], 1)
        self.assertEqual(integrity["status"], "WARNING")

    def test_legacy_rows_are_not_in_exact_integrity_totals(self):
        history = self.make_history()
        legacy = history.iloc[[0]].copy()
        legacy["outcome_method"] = "LEGACY"
        legacy["outcome_status"] = "INCORRECT"
        legacy["signal_time"] = "legacy-row"
        history = pd.concat([history, legacy], ignore_index=True)
        integrity = main.accuracy_integrity_summary(history)
        self.assertEqual(integrity["completed"], 321)
        self.assertEqual(integrity["incorrect"], 167)



if __name__ == "__main__":
    unittest.main()
