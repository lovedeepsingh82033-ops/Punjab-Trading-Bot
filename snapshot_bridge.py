"""Private Supabase Storage bridge for scanner snapshots.

The scanner uploads one compact JSON object after each scheduled run. The
separate Telegram worker downloads that object on demand. Credentials are
read only from environment variables and are never logged.
"""
import json
import os
from pathlib import Path
from urllib.parse import quote

import requests


def _configuration():
    base_url = os.getenv("BOT_STATE_BRIDGE_URL", "").strip().rstrip("/")
    key = os.getenv("BOT_STATE_BRIDGE_KEY", "").strip()
    bucket = os.getenv("BOT_STATE_BRIDGE_BUCKET", "scanner-state").strip()
    if not base_url or not key or not bucket:
        return None
    return base_url, key, bucket


def _object_url(base_url, bucket):
    safe_bucket = quote(bucket, safe="")
    return f"{base_url}/storage/v1/object/{safe_bucket}/bot_state.json"


def upload_snapshot(path="bot_state.json"):
    """Upload the local snapshot; return False when bridge is not configured."""
    config = _configuration()
    if config is None:
        return False

    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Refusing to upload an invalid scanner snapshot.")

    base_url, key, bucket = config
    response = requests.put(
        _object_url(base_url, bucket),
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "x-upsert": "true",
        },
        data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
        timeout=20,
    )
    response.raise_for_status()
    return True


def download_snapshot():
    """Download the latest snapshot, or return None when unavailable."""
    config = _configuration()
    if config is None:
        return None

    base_url, key, bucket = config
    response = requests.get(
        _object_url(base_url, bucket),
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
        },
        timeout=15,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return None
    return payload
