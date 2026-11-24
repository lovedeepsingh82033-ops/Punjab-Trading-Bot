"""Unified, non-directional intelligence layer for scanner research reports.

This module combines existing diagnostics into one operational research brief.
It is deterministic Python analytics, not an autonomous AI model, forecast, or
trade execution system.
"""


def build_intelligence_hub(dashboard, scan_results, scanner_health,
                           calendar_context=None):
    """Combine existing scanner outputs and produce prioritized diagnostics."""
    dashboard = dashboard or {}
    results = list(scan_results or [])
    health = scanner_health or {}
    calendar = calendar_context or {}

    quality_counts = {}
    regime_counts = {}
    volatility_counts = {}
    anomaly_count = 0
    walk_forward_counts = {}
    for item in results:
        quality = item.get("data_quality", {}).get("status", "UNKNOWN")
        regime = item.get("market_regime", {}).get("label", "UNKNOWN")
        volatility = item.get("volatility", {}).get("regime", "UNKNOWN")
        quality_counts[quality] = quality_counts.get(quality, 0) + 1
        regime_counts[regime] = regime_counts.get(regime, 0) + 1
        volatility_counts[volatility] = volatility_counts.get(volatility, 0) + 1
        if item.get("anomaly_research", {}).get("status") == "UNUSUAL OBSERVATION":
            anomaly_count += 1
        walk = item.get("walk_forward", {})
        if walk:
            status = walk.get("status", "UNKNOWN")
            walk_forward_counts[status] = walk_forward_counts.get(status, 0) + 1

    findings = []
    recommendations = []

    health_status = health.get("status", "UNKNOWN")
    if health_status in {"DEGRADED", "NO DATA", "PARTIAL", "NO TARGETS"}:
        findings.append("Scanner operations require attention: " + str(health_status))
        recommendations.append(
            "Review API availability, processing errors, and incomplete analyses before relying on this report."
        )

    failed_quality = quality_counts.get("FAIL", 0)
    warning_quality = quality_counts.get("WARNING", 0)
    if failed_quality:
        findings.append(f"Data integrity failures: {failed_quality} analysis result(s)")
        recommendations.append(
            "Inspect rejected candle data and upstream timestamps; keep failed datasets out of research comparisons."
        )
    if warning_quality:
        findings.append(f"Data quality warnings: {warning_quality} analysis result(s)")
        recommendations.append(
            "Review duplicate, missing, stale, or out-of-order candle observations."
        )

    if anomaly_count:
        findings.append(f"Unusual historical observations: {anomaly_count}")
        recommendations.append(
            "Inspect flagged observations against the source data; an outlier is not a forecast."
        )

    calendar_status = calendar.get("status", dashboard.get("calendar_status", "UNKNOWN"))
    if calendar_status == "NOT CONFIGURED":
        findings.append("Economic calendar source is not configured")
        recommendations.append(
            "Only add dated events from trusted, source-attributed references; no live feed is currently connected."
        )

    if not dashboard.get("correlations"):
        findings.append("Cross-market correlation context is unavailable")
    elif all("Insufficient" in str(line) for line in dashboard.get("correlations", [])):
        findings.append("Cross-market history is insufficient for correlation estimates")

    if walk_forward_counts.get("INSUFFICIENT SAMPLE", 0):
        findings.append(
            f"Walk-forward validation has insufficient samples in {walk_forward_counts['INSUFFICIENT SAMPLE']} analysis result(s)"
        )
        recommendations.append(
            "Collect more valid completed-candle history before interpreting stability diagnostics."
        )

    if not findings:
        findings.append("No priority operational or data-quality issue detected in the supplied scan results.")
    if not recommendations:
        recommendations.append(
            "Continue monitoring data quality and validation coverage; a healthy scan does not imply predictive accuracy."
        )

    return {
        "analyses": len(results),
        "scanner_health": health_status,
        "completion_pct": float(health.get("completion_pct", 0.0)),
        "quality_counts": quality_counts,
        "regime_counts": regime_counts,
        "volatility_counts": volatility_counts,
        "anomaly_count": anomaly_count,
        "walk_forward_counts": walk_forward_counts,
        "calendar_status": calendar_status,
        "calendar_events": int(calendar.get("count", dashboard.get("calendar_count", 0)) or 0),
        "findings": findings[:8],
        "recommendations": recommendations[:8],
        "scope": "combined descriptive research and operational diagnostics; no forecast, trading instruction, or order execution",
    }


def format_intelligence_hub(report):
    """Render a compact Telegram-safe text report."""
    lines = [
        "<b>Punjab AI Intelligence Hub</b>",
        f"Analyses reviewed: {report['analyses']}",
        f"Scanner health: {report['scanner_health']} ({report['completion_pct']:.1f}% complete)",
        f"Data quality: {', '.join(f'{key}={value}' for key, value in sorted(report['quality_counts'].items())) or 'No data'}",
        f"Market regimes: {', '.join(f'{key}={value}' for key, value in sorted(report['regime_counts'].items())) or 'No data'}",
        f"Volatility regimes: {', '.join(f'{key}={value}' for key, value in sorted(report['volatility_counts'].items())) or 'No data'}",
        f"Unusual observations: {report['anomaly_count']}",
        f"Walk-forward status: {', '.join(f'{key}={value}' for key, value in sorted(report['walk_forward_counts'].items())) or 'Not supplied'}",
        f"Economic calendar: {report['calendar_status']} ({report['calendar_events']} matching events)",
        "",
        "<b>Priority Findings</b>",
    ]
    lines.extend(f"• {finding}" for finding in report["findings"])
    lines.extend(["", "<b>Research / Maintenance Notes</b>"])
    lines.extend(f"• {note}" for note in report["recommendations"])
    lines.extend([
        "",
        "<i>Deterministic research aggregation, not an autonomous AI model. Descriptive only; no forecasts, buy/sell instructions, or orders.</i>"
    ])
    return "\n".join(lines)
