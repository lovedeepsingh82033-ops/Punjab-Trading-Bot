"""Descriptive market-regime classification for completed-candle data."""

import numpy as np
import pandas as pd


def market_regime_context(df, trend_adx=25.0, range_adx=20.0):
    """Classify trend/range conditions; never produces a trade instruction."""
    if not isinstance(trend_adx, (int, float)) or not isinstance(range_adx, (int, float)):
        raise ValueError("ADX thresholds must be numeric")
    if not np.isfinite(trend_adx) or not np.isfinite(range_adx) or range_adx < 0 or trend_adx <= range_adx:
        raise ValueError("ADX thresholds must be finite and trend_adx > range_adx >= 0")
    required = {"close", "ema21", "ema50", "adx"}
    if not required.issubset(df.columns):
        raise ValueError("DataFrame must contain close, ema21, ema50, and adx")
    row = df.iloc[-1]
    try:
        close, ema21, ema50, adx = (float(row[key]) for key in ("close", "ema21", "ema50", "adx"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Latest market-regime values must be numeric") from exc
    if not all(np.isfinite(value) for value in (close, ema21, ema50, adx)) or close <= 0 or ema21 <= 0 or ema50 <= 0 or adx < 0:
        raise ValueError("Latest market-regime values are invalid")

    if adx < range_adx:
        label = "RANGE / WEAK TREND"
        detail = f"ADX {adx:.1f} below {range_adx:.1f}; directional trend strength is weak"
    elif adx < trend_adx:
        label = "TRANSITION / MIXED"
        detail = f"ADX {adx:.1f} between {range_adx:.1f} and {trend_adx:.1f}; trend strength is developing"
    elif close > ema21 > ema50:
        label = "TRENDING UP"
        detail = f"ADX {adx:.1f}; close above EMA 21 above EMA 50"
    elif close < ema21 < ema50:
        label = "TRENDING DOWN"
        detail = f"ADX {adx:.1f}; close below EMA 21 below EMA 50"
    else:
        label = "STRONG BUT MIXED"
        detail = f"ADX {adx:.1f}; EMA structure is not aligned"

    return {"label": label, "detail": detail, "adx": adx,
            "trend_adx_threshold": float(trend_adx),
            "range_adx_threshold": float(range_adx)}
