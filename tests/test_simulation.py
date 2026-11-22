import unittest

from simulation import summarize_paper_returns


class PaperSimulationMetricsTests(unittest.TestCase):
    def test_costs_can_turn_gross_wins_into_net_losses(self):
        result = summarize_paper_returns([0.10, 0.10, -0.05], 0.12, 3)
        self.assertAlmostEqual(result["net_expectancy_pct"], -0.02)
        self.assertEqual(result["win_rate_pct"], 0.0)
        self.assertEqual(result["evidence_status"], "SAMPLE THRESHOLD MET")

    def test_compounded_total_return_and_drawdown(self):
        result = summarize_paper_returns([10.0, -10.0], 0.0, 2)
        self.assertAlmostEqual(result["gross_total_return_pct"], -1.0)
        self.assertAlmostEqual(result["net_total_return_pct"], -1.0)
        self.assertAlmostEqual(result["max_drawdown_pct"], 10.0)

    def test_small_sample_is_explicitly_flagged(self):
        result = summarize_paper_returns([1.0, -0.5], 0.01, 30)
        self.assertEqual(result["evidence_status"], "INSUFFICIENT SAMPLE: 2/30")

    def test_empty_input_has_no_fake_metrics(self):
        result = summarize_paper_returns([], 0.1)
        self.assertEqual(result["samples"], 0)
        self.assertIsNone(result["net_total_return_pct"])

    def test_rejects_invalid_costs_and_returns(self):
        for costs in (-0.1, float("nan"), float("inf"), True):
            with self.subTest(costs=costs):
                with self.assertRaises(ValueError):
                    summarize_paper_returns([1.0], costs)
        for values in ([float("nan")], [float("inf")], [-100.0], [True]):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    summarize_paper_returns(values)

    def test_profit_factor_uses_net_positive_and_negative_results(self):
        result = summarize_paper_returns([2.0, -1.0, 1.0], 0.5, 1)
        self.assertAlmostEqual(result["profit_factor"], 2.0)
        self.assertAlmostEqual(result["net_expectancy_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
