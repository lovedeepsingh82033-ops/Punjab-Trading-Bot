import unittest
from datetime import datetime, timezone

from market_universe import ALL_FOREX_SYMBOLS, symbols_for_scan


class MarketUniverseTests(unittest.TestCase):
    def test_universe_contains_28_unique_currency_pairs(self):
        self.assertEqual(len(ALL_FOREX_SYMBOLS), 28)
        self.assertEqual(len(set(ALL_FOREX_SYMBOLS)), 28)
        for symbol in ALL_FOREX_SYMBOLS:
            base, quote = symbol.split("/")
            self.assertEqual(len(base), 3)
            self.assertEqual(len(quote), 3)
            self.assertNotEqual(base, quote)

    def test_each_scan_batch_has_seven_pairs(self):
        for hour in (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22):
            batch = symbols_for_scan(datetime(2026, 11, 27, hour, 0, tzinfo=timezone.utc))
            self.assertEqual(len(batch), 7)

    def test_four_batches_cover_the_entire_universe_without_overlap(self):
        batches = [
            symbols_for_scan(datetime(2026, 11, 27, hour, 0, tzinfo=timezone.utc))
            for hour in (0, 2, 4, 6)
        ]
        flattened = [symbol for batch in batches for symbol in batch]
        self.assertEqual(len(flattened), 28)
        self.assertEqual(set(flattened), set(ALL_FOREX_SYMBOLS))
        self.assertEqual(len(set(flattened)), 28)

    def test_batch_repeats_after_eight_hours(self):
        first = datetime(2026, 11, 27, 0, 0, tzinfo=timezone.utc)
        later = datetime(2026, 11, 27, 8, 0, tzinfo=timezone.utc)
        self.assertEqual(symbols_for_scan(first), symbols_for_scan(later))

    def test_naive_datetime_is_rejected(self):
        with self.assertRaises(ValueError):
            symbols_for_scan(datetime(2026, 11, 27, 0, 0))


if __name__ == "__main__":
    unittest.main()
