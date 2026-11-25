import unittest
from unittest.mock import Mock

from fred_macro import fetch_fred_macro_context


class FredMacroTests(unittest.TestCase):
    def test_missing_key_does_not_make_request(self):
        client = Mock()
        result = fetch_fred_macro_context(api_key="", session=client)
        self.assertEqual(result["status"], "NOT CONFIGURED")
        client.get.assert_not_called()

    def test_parses_latest_and_previous_observations(self):
        client = Mock()
        response = Mock()
        response.json.return_value = {
            "observations": [
                {"date": "2026-10-01", "value": "4.2"},
                {"date": "2026-09-01", "value": "4.1"},
                {"date": "2026-08-01", "value": "."},
            ]
        }
        client.get.return_value = response
        result = fetch_fred_macro_context(
            api_key="test-key", session=client,
            series={"UNRATE": "Unemployment"}, observation_limit=3,
        )
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["series"][0]["latest"]["value"], 4.2)
        self.assertEqual(result["series"][0]["previous"]["value"], 4.1)
        self.assertAlmostEqual(result["series"][0]["change"], 0.1)
        self.assertNotIn("test-key", str(result))

    def test_failed_series_is_reported_without_secret(self):
        client = Mock()
        client.get.side_effect = RuntimeError("private detail")
        result = fetch_fred_macro_context(
            api_key="test-key", session=client,
            series={"UNRATE": "Unemployment"},
        )
        self.assertEqual(result["status"], "ERROR")
        self.assertNotIn("private detail", str(result))
        self.assertNotIn("test-key", str(result))

    def test_observation_limit_is_bounded(self):
        with self.assertRaises(ValueError):
            fetch_fred_macro_context(api_key="x", observation_limit=100)

    def test_timeout_is_bounded(self):
        with self.assertRaises(ValueError):
            fetch_fred_macro_context(api_key="x", timeout=60)


if __name__ == "__main__":
    unittest.main()
