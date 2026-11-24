"""Operational health summary for the Punjab market-data scanner.

This module reports scan completeness and service outcomes only. It does not
interpret market direction, produce trading instructions, or place orders.
"""


def scanner_health_context(
    expected_analyses,
    completed_analyses,
    processing_errors,
    api_rate_limited=False,
    telegram_deliveries=0,
    discord_deliveries=0,
):
    """Summarize one scan run using explicit counters supplied by the caller."""
    counters = {
        "expected_analyses": expected_analyses,
        "completed_analyses": completed_analyses,
        "processing_errors": processing_errors,
        "telegram_deliveries": telegram_deliveries,
        "discord_deliveries": discord_deliveries,
    }
    for name, value in counters.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")

    if completed_analyses > expected_analyses:
        raise ValueError("completed_analyses cannot exceed expected_analyses")
    if not isinstance(api_rate_limited, bool):
        raise ValueError("api_rate_limited must be a boolean")

    completion_pct = (
        completed_analyses / expected_analyses * 100.0
        if expected_analyses else 0.0
    )

    if expected_analyses == 0:
        status = "NO TARGETS"
    elif completed_analyses == 0:
        status = "NO DATA"
    elif api_rate_limited or processing_errors:
        status = "DEGRADED"
    elif completed_analyses < expected_analyses:
        status = "PARTIAL"
    else:
        status = "HEALTHY"

    return {
        "status": status,
        "expected_analyses": expected_analyses,
        "completed_analyses": completed_analyses,
        "completion_pct": completion_pct,
        "processing_errors": processing_errors,
        "api_rate_limited": api_rate_limited,
        "telegram_deliveries": telegram_deliveries,
        "discord_deliveries": discord_deliveries,
        "scope": "scanner operations only; not a market forecast or trading instruction",
    }
