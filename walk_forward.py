"""Chronological walk-forward stability diagnostics for historical market data.

This module compares expanding historical return distributions with later,
unseen windows. It does not train a trading model or produce trade guidance.
"""
import numpy as np
import pandas as pd


def walk_forward_research_context(
    df, train_fraction=0.5, folds=4, minimum_samples=10
):
    """Compare expanding train windows with sequential, non-overlapping tests."""
    if not isinstance(folds, int) or isinstance(folds, bool) or folds < 2:
        raise ValueError("folds must be an integer of at least 2")
    if not isinstance(minimum_samples, int) or isinstance(minimum_samples, bool) or minimum_samples < 2:
        raise ValueError("minimum_samples must be an integer of at least 2")
    if not isinstance(train_fraction, (int, float)) or isinstance(train_fraction, bool) or not 0.2 <= train_fraction < 0.8:
        raise ValueError("train_fraction must be between 0.2 and 0.8")

    if "close" not in df.columns:
        raise ValueError("DataFrame must contain close")
    close = pd.to_numeric(df["close"], errors="coerce")
    if close.isna().any() or not np.isfinite(close.to_numpy(dtype=float)).all() or (close <= 0).any():
        raise ValueError("close prices must be finite, positive, and complete")

    returns = np.log(close / close.shift(1)).dropna().to_numpy(dtype=float)
    initial = int(len(returns) * train_fraction)
    remaining = len(returns) - initial
    if initial < minimum_samples or remaining < folds * minimum_samples:
        return {
            "status": "INSUFFICIENT SAMPLE",
            "detail": "Not enough observations for the requested chronological folds",
            "fold_count": 0,
            "requested_folds": folds,
            "observations": int(len(returns)),
            "folds": [],
            "scope": "distribution stability only; not predictive performance or profitability",
        }

    chunks = np.array_split(returns[initial:], folds)
    results = []
    for index, test in enumerate(chunks):
        train_end = initial + sum(len(chunk) for chunk in chunks[:index])
        train = returns[:train_end]
        if len(train) < minimum_samples or len(test) < minimum_samples:
            continue
        train_vol = float(np.std(train, ddof=1) * 100)
        test_vol = float(np.std(test, ddof=1) * 100)
        results.append({
            "fold": index + 1,
            "train_samples": int(len(train)),
            "test_samples": int(len(test)),
            "train_mean_return_pct": float(np.mean(train) * 100),
            "test_mean_return_pct": float(np.mean(test) * 100),
            "train_volatility_pct": train_vol,
            "test_volatility_pct": test_vol,
            "volatility_ratio": float(test_vol / train_vol) if train_vol > 0 else None,
        })

    if len(results) != folds:
        status = "INSUFFICIENT SAMPLE"
    else:
        status = "COMPLETED"
    return {
        "status": status,
        "detail": f"{len(results)}/{folds} chronological out-of-sample folds evaluated",
        "fold_count": len(results),
        "requested_folds": folds,
        "observations": int(len(returns)),
        "folds": results,
        "scope": "expanding-window distribution stability only; not predictive performance or profitability",
    }
