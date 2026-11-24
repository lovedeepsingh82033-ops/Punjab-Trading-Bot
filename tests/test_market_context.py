import unittest

import pandas as pd

from market_context import volatility_context


class VolatilityContextTests(unittest.TestCase):
    def frame(self, values):
        return pd.DataFrame({
            "close": [100.0] * len(values),
            "atr": values,
        })

    def test_low_volatility_is_classified_against_recent_history(self):
        result = volatility_context(self.frame([2.0] * 99 + [0.5]))
        self.assertEqual(result["regime"], "LOW")
        self.assertAlmostEqual(result["atr_pct"], 0.5)
        self.assertEqual(result["sample_size"], 100)

    def test_high_volatility_is_classified_against_recent_history(self):
        result = volatility_context(self.frame([0.5] * 99 + [2.0]))
        self.assertEqual(result["regime"], "HIGH")
        self.assertAlmostEqual(result["percentile"], 100.0)

    def test_middle_volatility_is_normal(self):
        result = volatility_context(self.frame([1.0] * 99 + [1.0]))
        self.assertEqual(result["regime"], "NORMAL")

    def test_invalid_or_insufficient_data_is_rejected(self):
        with self.assertRaises(ValueError):
            volatility_context(self.frame([1.0] * 10))
        with self.assertRaises(ValueError):
            volatility_context(pd.DataFrame({"close": [100.0], "atr": [1.0]}), window=0)

    def test_non_positive_prices_and_atr_are_excluded(self):
        frame = self.frame([1.0] * 30)
        frame.loc[0, "close"] = 0
        frame.loc[1, "atr"] = float("nan")
        result = volatility_context(frame, window=30, minimum_samples=28)
        self.assertEqual(result["sample_size"], 28)


if __name__ == "__main__":
    unittest.main()
