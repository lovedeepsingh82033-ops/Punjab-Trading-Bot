"""Educational institutional-style market research diagnostics.

Metrics describe historical market data and offline test integrity only.
They are not portfolio advice, trade instructions, or execution logic.
"""
import numpy as np
import pandas as pd


def _close_series(df):
    if "close" not in df.columns:
        raise ValueError("DataFrame must contain close")
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(close) < 2 or (close <= 0).any() or not np.isfinite(close.to_numpy()).all():
        raise ValueError("At least two finite positive close prices are required")
    return close


def quantitative_research_context(df):
    """Summarize historical close-to-close log-return distribution."""
    close = _close_series(df)
    returns = np.log(close / close.shift(1)).dropna()
    if returns.empty or not np.isfinite(returns.to_numpy()).all():
        raise ValueError("Historical returns are not valid")
    return {
        "sample_count": int(len(returns)),
        "mean_return_pct": float(returns.mean() * 100),
        "return_volatility_pct": float(returns.std(ddof=1) * 100) if len(returns) > 1 else 0.0,
        "return_skew": float(returns.skew()) if len(returns) >= 3 else 0.0,
        "return_excess_kurtosis": float(returns.kurt()) if len(returns) >= 4 else 0.0,
    }


def risk_management_context(df):
    """Report historical price-path drawdown and absolute candle moves only."""
    close = _close_series(df)
    drawdown = (close / close.cummax() - 1.0) * 100
    returns_pct = close.pct_change().dropna().abs() * 100
    return {
        "max_drawdown_pct": float(abs(drawdown.min())),
        "return_p95_abs_pct": float(returns_pct.quantile(0.95)) if not returns_pct.empty else 0.0,
        "observations": int(len(close)),
        "scope": "historical price series only; not account or portfolio risk",
    }


def algorithmic_system_context(df):
    """Validate candle data and mature indicator values without flagging warm-up NaNs."""
    required = {
        "datetime", "open", "high", "low", "close",
        "ema9", "ema21", "ema50", "rsi", "macd",
        "macd_signal", "macd_hist", "adx", "atr",
        "plus_di", "minus_di",
    }
    missing = sorted(required.difference(df.columns))
    if missing:
        failed = ["MISSING REQUIRED FIELDS: " + ", ".join(missing)]
        return {
            "status": "WARNING",
            "detail": "Missing required fields",
            "checks_passed": 0,
            "checks_total": 4,
            "failed_checks": failed,
            "check_details": [
                {"name": "Required fields present", "passed": False},
                {"name": "Timestamps valid and chronological", "passed": False},
                {"name": "Timestamps unique", "passed": False},
                {"name": "OHLC and mature indicators finite/consistent", "passed": False},
            ],
        }

    times = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
    numeric = df[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    ohlc = numeric.to_numpy(dtype=float)
    valid_ohlc = np.isfinite(ohlc).all(axis=1) & (numeric > 0).all(axis=1)
    valid_ohlc &= numeric["high"] >= numeric["low"]
    valid_ohlc &= numeric["high"] >= numeric[["open", "close"]].max(axis=1)
    valid_ohlc &= numeric["low"] <= numeric[["open", "close"]].min(axis=1)

    indicator_columns = [
        "ema9", "ema21", "ema50", "rsi", "macd",
        "macd_signal", "macd_hist", "adx", "atr",
        "plus_di", "minus_di",
    ]
    indicators = df[indicator_columns].apply(pd.to_numeric, errors="coerce")
    values = indicators.to_numpy(dtype=float)

    # RSI, ADX, ATR and directional indicators need a warm-up period.
    # Validate the mature series and the latest row, not expected early NaNs.
    warmup = 50
    mature = values[warmup:] if len(values) > warmup else np.empty((0, len(indicator_columns)))
    mature_finite = bool(
        len(mature) > 0
        and np.isfinite(mature).all()
        and np.isfinite(values[-1]).all()
    )
    rsi = indicators["rsi"].to_numpy(dtype=float)
    adx = indicators["adx"].to_numpy(dtype=float)
    bounded_indicators_valid = bool(
        mature_finite
        and ((rsi[warmup:] >= 0) & (rsi[warmup:] <= 100)).all()
        and ((adx[warmup:] >= 0) & (adx[warmup:] <= 100)).all()
    )

    checks = [
        bool(not times.isna().any() and times.is_monotonic_increasing),
        bool(not times.duplicated().any()),
        bool(valid_ohlc.all()),
        bool(mature_finite and bounded_indicators_valid),
    ]
    names = [
        "Timestamps valid and chronological",
        "Timestamps unique",
        "OHLC values positive and internally consistent",
        "EMA/RSI/MACD/ADX/ATR values finite after 50-row warm-up",
    ]
    failed = [name for name, passed in zip(names, checks) if not passed]
    passed_count = sum(checks)
    return {
        "status": "PASS" if passed_count == len(checks) else "WARNING",
        "detail": f"{passed_count}/{len(checks)} data and indicator integrity checks passed",
        "checks_passed": int(passed_count),
        "checks_total": len(checks),
        "failed_checks": failed,
        "check_details": [
            {"name": name, "passed": bool(passed)}
            for name, passed in zip(names, checks)
        ],
    }


def validation_context(backtest, minimum_samples=30):
    """Label the existing chronological holdout test's evidence sufficiency."""
    if not isinstance(minimum_samples, int) or isinstance(minimum_samples, bool) or minimum_samples < 1:
        raise ValueError("minimum_samples must be a positive integer")
    samples = backtest.get("samples", 0)
    if not isinstance(samples, int) or isinstance(samples, bool) or samples < 0:
        raise ValueError("backtest samples must be a non-negative integer")
    overlap = backtest.get("overlap_policy", "UNKNOWN")
    entry = backtest.get("entry_policy", "UNKNOWN")
    if samples < minimum_samples:
        status = "INSUFFICIENT SAMPLE"
        detail = f"{samples} holdout observations; {minimum_samples} required before evidence review"
    elif overlap != "NON_OVERLAPPING_HORIZON" or entry != "NEXT_CANDLE_OPEN_TO_HORIZON_CLOSE":
        status = "REVIEW REQUIRED"
        detail = "Holdout methodology metadata does not match the documented test design"
    else:
        status = "METHODOLOGY CHECK PASS"
        detail = f"{samples} non-overlapping chronological holdout observations; costs and slippage are not modeled"
    return {
        "status": status, "detail": detail, "samples": samples,
        "minimum_samples": minimum_samples, "overlap_policy": overlap,
        "entry_policy": entry, "scope": "historical directional validation, not profitability",
    }
