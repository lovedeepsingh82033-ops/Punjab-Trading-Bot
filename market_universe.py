"""Rotating, quota-aware coverage for a 28-pair FX research universe.

The scanner runs every two hours. Four deterministic seven-pair batches ensure
all 28 pairs are observed once every eight hours without multiplying the
existing per-run API request budget.
"""

from datetime import datetime, timezone

ALL_FOREX_SYMBOLS = (
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "USD/CAD", "NZD/USD",
    "EUR/GBP", "EUR/JPY", "EUR/CHF", "EUR/AUD", "EUR/CAD", "EUR/NZD",
    "GBP/JPY", "GBP/CHF", "GBP/AUD", "GBP/CAD", "GBP/NZD",
    "AUD/JPY", "AUD/CHF", "AUD/CAD", "AUD/NZD",
    "NZD/JPY", "NZD/CHF", "NZD/CAD",
    "CAD/JPY", "CAD/CHF", "CHF/JPY",
)

BATCH_SIZE = 7
BATCH_INTERVAL_HOURS = 2


def symbols_for_scan(as_of=None):
    """Return the seven-pair batch assigned to the current UTC two-hour slot."""
    if as_of is None:
        as_of = datetime.now(timezone.utc)
    if not isinstance(as_of, datetime):
        raise TypeError("as_of must be a datetime")
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    utc_time = as_of.astimezone(timezone.utc)
    slot = (utc_time.weekday() * 12) + (utc_time.hour // BATCH_INTERVAL_HOURS)
    batch_count = (len(ALL_FOREX_SYMBOLS) + BATCH_SIZE - 1) // BATCH_SIZE
    batch_index = slot % batch_count
    start = batch_index * BATCH_SIZE
    return list(ALL_FOREX_SYMBOLS[start:start + BATCH_SIZE])
