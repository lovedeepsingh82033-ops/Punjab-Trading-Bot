"""Offline paper-simulation metrics; this module never places orders.

Inputs are hypothetical directional trade returns in percent, before costs.
Costs are a user-supplied round-trip percentage assumption, not broker quotes.
"""
from math import isfinite


def summarize_paper_returns(gross_returns_pct, round_trip_cost_pct=0.0,
                            minimum_samples=30):
    """Summarize hypothetical returns after an assumed per-trade cost.

    Returns percentage metrics and a sample-size warning. This is a research
    aid only: it does not estimate execution quality or predict future returns.
    """
    if isinstance(round_trip_cost_pct, bool) or not isinstance(
        round_trip_cost_pct, (int, float)
    ):
        raise ValueError("round_trip_cost_pct must be a finite non-negative number")
    if not isfinite(float(round_trip_cost_pct)) or round_trip_cost_pct < 0:
        raise ValueError("round_trip_cost_pct must be a finite non-negative number")
    if isinstance(minimum_samples, bool) or not isinstance(minimum_samples, int):
        raise ValueError("minimum_samples must be a positive integer")
    if minimum_samples < 1:
        raise ValueError("minimum_samples must be a positive integer")

    values = list(gross_returns_pct)
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("every return must be a finite number")
        if not isfinite(float(value)):
            raise ValueError("every return must be a finite number")
        if value <= -100:
            raise ValueError("a percentage return must be greater than -100")

    net = [float(value) - float(round_trip_cost_pct) for value in values]
    if any(not isfinite(value) or value <= -100 for value in net):
        raise ValueError(
            "every net return must be finite and greater than -100 after costs"
        )
    count = len(net)
    if not count:
        return {
            "samples": 0,
            "evidence_status": "NO DATA",
            "gross_total_return_pct": None,
            "net_total_return_pct": None,
            "net_expectancy_pct": None,
            "win_rate_pct": None,
            "profit_factor": None,
            "max_drawdown_pct": None,
            "net_returns_pct": [],
        }

    gross_equity = 1.0
    net_equity = 1.0
    peak_equity = 1.0
    max_drawdown = 0.0
    gross_wins = 0.0
    gross_losses = 0.0
    net_wins = 0
    net_profit = 0.0
    net_loss = 0.0

    for gross_value, net_value in zip(values, net):
        gross_equity *= 1.0 + float(gross_value) / 100.0
        net_equity *= 1.0 + net_value / 100.0
        peak_equity = max(peak_equity, net_equity)
        if peak_equity > 0:
            drawdown = (peak_equity - net_equity) / peak_equity * 100.0
            max_drawdown = max(max_drawdown, drawdown)

        if gross_value > 0:
            gross_wins += float(gross_value)
        elif gross_value < 0:
            gross_losses += abs(float(gross_value))
        if net_value > 0:
            net_wins += 1
            net_profit += net_value
        elif net_value < 0:
            net_loss += abs(net_value)

    profit_factor = (
        net_profit / net_loss if net_loss > 0 else None
    )
    return {
        "samples": count,
        "evidence_status": (
            "SAMPLE THRESHOLD MET"
            if count >= minimum_samples
            else f"INSUFFICIENT SAMPLE: {count}/{minimum_samples}"
        ),
        "gross_total_return_pct": (gross_equity - 1.0) * 100.0,
        "net_total_return_pct": (net_equity - 1.0) * 100.0,
        "net_expectancy_pct": sum(net) / count,
        "win_rate_pct": net_wins / count * 100.0,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_drawdown,
        "gross_winning_sum_pct": gross_wins,
        "gross_losing_sum_pct": gross_losses,
        "net_returns_pct": net,
    }
