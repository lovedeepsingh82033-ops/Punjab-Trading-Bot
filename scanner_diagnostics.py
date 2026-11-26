"""Read-only diagnostics for saved scanner observations.

This module summarizes historical scanner output. It does not create signals,
rank instruments, predict prices, or provide trading recommendations.
"""
import pandas as pd


def build_scanner_diagnostics(history):
    """Summarize saved observations by direction, instrument, and timeframe."""
    if not isinstance(history, pd.DataFrame):
        raise TypeError("history must be a pandas DataFrame")

    result = {
        "total_rows": int(len(history)),
        "directional_rows": 0,
        "neutral_rows": 0,
        "unknown_rows": 0,
        "by_symbol": [],
        "by_timeframe": [],
        "scope": "saved historical observations only",
    }
    if history.empty:
        return result

    if "direction" not in history.columns:
        directions = pd.Series("UNKNOWN", index=history.index, dtype="object")
    else:
        directions = (
            history["direction"].fillna("UNKNOWN").astype(str).str.strip().str.upper()
        )
        directions = directions.replace({"UP": "BULLISH", "DOWN": "BEARISH", "": "UNKNOWN"})

    result["directional_rows"] = int(directions.isin(["BULLISH", "BEARISH"]).sum())
    result["neutral_rows"] = int((directions == "NEUTRAL").sum())
    result["unknown_rows"] = int(
        (~directions.isin(["BULLISH", "BEARISH", "NEUTRAL"])).sum()
    )

    for column, target in (("symbol", "by_symbol"), ("timeframe", "by_timeframe")):
        if column not in history.columns:
            continue
        labels = history[column].fillna("UNKNOWN").astype(str).str.strip()
        labels = labels.replace("", "UNKNOWN")
        grouped = pd.DataFrame({"label": labels, "direction": directions}).groupby(
            "label", sort=True
        )
        rows = []
        for label, group in grouped:
            group_directions = group["direction"]
            rows.append({
                "name": str(label),
                "total": int(len(group)),
                "bullish": int((group_directions == "BULLISH").sum()),
                "bearish": int((group_directions == "BEARISH").sum()),
                "neutral": int((group_directions == "NEUTRAL").sum()),
                "unknown": int((~group_directions.isin(
                    ["BULLISH", "BEARISH", "NEUTRAL"]
                )).sum()),
            })
        result[target] = rows

    return result
