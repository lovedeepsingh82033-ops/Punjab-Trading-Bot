"""Descriptive market-volatility context for completed-candle data."""

import numpy as np
import pandas as pd


def volatility_context(df, window=100, minimum_samples=30):
    """Classify latest ATR as low/normal/high versus recent ATR as % of price.

    This is descriptive context only: it does not change the scanner's
    directional observation or notification eligibility.
    """
    if not isinstance(window, int) or isinstance(window, bool) or window < 1:
        raise ValueError("window must be a positive integer")
    if not isinstance(minimum_samples, int) or isinstance(minimum_samples, bool) or minimum_samples < 1:
        raise ValueError("minimum_samples must be a positive integer")
    if minimum_samples > window:
        raise ValueError("minimum_samples cannot exceed window")
    if not {"close", "atr"}.issubset(df.columns):
        raise ValueError("DataFrame must contain close and atr columns")

    recent = df[["close", "atr"]].tail(window).apply(pd.to_numeric, errors="coerce")
    valid = (
        np.isfinite(recent["close"])
        & np.isfinite(recent["atr"])
        & (recent["close"] > 0)
        & (recent["atr"] > 0)
    )
    if not bool(valid.iloc[-1]):
        raise ValueError("Latest candle has invalid close or ATR data")
    atr_pct = (recent.loc[valid, "atr"] / recent.loc[valid, "close"]) * 100.0
    if len(atr_pct) < minimum_samples:
        raise ValueError("Not enough valid candles for volatility context")

    current = float(atr_pct.iloc[-1])
    less = int((atr_pct.iloc[:-1] < current).sum())
    equal = int((atr_pct.iloc[:-1] == current).sum())
    historical_count = len(atr_pct) - 1
    percentile = (
        float((less + 0.5 * equal) / historical_count * 100.0)
        if historical_count > 0 else 50.0
    )
    if not np.isfinite(current) or not np.isfinite(percentile):
        raise ValueError("Volatility context is not finite")

    if percentile < 25.0:
        regime = "LOW"
    elif percentile > 75.0:
        regime = "HIGH"
    else:
        regime = "NORMAL"

    return {
        "atr_pct": current,
        "percentile": percentile,
        "regime": regime,
        "sample_size": int(len(atr_pct)),
    }
