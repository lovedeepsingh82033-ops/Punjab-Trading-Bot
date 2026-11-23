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


class HistoricalBacktestSamplingTests(unittest.TestCase):
    def make_bullish_frame(self, count=100):
        return pd.DataFrame({
            "open": [100.5 + i for i in range(count)],
            "close": [100.0 + i for i in range(count)],
            "ema9": [3.0] * count,
            "ema21": [2.0] * count,
            "ema50": [1.0] * count,
            "rsi": [60.0] * count,
            "macd": [2.0] * count,
            "macd_signal": [1.0] * count,
            "macd_hist": [1.0] * count,
            "adx": [25.0] * count,
            "plus_di": [30.0] * count,
            "minus_di": [10.0] * count,
        })

    def test_outcome_windows_do_not_overlap(self):
        result = main.historical_backtest(self.make_bullish_frame(), horizon_bars=3)
        # The 30-row holdout yields nine disjoint three-bar outcome windows.
        self.assertEqual(result["samples"], 9)
        self.assertEqual(result["overlap_policy"], "NON_OVERLAPPING_HORIZON")
        self.assertEqual(result["entry_policy"], "NEXT_CANDLE_OPEN_TO_HORIZON_CLOSE")
        # Nine signals start at indices 70, 73, ..., 94. Each enters at
        # the next candle open and exits at the horizon candle close.
        expected_moves = [
            (float(i + 103) - float(i + 101.5)) / float(i + 101.5) * 100
            for i in range(70, 97, 3)
        ]
        self.assertAlmostEqual(result["hit_rate"], 100.0)
        self.assertAlmostEqual(result["avg_move_pct"], sum(expected_moves) / len(expected_moves))
        expected_moves.sort()
        self.assertAlmostEqual(result["median_move_pct"], expected_moves[len(expected_moves) // 2])

    def test_short_history_returns_empty_metrics(self):
        result = main.historical_backtest(self.make_bullish_frame(count=20), horizon_bars=3)
        self.assertEqual(result["samples"], 0)
        self.assertIsNone(result["hit_rate"])
        self.assertIsNone(result["avg_move_pct"])
        self.assertIsNone(result["median_move_pct"])
        self.assertEqual(result["overlap_policy"], "NON_OVERLAPPING_HORIZON")
        self.assertEqual(result["entry_policy"], "NEXT_CANDLE_OPEN_TO_HORIZON_CLOSE")

    def test_invalid_horizon_is_rejected(self):
        for horizon in (0, -1, 1.5, True):
            with self.subTest(horizon=horizon):
                with self.assertRaises(ValueError):
                    main.historical_backtest(self.make_bullish_frame(), horizon_bars=horizon)


class IndicatorCausalityTests(unittest.TestCase):
    def test_past_indicator_values_do_not_change_when_future_rows_are_added(self):
        closes = [100.0 + i * 0.15 + (i % 7) * 0.08 for i in range(120)]
        frame = pd.DataFrame({
            "close": closes,
            "high": [value + 0.4 + (i % 3) * 0.02 for i, value in enumerate(closes)],
            "low": [value - 0.35 - (i % 4) * 0.015 for i, value in enumerate(closes)],
        })
        cutoff = 85
        full = main.add_indicators(frame)
        prefix = main.add_indicators(frame.iloc[:cutoff + 1].copy())
        columns = [
            "ema9", "ema21", "ema50", "rsi", "macd",
            "macd_signal", "macd_hist", "atr", "adx",
            "plus_di", "minus_di", "support", "resistance",
        ]
        for column in columns:
            with self.subTest(column=column):
                self.assertAlmostEqual(
                    float(full.iloc[cutoff][column]),
                    float(prefix.iloc[-1][column]),
                    places=10,
                )


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

    def test_missing_or_non_numeric_anchor_adx_fails_closed(self):
        for invalid in (None, "not-a-number"):
            with self.subTest(invalid=invalid):
                results = [item("M5", "BULLISH"), item("M15", "BULLISH"),
                           item("M30", "BULLISH"), item("H1", "BULLISH")]
                results[2]["adx"] = invalid
                decision = main.mtf_decision(results[0], results)
                self.assertFalse(decision["passed"])
                self.assertEqual(decision["cohort"], "BLOCKED")
                self.assertEqual(decision["reason"], "H1_OR_M30_ADX_BELOW_20")

    def test_infinite_anchor_adx_fails_closed(self):
        results = [item("M5", "BULLISH"), item("M15", "BULLISH"),
                   item("M30", "BULLISH"), item("H1", "BULLISH")]
        results[3]["adx"] = float("inf")
        decision = main.mtf_decision(results[0], results)
        self.assertFalse(decision["passed"])
        self.assertEqual(decision["cohort"], "BLOCKED")
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
        start = pd.Timestamp("2026-11-22T00:00:00Z")
        for i, status in enumerate(statuses):
            rows.append({
                "symbol": markets[i % len(markets)],
                "timeframe": timeframes[i % len(timeframes)],
                "signal_time": (start + pd.Timedelta(minutes=i)).isoformat(),
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



class MTFEvidenceAndTimestampTests(unittest.TestCase):
    def test_wilson_interval_and_minimum_sample_warning(self):
        rows = []
        for i in range(20):
            rows.append({
                "symbol": "EUR/USD", "timeframe": "M5",
                "signal_time": f"2026-11-22T10:{i:02d}:00Z",
                "mtf_cohort": "PASSED",
                "outcome_method": "EXACT_3_CANDLE",
                "outcome_status": "CORRECT" if i < 12 else "INCORRECT",
            })
        lines, stats = main.mtf_cohort_evidence_summary(pd.DataFrame(rows))
        self.assertEqual(stats["PASSED"]["directional_samples"], 20)
        self.assertAlmostEqual(stats["PASSED"]["hit_rate"], 0.60)
        self.assertGreater(stats["PASSED"]["ci95_high"], stats["PASSED"]["ci95_low"])
        self.assertIn("insufficient evidence", lines[0])
        self.assertIn("comparison: not ready", lines[2])

    def test_equivalent_timezone_strings_match_when_labeling_cohort(self):
        result = item("M5", "BULLISH")
        result["signal_time"] = "2026-11-22T09:55:00+00:00"
        scan = [
            result,
            item("M15", "BULLISH"),
            item("M30", "BULLISH"),
            item("H1", "BULLISH"),
        ]
        history = pd.DataFrame([{
            "symbol": "EUR/USD", "timeframe": "M5",
            "signal_time": "2026-11-22T11:55:00+02:00",
            "mtf_cohort": "UNASSESSED",
        }])
        labeled = main.label_mtf_cohorts(scan, history)
        self.assertEqual(labeled.loc[0, "mtf_cohort"], "PASSED")

    def test_equivalent_timestamp_does_not_create_duplicate_record(self):
        result = {
            "symbol": "EUR/USD", "timeframe": "M5",
            "signal_time": "2026-11-22T10:00:00+00:00",
        }
        history = pd.DataFrame([{
            "symbol": "EUR/USD", "timeframe": "M5",
            "signal_time": "2026-11-22T12:00:00+02:00",
        }])
        updated, is_new = main.save_new_record(result, history)
        self.assertFalse(is_new)
        self.assertEqual(len(updated), 1)

    def test_equivalent_timestamp_duplicate_rows_are_excluded(self):
        rows = [
            {"symbol": "EUR/USD", "timeframe": "M5",
             "signal_time": "2026-11-22T10:00:00Z",
             "outcome_method": "EXACT_3_CANDLE", "outcome_status": "CORRECT"},
            {"symbol": "EUR/USD", "timeframe": "M5",
             "signal_time": "2026-11-22T12:00:00+02:00",
             "outcome_method": "EXACT_3_CANDLE", "outcome_status": "INCORRECT"},
        ]
        self.assertEqual(main.accuracy_summary(pd.DataFrame(rows))["completed"], 0)


class RsiWarningTests(unittest.TestCase):
    def test_extreme_rsi_reports_overbought_warning(self):
        self.assertIn("OVERBOUGHT", main.rsi_warning(82.54))

    def test_rsi_below_extreme_threshold_has_no_extreme_warning(self):
        self.assertEqual(main.rsi_warning(79.99), "No extreme RSI warning")

    def test_non_finite_rsi_is_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    main.rsi_warning(value)
