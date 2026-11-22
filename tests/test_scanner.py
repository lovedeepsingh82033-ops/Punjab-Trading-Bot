import unittest
from unittest.mock import patch

import pandas as pd

import main


def item(tf, direction, adx=25):
    candle_open = {
        "M5": "2026-11-22T09:55:00Z",
        "M15": "2026-11-22T09:45:00Z",
        "M30": "2026-11-22T09:30:00Z",
        "H1": "2026-11-22T09:00:00Z",
    }.get(tf, "2026-11-22T09:55:00Z")
    return {
        "symbol": "EUR/USD", "timeframe": tf,
        "direction": direction, "adx": adx,
        "signal_time": candle_open,
        "scan_cutoff": "2026-11-22T10:00:00Z",
    }


class CompletedCandleCutoffTests(unittest.TestCase):
    def test_shared_cutoff_excludes_candles_not_yet_closed(self):
        frame = pd.DataFrame({
            "datetime": pd.to_datetime([
                "2026-11-22T10:00:00Z",
                "2026-11-22T10:05:00Z",
                "2026-11-22T10:10:00Z",
            ], utc=True),
            "close": [1.0, 1.1, 1.2],
        })
        result = main.filter_completed_candles(
            frame, "5min", "2026-11-22T10:10:00Z"
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(
            result["datetime"].iloc[-1],
            pd.Timestamp("2026-11-22T10:05:00Z"),
        )

    def test_cutoff_is_normalized_to_utc(self):
        frame = pd.DataFrame({
            "datetime": pd.to_datetime(["2026-11-22T10:00:00Z"], utc=True),
            "close": [1.0],
        })
        result = main.filter_completed_candles(
            frame, "5min", "2026-11-22T12:05:00+02:00"
        )
        self.assertEqual(len(result), 1)

    def test_unknown_interval_is_rejected(self):
        frame = pd.DataFrame({
            "datetime": pd.to_datetime(["2026-11-22T10:00:00Z"], utc=True),
            "close": [1.0],
        })
        with self.assertRaises(ValueError):
            main.filter_completed_candles(
                frame, "2hour", "2026-11-22T12:00:00Z"
            )


class MTFFreshnessTests(unittest.TestCase):
    def cohort(self, cutoff="2026-11-22T10:00:00Z"):
        candles = {
            "M5": "2026-11-22T09:55:00Z",
            "M15": "2026-11-22T09:45:00Z",
            "M30": "2026-11-22T09:30:00Z",
            "H1": "2026-11-22T09:00:00Z",
        }
        results = []
        for timeframe, candle_time in candles.items():
            row = item(timeframe, "BULLISH")
            row["signal_time"] = candle_time
            row["scan_cutoff"] = cutoff
            results.append(row)
        return results

    def test_recent_closed_candles_can_pass(self):
        results = self.cohort()
        decision = main.mtf_decision(results[0], results)
        self.assertTrue(decision["passed"])
        self.assertEqual(decision["stale_timeframes"], [])

    def test_old_candle_blocks_cohort_as_incomplete(self):
        results = self.cohort()
        results[3]["signal_time"] = "2026-11-22T08:00:00Z"
        decision = main.mtf_decision(results[0], results)
        self.assertFalse(decision["passed"])
        self.assertEqual(decision["cohort"], "INCOMPLETE")
        self.assertEqual(decision["reason"], "STALE_OR_MISSING_CANDLE_TIMING")
        self.assertEqual(decision["stale_timeframes"], ["H1"])

    def test_missing_timing_metadata_fails_closed(self):
        results = self.cohort()
        del results[1]["scan_cutoff"]
        decision = main.mtf_decision(results[0], results)
        self.assertFalse(decision["passed"])
        self.assertEqual(decision["cohort"], "INCOMPLETE")
        self.assertIn("M15", decision["stale_timeframes"])


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

    def test_mixed_symbols_cannot_complete_an_mtf_cohort(self):
        results = [item("M5", "BULLISH"), item("M15", "BULLISH"),
                   item("M30", "BULLISH"), item("H1", "BULLISH")]
        foreign = item("H1", "BULLISH")
        foreign["symbol"] = "GBP/USD"
        decision = main.mtf_decision(results[0], results + [foreign])
        self.assertFalse(decision["passed"])
        self.assertEqual(decision["cohort"], "INCOMPLETE")
        self.assertEqual(decision["reason"], "MIXED_SYMBOLS")
        self.assertEqual(decision["mixed_symbols"], ["GBP/USD"])

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

    def test_mtf_diagnostics_uses_all_timeframes_not_only_alerts(self):
        results = [item("M5", "BULLISH"), item("M15", "NEUTRAL"),
                   item("M30", "BULLISH"), item("H1", "BULLISH")]
        summary = main.mtf_diagnostic_summary(results)
        self.assertEqual(summary["candidates"], 3)
        self.assertEqual(summary["passed"], 3)
        self.assertEqual(summary["incomplete"], 0)

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


class MTFCohortHistoryTests(unittest.TestCase):
    def make_history_row(self, cohort, signal_time, status="PENDING",
                         method="", symbol="EUR/USD", timeframe="M5"):
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "signal_time": signal_time,
            "direction": "BULLISH",
            "mtf_cohort": cohort,
            "outcome_method": method,
            "outcome_status": status,
        }

    def test_first_mtf_cohort_assignment_is_frozen(self):
        result = item("M5", "BULLISH")
        history = pd.DataFrame([{
            "symbol": "EUR/USD",
            "timeframe": "M5",
            "signal_time": result["signal_time"],
            "mtf_cohort": "UNASSESSED",
        }])
        first_scan = [
            item("M5", "BULLISH"), item("M15", "BULLISH"),
            item("M30", "BULLISH"), item("H1", "BULLISH"),
        ]
        history = main.label_mtf_cohorts(first_scan, history)
        self.assertEqual(history.loc[0, "mtf_cohort"], "PASSED")

        later_scan = [
            item("M5", "BULLISH"), item("M15", "BEARISH"),
            item("M30", "BEARISH"), item("H1", "BEARISH"),
        ]
        history = main.label_mtf_cohorts(later_scan, history)
        self.assertEqual(history.loc[0, "mtf_cohort"], "PASSED")

    def test_mtf_accuracy_counts_only_unique_matured_exact_rows(self):
        rows = [
            self.make_history_row("PASSED", "2026-11-22T10:00:00Z",
                                  "CORRECT", "EXACT_3_CANDLE"),
            self.make_history_row("PASSED", "2026-11-22T10:05:00Z",
                                  "INCORRECT", "EXACT_3_CANDLE"),
            self.make_history_row("PASSED", "2026-11-22T10:10:00Z",
                                  "FLAT", "EXACT_3_CANDLE"),
            self.make_history_row("BLOCKED", "2026-11-22T10:15:00Z",
                                  "INCORRECT", "EXACT_3_CANDLE"),
            self.make_history_row("BLOCKED", "2026-11-22T10:20:00Z",
                                  "CORRECT", "LEGACY"),
            self.make_history_row("PASSED", "2026-11-22T10:25:00Z",
                                  "PENDING", ""),
            self.make_history_row("PASSED", "2026-11-22T10:30:00Z",
                                  "CORRECT", "EXACT_3_CANDLE"),
            self.make_history_row("PASSED", "2026-11-22T10:30:00Z",
                                  "INCORRECT", "EXACT_3_CANDLE"),
        ]
        summary = main.mtf_accuracy_summary(pd.DataFrame(rows))
        self.assertEqual(
            summary["PASSED"],
            "PASSED: 3 matured; 1 correct / 1 incorrect / 1 flat; hit rate 50.0%",
        )
        self.assertEqual(
            summary["BLOCKED"],
            "BLOCKED: 1 matured; 0 correct / 1 incorrect / 0 flat; hit rate 0.0%",
        )

    def test_legacy_or_unassigned_cohorts_do_not_enter_mtf_accuracy(self):
        rows = [
            self.make_history_row("LEGACY_UNKNOWN", "2026-11-22T10:00:00Z",
                                  "CORRECT", "EXACT_3_CANDLE"),
            self.make_history_row("UNASSESSED", "2026-11-22T10:05:00Z",
                                  "INCORRECT", "EXACT_3_CANDLE"),
        ]
        summary = main.mtf_accuracy_summary(pd.DataFrame(rows))
        self.assertEqual(summary["PASSED"],
                         "PASSED: 0 matured; 0 correct / 0 incorrect / 0 flat; hit rate not available")
        self.assertEqual(summary["BLOCKED"],
                         "BLOCKED: 0 matured; 0 correct / 0 incorrect / 0 flat; hit rate not available")



if __name__ == "__main__":
    unittest.main()
