import unittest

import pandas as pd

from data_quality import data_quality_context


class DataQualityTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame({
            "datetime": pd.date_range(
                "2026-01-01", periods=4, freq="5min", tz="UTC"
            ),
            "open": [100.0, 101.0, 102.0, 103.0],
            "high": [101.0, 102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0, 102.0],
            "close": [100.5, 101.5, 102.5, 103.5],
        })

    def test_valid_data_passes(self):
        result = data_quality_context(
            self.frame(), timeframe_minutes=5,
            as_of="2026-01-01T00:20:00Z",
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["invalid_rows"], 0)
        self.assertEqual(result["missing_intervals"], 0)

    def test_invalid_ohlc_fails(self):
        frame = self.frame()
        frame.loc[1, "high"] = 90.0
        result = data_quality_context(frame, timeframe_minutes=5)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["invalid_rows"], 1)

    def test_duplicate_timestamps_warn(self):
        frame = self.frame()
        frame.loc[1, "datetime"] = frame.loc[0, "datetime"]
        result = data_quality_context(frame)
        self.assertEqual(result["status"], "WARNING")
        self.assertEqual(result["duplicate_timestamps"], 1)

    def test_out_of_order_timestamps_warn(self):
        frame = self.frame()
        frame.loc[[1, 2], "datetime"] = frame.loc[[2, 1], "datetime"].to_numpy()
        result = data_quality_context(frame)
        self.assertTrue(result["out_of_order"])
        self.assertEqual(result["status"], "WARNING")

    def test_missing_intervals_are_reported(self):
        frame = self.frame().drop(index=1).reset_index(drop=True)
        result = data_quality_context(frame, timeframe_minutes=5)
        self.assertEqual(result["missing_intervals"], 1)
        self.assertEqual(result["status"], "WARNING")

    def test_stale_latest_candle_is_reported(self):
        result = data_quality_context(
            self.frame(), timeframe_minutes=5,
            as_of="2026-01-01T01:00:00Z",
        )
        self.assertTrue(result["latest_candle_stale"])
        self.assertEqual(result["status"], "WARNING")

    def test_empty_dataset_fails(self):
        result = data_quality_context(self.frame().iloc[:0])
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["row_count"], 0)

    def test_missing_columns_fail(self):
        result = data_quality_context(pd.DataFrame({"close": [100.0]}))
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("MISSING REQUIRED COLUMNS: ", result["findings"][0])

    def test_invalid_timeframe_rejected(self):
        with self.assertRaises(ValueError):
            data_quality_context(self.frame(), timeframe_minutes=0)


if __name__ == "__main__":
    unittest.main()
