import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import snapshot_bridge


class SnapshotBridgeTests(unittest.TestCase):
    def test_upload_is_disabled_without_bridge_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(snapshot_bridge.upload_snapshot("missing.json"))

    def test_upload_posts_only_valid_schema_snapshot(self):
        payload = {"schema_version": 1, "generated_at": "2026-11-25T00:00:00Z"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bot_state.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.dict(os.environ, {
                "BOT_STATE_BRIDGE_URL": "https://example.supabase.co",
                "BOT_STATE_BRIDGE_KEY": "test-secret",
                "BOT_STATE_BRIDGE_BUCKET": "scanner-state",
            }, clear=True), patch("snapshot_bridge.requests.post") as post:
                post.return_value.raise_for_status.return_value = None
                self.assertTrue(snapshot_bridge.upload_snapshot(path))
                args, kwargs = post.call_args
                self.assertEqual(args[0], "https://example.supabase.co/storage/v1/object/scanner-state/bot_state.json")
                self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-secret")
                self.assertEqual(json.loads(kwargs["data"]), payload)

    def test_invalid_snapshot_is_not_uploaded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"schema_version": 2}', encoding="utf-8")
            with patch.dict(os.environ, {
                "BOT_STATE_BRIDGE_URL": "https://example.supabase.co",
                "BOT_STATE_BRIDGE_KEY": "test-secret",
            }, clear=True), patch("snapshot_bridge.requests.post") as post:
                with self.assertRaises(ValueError):
                    snapshot_bridge.upload_snapshot(path)
                post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
