"""Data-quality diagnostics for historical market candle datasets.

This module checks input integrity and freshness only. It does not produce
forecasts, trading instructions, or execution decisions.
"""
import numpy as np
import pandas as pd


def data_quality_context(df, timeframe_minutes=None, as_of=None):
    """Return transparent integrity checks for a timestamped OHLC dataset.

    Critical structural or OHLC errors produce FAIL. Duplicate/out-of-order
    timestamps, missing intervals, and stale/future latest candles produce
    WARNING. Missing optional timing context is reported, not guessed.
    """
    required = {"datetime", "open", "high", "low", "close"}
    missing = sorted(required.difference(getattr(df, "columns", [])))
    if df is None or not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")
    if df.empty:
        return {
            "status": "FAIL", "checks_passed": 0, "checks_total": 5,
            "row_count": 0, "invalid_rows": 0, "duplicate_timestamps": 0,
            "out_of_order": False, "missing_intervals": None,
            "findings": ["EMPTY DATASET"],
            "scope": "data integrity only; not a forecast or trading instruction",
        }

    findings = []
    if missing:
        findings.append("MISSING REQUIRED COLUMNS: " + ", ".join(missing))
        return {
            "status": "FAIL", "checks_passed": 0, "checks_total": 5,
            "row_count": int(len(df)), "invalid_rows": int(len(df)),
            "duplicate_timestamps": 0, "out_of_order": False,
            "missing_intervals": None, "findings": findings,
            "scope": "data integrity only; not a forecast or trading instruction",
        }

    times = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
    numeric = df[["open", "high", "low", "close"]].apply(
        pd.to_numeric, errors="coerce"
    )
    finite = np.isfinite(numeric.to_numpy(dtype=float)).all(axis=1)
    positive = (numeric > 0).all(axis=1)
    ohlc = (
        finite & positive
        & (numeric["high"] >= numeric["low"])
        & (numeric["high"] >= numeric[["open", "close"]].max(axis=1))
        & (numeric["low"] <= numeric[["open", "close"]].min(axis=1))
    )
    valid = times.notna().to_numpy() & ohlc.to_numpy()
    invalid_rows = int((~valid).sum())
    duplicate_count = int(times[times.notna()].duplicated().sum())
    valid_times = times.dropna()
    out_of_order = bool(not valid_times.is_monotonic_increasing)

    missing_intervals = None
    if timeframe_minutes is not None:
        if (not isinstance(timeframe_minutes, int)
                or isinstance(timeframe_minutes, bool)
                or timeframe_minutes < 1):
            raise ValueError("timeframe_minutes must be a positive integer")
        ordered_unique = valid_times.drop_duplicates().sort_values()
        if len(ordered_unique) > 1:
            deltas = ordered_unique.diff().dropna()
            expected = pd.Timedelta(minutes=timeframe_minutes)
            missing_intervals = int(
                sum(max(0, int(delta / expected) - 1) for delta in deltas)
            )
        else:
            missing_intervals = 0

    stale_latest = None
    if as_of is not None and len(valid_times):
        cutoff = pd.to_datetime(as_of, utc=True, errors="coerce")
        if pd.isna(cutoff):
            raise ValueError("as_of must be a valid timestamp")
        latest = valid_times.max()
        stale_latest = bool(latest > cutoff)
        if stale_latest:
            findings.append("LATEST CANDLE IS IN THE FUTURE")
        elif timeframe_minutes is not None:
            age = cutoff - latest
            if age > pd.Timedelta(minutes=2 * timeframe_minutes):
                stale_latest = True
                findings.append("LATEST CANDLE IS STALE")

    checks = [
        not missing,
        invalid_rows == 0,
        duplicate_count == 0,
        not out_of_order,
        (missing_intervals in (None, 0)) and stale_latest is not True,
    ]
    if invalid_rows:
        findings.append("INVALID TIMESTAMP OR OHLC ROWS")
    if duplicate_count:
        findings.append("DUPLICATE TIMESTAMPS")
    if out_of_order:
        findings.append("TIMESTAMPS OUT OF ORDER")
    if missing_intervals:
        findings.append("MISSING CANDLE INTERVALS")
    if not findings:
        findings.append("ALL CHECKS PASSED")

    critical_failure = invalid_rows > 0
    status = "FAIL" if critical_failure else ("PASS" if all(checks) else "WARNING")
    return {
        "status": status,
        "checks_passed": int(sum(checks)),
        "checks_total": len(checks),
        "row_count": int(len(df)),
        "invalid_rows": invalid_rows,
        "duplicate_timestamps": duplicate_count,
        "out_of_order": out_of_order,
        "missing_intervals": missing_intervals,
        "latest_candle_stale": stale_latest,
        "findings": findings,
        "scope": "data integrity only; not a forecast or trading instruction",
    }
