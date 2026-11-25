"""Aggregated quantitative research diagnostics for Punjab Scanner.

Descriptive research only: this module does not forecast prices, create trade
recommendations, alter existing signal rules, or place orders.
"""


def _count(items, key, fallback="UNKNOWN"):
    counts = {}
    for item in items:
        value = item.get(key, fallback)
        counts[value] = counts.get(value, 0) + 1
    return counts


def build_quant_intelligence(scan_results):
    """Aggregate the scanner's existing diagnostics without changing them."""
    results = list(scan_results or [])
    quality = _count([x.get("data_quality", {}) for x in results], "status")
    regimes = _count([x.get("market_regime", {}) for x in results], "label")
    volatility = _count([x.get("volatility", {}) for x in results], "regime")
    integrity = _count([x.get("algorithmic_system", {}) for x in results], "status")
    validation = _count([x.get("validation", {}) for x in results], "status")
    walk_forward = _count([x.get("walk_forward", {}) for x in results], "status")

    drawdowns = []
    anomalies = 0
    for item in results:
        value = item.get("risk_context", {}).get("max_drawdown_pct")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            drawdowns.append(float(value))
        if item.get("anomaly_research", {}).get("status") == "UNUSUAL OBSERVATION":
            anomalies += 1

    findings = []
    if quality.get("FAIL", 0):
        findings.append(f"Data-quality failures: {quality['FAIL']}")
    if integrity.get("WARNING", 0):
        findings.append(f"Data-integrity warnings: {integrity['WARNING']}")
    if validation.get("INSUFFICIENT SAMPLE", 0):
        findings.append(f"Holdout samples insufficient: {validation['INSUFFICIENT SAMPLE']}")
    if walk_forward.get("INSUFFICIENT SAMPLE", 0):
        findings.append(f"Walk-forward samples insufficient: {walk_forward['INSUFFICIENT SAMPLE']}")
    if anomalies:
        findings.append(f"Unusual historical observations: {anomalies}")
    if not findings:
        findings.append("No priority data-quality or sample-size issue detected.")

    return {
        "markets_reviewed": len(results),
        "data_quality": quality,
        "market_regimes": regimes,
        "volatility_regimes": volatility,
        "algorithmic_integrity": integrity,
        "holdout_validation": validation,
        "walk_forward": walk_forward,
        "unusual_observations": anomalies,
        "worst_historical_drawdown_pct": max(drawdowns) if drawdowns else None,
        "findings": findings[:8],
    }


def format_quant_intelligence(report):
    """Format aggregate diagnostics for the existing Telegram report channel."""
    def counts(values):
        return ", ".join(f"{key}: {value}" for key, value in sorted(values.items())) or "No data"

    drawdown = report.get("worst_historical_drawdown_pct")
    drawdown_text = f"{drawdown:.2f}%" if drawdown is not None else "No data"
    lines = [
        "<b>Punjab Quant Intelligence</b>",
        f"Markets/timeframes reviewed: {report.get('markets_reviewed', 0)}",
        f"Data quality: {counts(report.get('data_quality', {}))}",
        f"Market regimes: {counts(report.get('market_regimes', {}))}",
        f"Volatility regimes: {counts(report.get('volatility_regimes', {}))}",
        f"Data integrity: {counts(report.get('algorithmic_integrity', {}))}",
        f"Holdout validation: {counts(report.get('holdout_validation', {}))}",
        f"Walk-forward: {counts(report.get('walk_forward', {}))}",
        f"Unusual observations: {report.get('unusual_observations', 0)}",
        f"Worst historical drawdown in reviewed samples: {drawdown_text}",
        "",
        "<b>Research findings</b>",
    ]
    lines.extend(f"• {finding}" for finding in report.get("findings", []))
    lines.extend(["", "<i>Historical diagnostics only; not a forecast or trading instruction.</i>"])
    return "\n".join(lines)
