import unittest

import pandas as pd

from research_context import market_regime_context


class MarketRegimeContextTests(unittest.TestCase):
    def frame(self, close=105, ema21=103, ema50=100, adx=30):
        return pd.DataFrame({"close": [close], "ema21": [ema21], "ema50": [ema50], "adx": [adx]})

    def test_trending_up(self):
        self.assertEqual(market_regime_context(self.frame())["label"], "TRENDING UP")

    def test_trending_down(self):
        self.assertEqual(market_regime_context(self.frame(95, 97, 100, 30))["label"], "TRENDING DOWN")

    def test_weak_trend_and_transition(self):
        self.assertEqual(market_regime_context(self.frame(adx=15))["label"], "RANGE / WEAK TREND")
        self.assertEqual(market_regime_context(self.frame(adx=22))["label"], "TRANSITION / MIXED")

    def test_strong_but_mixed_structure(self):
        self.assertEqual(market_regime_context(self.frame(101, 103, 100, 30))["label"], "STRONG BUT MIXED")

    def test_invalid_data_and_thresholds_rejected(self):
        with self.assertRaises(ValueError):
            market_regime_context(self.frame(close=0))
        with self.assertRaises(ValueError):
            market_regime_context(self.frame(), trend_adx=10, range_adx=20)
        with self.assertRaises(ValueError):
            market_regime_context(pd.DataFrame({"close": [1]}))


if __name__ == "__main__":
    unittest.main()
