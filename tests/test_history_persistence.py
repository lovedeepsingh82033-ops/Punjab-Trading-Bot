import unittest
from unittest.mock import patch

import pandas as pd

import main


class HistoryPersistenceGuardTests(unittest.TestCase):
    def test_save_failure_aborts_instead_of_continuing_with_stale_history(self):
        history = pd.DataFrame([{"symbol": "TEST", "signal_time": "2026-01-01T00:00:00Z"}])
        with patch.object(main, "atomic_save_history", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(RuntimeError, "refusing to continue with stale data"):
                main.save_history_or_raise(history)

    def test_successful_save_returns_normally(self):
        history = pd.DataFrame([{"symbol": "TEST"}])
        with patch.object(main, "atomic_save_history") as save:
            main.save_history_or_raise(history)
        save.assert_called_once_with(history)


if __name__ == "__main__":
    unittest.main()
