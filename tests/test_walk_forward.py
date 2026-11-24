import unittest
import numpy as np
import pandas as pd

from walk_forward import walk_forward_research_context


class WalkForwardResearchTests(unittest.TestCase):
    def frame(self, count=241):
        returns = np.tile([0.001, -0.0005, 0.0002, -0.0001], count // 4 + 1)[:count - 1]
        close = 100 * np.exp(np.r_[0.0, np.cumsum(returns)])
        return pd.DataFrame({"close": close})

    def test_creates_expanding_train_and_sequential_test_folds(self):
        result = walk_forward_research_context(self.frame(), folds=4, minimum_samples=10)
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["fold_count"], 4)
        train_sizes = [fold["train_samples"] for fold in result["folds"]]
        self.assertEqual(train_sizes, sorted(train_sizes))
        self.assertTrue(all(fold["test_samples"] >= 10 for fold in result["folds"]))

    def test_insufficient_history_is_reported_not_raised(self):
        result = walk_forward_research_context(self.frame(30), folds=4, minimum_samples=10)
        self.assertEqual(result["status"], "INSUFFICIENT SAMPLE")
        self.assertEqual(result["fold_count"], 0)

    def test_rejects_missing_or_invalid_prices(self):
        with self.assertRaises(ValueError):
            walk_forward_research_context(pd.DataFrame({"other": [1, 2, 3]}))
        with self.assertRaises(ValueError):
            walk_forward_research_context(pd.DataFrame({"close": [1, 2, np.nan, 4]}))
        with self.assertRaises(ValueError):
            walk_forward_research_context(pd.DataFrame({"close": [1, 2, 0, 4]}))

    def test_rejects_invalid_configuration(self):
        with self.assertRaises(ValueError):
            walk_forward_research_context(self.frame(), folds=1)
        with self.assertRaises(ValueError):
            walk_forward_research_context(self.frame(), minimum_samples=1)


if __name__ == "__main__":
    unittest.main()
