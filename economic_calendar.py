"""CSV-based economic calendar context for market research.

No third-party calendar is assumed. Events are only reported when a dated,
source-attributed row is present in the repository CSV. This module does not
fetch live events or generate trading instructions.
"""
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path


REQUIRED_COLUMNS = {"event_time_utc", "currency", "impact", "event", "source"}
ALLOWED_IMPACTS = {"LOW", "MEDIUM", "HIGH"}


def economic_calendar_context(path="economic_calendar.csv", as_of=None,
                              symbols=None, lookahead_hours=24):
    if not isinstance(lookahead_hours, (int, float)) or isinstance(lookahead_hours, bool) or lookahead_hours <= 0:
        raise ValueError("lookahead_hours must be positive")
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    now = now.astimezone(timezone.utc)
    target_currencies = set()
    for symbol in symbols or []:
        target_currencies.update(part.upper() for part in str(symbol).replace("/", " ").split())
    target_currencies.discard("")

    file_path = Path(path)
    if not file_path.exists():
        return {"status": "NOT CONFIGURED", "events": [], "count": 0,
                "message": "Add source-attributed events to economic_calendar.csv; no live feed is configured."}

    events = []
    invalid_rows = 0
    cutoff = now + timedelta(hours=float(lookahead_hours))
    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
            raise ValueError("Calendar CSV is missing required columns")
        for row in reader:
            try:
                raw_time = (row.get("event_time_utc") or "").strip()
                event_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                if event_time.tzinfo is None:
                    raise ValueError("event_time_utc must include a timezone")
                event_time = event_time.astimezone(timezone.utc)
                currency = (row.get("currency") or "").strip().upper()
                impact = (row.get("impact") or "").strip().upper()
                name = (row.get("event") or "").strip()
                source = (row.get("source") or "").strip()
                if not currency or impact not in ALLOWED_IMPACTS or not name or not source:
                    raise ValueError("invalid calendar fields")
            except (TypeError, ValueError, OverflowError):
                invalid_rows += 1
                continue
            if now <= event_time <= cutoff and (not target_currencies or currency in target_currencies):
                events.append({
                    "event_time_utc": event_time.isoformat().replace("+00:00", "Z"),
                    "currency": currency, "impact": impact,
                    "event": name[:160], "source": source[:200],
                })
    events.sort(key=lambda item: item["event_time_utc"])
    high_count = sum(item["impact"] == "HIGH" for item in events)
    status = "EVENTS FOUND" if events else "NO MATCHING EVENTS"
    return {
        "status": status, "events": events, "count": len(events),
        "high_impact_count": high_count, "invalid_rows": invalid_rows,
        "lookahead_hours": float(lookahead_hours),
        "message": "Manually maintained, source-attributed calendar context; not a live feed.",
    }
