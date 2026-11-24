"""Non-directional cross-market and anomaly research diagnostics.

These functions describe historical data relationships and unusual observations.
They do not forecast prices or generate trading instructions.
"""
import numpy as np
import pandas as pd


def anomaly_research_context(df, window=100, minimum_samples=30, threshold=3.5):
    """Flag an unusually large latest absolute return using a robust historical baseline."""
    if not isinstance(window, int) or isinstance(window, bool) or window < 2:
        raise ValueError("window must be an integer >= 2")
    if not isinstance(minimum_samples, int) or isinstance(minimum_samples, bool) or minimum_samples < 10:
        raise ValueError("minimum_samples must be an integer >= 10")
    if minimum_samples > window:
        raise ValueError("minimum_samples cannot exceed window")
    if not isinstance(threshold, (int, float)) or not np.isfinite(threshold) or threshold <= 0:
        raise ValueError("threshold must be finite and positive")
    if "close" not in df.columns:
        raise ValueError("DataFrame must contain close")

    close = pd.to_numeric(df["close"], errors="coerce")
    returns = np.log(close.where(close > 0) / close.where(close > 0).shift(1))
    values = returns.replace([np.inf, -np.inf], np.nan).dropna().tail(window + 1)
    if len(values) < minimum_samples + 1:
        return {
            "status": "INSUFFICIENT DATA",
            "score": None,
            "latest_abs_return_pct": None,
            "baseline_samples": max(0, len(values) - 1),
            "threshold": float(threshold),
            "scope": "historical outlier diagnostic only; not predictive",
        }

    baseline = values.iloc[:-1].abs().tail(window)
    latest = float(abs(values.iloc[-1]) * 100.0)
    baseline_pct = baseline * 100.0
    median = float(baseline_pct.median())
    mad = float((baseline_pct - median).abs().median())
    if mad > 0:
        scale = 1.4826 * mad
    else:
        scale = float(baseline_pct.std(ddof=1))
    score = float((latest - median) / scale) if scale > 0 else (0.0 if latest == median else float("inf"))
    unusual = score >= threshold
    return {
        "status": "UNUSUAL OBSERVATION" if unusual else "WITHIN BASELINE",
        "score": score if np.isfinite(score) else None,
        "latest_abs_return_pct": latest,
        "baseline_samples": int(len(baseline_pct)),
        "threshold": float(threshold),
        "scope": "historical outlier diagnostic only; not predictive",
    }


def cross_market_correlation_context(series_by_symbol, minimum_samples=30):
    """Compute pairwise Pearson correlations of aligned completed-candle log returns."""
    if not isinstance(minimum_samples, int) or isinstance(minimum_samples, bool) or minimum_samples < 3:
        raise ValueError("minimum_samples must be an integer >= 3")
    aligned = {}
    for symbol, frame in series_by_symbol.items():
        if not {"datetime", "close"}.issubset(frame.columns):
            continue
        data = frame[["datetime", "close"]].copy()
        data["datetime"] = pd.to_datetime(data["datetime"], utc=True, errors="coerce")
        data["close"] = pd.to_numeric(data["close"], errors="coerce")
        data = data.dropna().drop_duplicates("datetime").sort_values("datetime")
        data = data[data["close"] > 0]
        if len(data) < minimum_samples + 1:
            continue
        data["return"] = np.log(data["close"] / data["close"].shift(1))
        aligned[str(symbol)] = data.set_index("datetime")["return"]

    pairs = []
    symbols = sorted(aligned)
    for i, left in enumerate(symbols):
        for right in symbols[i + 1:]:
            joined = pd.concat(
                [aligned[left].rename("left"), aligned[right].rename("right")],
                axis=1,
                join="inner",
            ).dropna()
            if len(joined) < minimum_samples:
                continue
            correlation = float(joined["left"].corr(joined["right"]))
            if np.isfinite(correlation):
                pairs.append({
                    "symbol_a": left,
                    "symbol_b": right,
                    "correlation": correlation,
                    "samples": int(len(joined)),
                })
    pairs.sort(key=lambda item: abs(item["correlation"]), reverse=True)
    return {
        "pairs": pairs,
        "pairs_calculated": len(pairs),
        "minimum_samples": minimum_samples,
        "scope": "historical return correlation; not causation or a forecast",
    }
