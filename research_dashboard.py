"""Compact, descriptive dashboard for completed scanner research results."""


def advanced_research_dashboard(scan_results, correlation_by_timeframe,
                                calendar_context=None, scanner_health=None):
    results = list(scan_results or [])
    regime_counts = {}
    volatility_counts = {}
    quality_counts = {}
    anomaly_count = 0
    timeframe_counts = {}
    for item in results:
        regime = item.get("market_regime", {}).get("label", "UNKNOWN")
        volatility = item.get("volatility", {}).get("regime", "UNKNOWN")
        quality = item.get("data_quality", {}).get("status", "UNKNOWN")
        regime_counts[regime] = regime_counts.get(regime, 0) + 1
        volatility_counts[volatility] = volatility_counts.get(volatility, 0) + 1
        quality_counts[quality] = quality_counts.get(quality, 0) + 1
        timeframe = item.get("timeframe", "UNKNOWN")
        timeframe_counts[timeframe] = timeframe_counts.get(timeframe, 0) + 1
        if item.get("anomaly_research", {}).get("status") == "UNUSUAL OBSERVATION":
            anomaly_count += 1

    def compact(mapping):
        return ", ".join(f"{key}: {mapping[key]}" for key in sorted(mapping)) or "No data"

    correlation_lines = []
    for timeframe in sorted(correlation_by_timeframe or {}):
        pairs = correlation_by_timeframe[timeframe].get("pairs", [])[:3]
        if pairs:
            rendered = "; ".join(
                f"{p['symbol_a']}/{p['symbol_b']} {p['correlation']:+.2f} (n={p['samples']})"
                for p in pairs
            )
        else:
            rendered = "Insufficient aligned history"
        correlation_lines.append(f"{timeframe}: {rendered}")

    calendar = calendar_context or {"status": "NOT CONFIGURED", "events": [], "count": 0}
    calendar_lines = [
        f"{event['event_time_utc']} {event['currency']} [{event['impact']}] {event['event']} — {event['source']}"
        for event in calendar.get("events", [])[:8]
    ]
    health = scanner_health or {"status": "UNKNOWN", "completion_pct": 0.0}
    return {
        "analyses": len(results),
        "regimes": compact(regime_counts),
        "volatility": compact(volatility_counts),
        "data_quality": compact(quality_counts),
        "timeframes": compact(timeframe_counts),
        "anomalies": anomaly_count,
        "correlations": correlation_lines or ["No correlation data"],
        "calendar_status": calendar.get("status", "UNKNOWN"),
        "calendar_count": calendar.get("count", 0),
        "calendar_events": calendar_lines or ["No matching events loaded"],
        "calendar_note": calendar.get("message", ""),
        "scanner_health": health.get("status", "UNKNOWN"),
        "completion_pct": float(health.get("completion_pct", 0.0)),
        "scope": "descriptive research dashboard; no forecast or trading instruction",
    }


def format_research_dashboard(dashboard):
    lines = [
        "<b>Advanced Research Dashboard</b>",
        f"Analyses included: {dashboard['analyses']}",
        f"Scanner health: {dashboard['scanner_health']} ({dashboard['completion_pct']:.1f}% complete)",
        f"Market regimes: {dashboard['regimes']}",
        f"Volatility regimes: {dashboard['volatility']}",
        f"Data quality: {dashboard['data_quality']}",
        f"Timeframe coverage: {dashboard['timeframes']}",
        f"Unusual historical observations: {dashboard['anomalies']}",
        "",
        "<b>Cross-Market Correlation</b>",
        *dashboard["correlations"],
        "",
        f"<b>Economic Calendar: {dashboard['calendar_status']}</b>",
        f"Matching events in window: {dashboard['calendar_count']}",
        *dashboard["calendar_events"],
        dashboard["calendar_note"],
        "",
        "<i>Descriptive research only. Correlation is not causation; historical outliers are not forecasts. No trading instructions or orders.</i>",
    ]
    return "\n".join(lines)
