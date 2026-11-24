"""Atomic, compact snapshot writer for the read-only Telegram bot."""
import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path


def _safe(value, depth=0):
    if depth > 7:
        return "[truncated]"
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            return None
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _safe(v, depth + 1) for k, v in list(value.items())[:100]}
    if isinstance(value, (list, tuple)):
        return [_safe(v, depth + 1) for v in value[:100]]
    if hasattr(value, "item"):
        try:
            return _safe(value.item(), depth + 1)
        except (ValueError, TypeError):
            pass
    return str(value)[:500]


def write_bot_snapshot(*, scan_cutoff, scanner_health, dashboard, intelligence,
                       calendar_context, scan_results, path=None):
    target = Path(path or os.getenv("BOT_STATE_PATH", "bot_state.json"))
    observations = []
    for item in scan_results[-50:]:
        observations.append({
            key: _safe(item.get(key))
            for key in ("symbol", "timeframe", "price", "candle_time",
                        "data_quality", "market_regime", "volatility",
                        "anomaly_research", "walk_forward")
            if key in item
        })
    payload = {
        "schema_version": 1,
        "generated_at": _safe(scan_cutoff),
        "scanner_health": _safe(scanner_health),
        "dashboard": _safe(dashboard),
        "intelligence": _safe(intelligence),
        "calendar": _safe(calendar_context),
        "observations": observations,
        "observation_count": len(scan_results),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=target.name + ".", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
        os.replace(temp_path, target)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    return target
