import unittest

import pandas as pd

from scanner_diagnostics import build_scanner_diagnostics


class ScannerDiagnosticsTests(unittest.TestCase):
    def test_empty_history_returns_zero_counts(self):
        result = build_scanner_diagnostics(pd.DataFrame())
        self.assertEqual(result["total_rows"], 0)
        self.assertEqual(result["directional_rows"], 0)
        self.assertEqual(result["by_symbol"], [])

    def test_counts_direction_aliases_and_unknown_values(self):
        history = pd.DataFrame({
            "symbol": ["XAU/USD", "XAU/USD", "EUR/USD", "EUR/USD"],
            "timeframe": ["H1", "M15", "H1", "M15"],
            "direction": ["BULLISH", "UP", "NEUTRAL", None],
        })
        result = build_scanner_diagnostics(history)
        self.assertEqual(result["total_rows"], 4)
        self.assertEqual(result["directional_rows"], 2)
        self.assertEqual(result["neutral_rows"], 1)
        self.assertEqual(result["unknown_rows"], 1)
        xau = next(row for row in result["by_symbol"] if row["name"] == "XAU/USD")
        self.assertEqual(xau["bullish"], 2)
        self.assertEqual(xau["total"], 2)

    def test_missing_direction_column_is_reported_as_unknown(self):
        result = build_scanner_diagnostics(pd.DataFrame({"symbol": ["XAU/USD"]}))
        self.assertEqual(result["unknown_rows"], 1)
        self.assertEqual(result["by_symbol"][0]["unknown"], 1)

    def test_invalid_input_type_is_rejected(self):
        with self.assertRaises(TypeError):
            build_scanner_diagnostics([{"direction": "BULLISH"}])


if __name__ == "__main__":
    unittest.main()
