"""FRED macroeconomic context for descriptive research only.

Requires an optional FRED_API_KEY. No requests are made at import time.
This module reports published observations and changes; it does not forecast,
generate trading instructions, or connect to brokers.
"""
import math
import os

import requests


FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
DEFAULT_SERIES = {
    "FEDFUNDS": "Federal Funds Effective Rate",
    "CPIAUCSL": "Consumer Price Index for All Urban Consumers",
    "UNRATE": "Civilian Unemployment Rate",
    "DGS10": "10-Year Treasury Constant Maturity Rate",
    "DTWEXBGS": "Nominal Broad U.S. Dollar Index",
}


def fetch_fred_macro_context(api_key=None, session=None, series=None,
                             observation_limit=3, timeout=12):
    """Fetch a small, bounded set of recent FRED observations.

    Returns explicit configuration/partial/error states. Values are published
    observations, not real-time market prices. The API key is never returned
    or included in error messages.
    """
    key = (api_key if api_key is not None else os.getenv("FRED_API_KEY", "")).strip()
    if not key:
        return {
            "status": "NOT CONFIGURED",
            "source": "Federal Reserve Bank of St. Louis FRED",
            "series": [],
            "message": "Set FRED_API_KEY to enable published macroeconomic observations.",
        }

    if not isinstance(observation_limit, int) or isinstance(observation_limit, bool) or not 2 <= observation_limit <= 10:
        raise ValueError("observation_limit must be an integer from 2 to 10")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0 or timeout > 30:
        raise ValueError("timeout must be greater than 0 and at most 30 seconds")

    selected = series or DEFAULT_SERIES
    if not isinstance(selected, dict) or not selected:
        raise ValueError("series must be a non-empty mapping of series IDs to labels")

    client = session or requests.Session()
    results = []
    errors = []

    for series_id, label in selected.items():
        if not isinstance(series_id, str) or not series_id.isalnum():
            errors.append("Invalid series identifier")
            continue
        try:
            response = client.get(
                FRED_OBSERVATIONS_URL,
                params={
                    "series_id": series_id,
                    "api_key": key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": observation_limit,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            observations = payload.get("observations")
            if not isinstance(observations, list):
                raise ValueError("Invalid observations payload")

            valid = []
            for item in observations:
                date = item.get("date")
                raw_value = item.get("value")
                if not isinstance(date, str) or not isinstance(raw_value, str):
                    continue
                try:
                    value = float(raw_value)
                except ValueError:
                    continue
                if math.isfinite(value):
                    valid.append({"date": date, "value": value})

            valid.sort(key=lambda item: item["date"], reverse=True)
            if not valid:
                errors.append("No numeric observations for " + series_id)
                continue

            latest = valid[0]
            previous = valid[1] if len(valid) > 1 else None
            results.append({
                "series_id": series_id,
                "label": str(label)[:120],
                "latest": latest,
                "previous": previous,
                "change": (
                    latest["value"] - previous["value"] if previous else None
                ),
                "observations_returned": len(valid),
                "source": "Federal Reserve Bank of St. Louis FRED",
            })
        except (requests.RequestException, ValueError, TypeError, KeyError):
            errors.append("Unable to retrieve " + series_id)

    if results and errors:
        status = "PARTIAL"
    elif results:
        status = "OK"
    else:
        status = "ERROR"

    return {
        "status": status,
        "source": "Federal Reserve Bank of St. Louis FRED",
        "series": results,
        "errors": errors,
        "message": (
            "Published macroeconomic observations; release dates and "
            "frequencies differ by series. Descriptive context only."
        ),
    }
