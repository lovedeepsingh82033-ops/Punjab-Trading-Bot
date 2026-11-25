"""Read-only Streamlit dashboard for historical Punjab Market Scanner research data."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
HISTORY_PATH = ROOT / "signal_history.csv"
SNAPSHOT_PATH = ROOT / "bot_state.json"

st.set_page_config(page_title="Punjab Market Research Dashboard", page_icon="📊", layout="wide")
st.markdown("""
<style>
.stApp { background: #0b1220; color: #e5e7eb; }
[data-testid="stSidebar"] { background: #111b2d; }
div[data-testid="stMetric"] { background: #142238; border: 1px solid #263852; padding: 14px; border-radius: 12px; }
.notice { padding: 12px 16px; border-radius: 10px; background: #172b3d; border: 1px solid #31516a; color: #dbeafe; margin-bottom: 16px; }
</style>
""", unsafe_allow_html=True)

st.title("📊 PUNJAB MARKET RESEARCH")
st.caption("Read-only scanner dashboard · Historical observations · Paper research")
st.markdown('<div class="notice"><b>Research mode only.</b> Labels describe recorded market observations, not instructions to buy, sell, or place an order. No broker connection or order execution is available.</div>', unsafe_allow_html=True)

@st.cache_data(ttl=30)
def load_history(path: str, modified: float) -> pd.DataFrame:
    del modified
    frame = pd.read_csv(path)
    for col in ("signal_time", "recorded_at_utc", "evaluated_at"):
        if col in frame:
            frame[col] = pd.to_datetime(frame[col], errors="coerce", utc=True)
    for col in ("price", "rsi", "adx", "atr", "bull_score", "bear_score", "outcome_pct", "ema9", "ema21", "ema50", "macd", "macd_signal", "macd_hist"):
        if col in frame:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame

@st.cache_data(ttl=15)
def load_snapshot(path: str, modified: float):
    del modified
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

if not HISTORY_PATH.exists():
    st.warning("signal_history.csv was not found. Run the scanner to create history.")
    st.stop()

history = load_history(str(HISTORY_PATH), HISTORY_PATH.stat().st_mtime)
snapshot = load_snapshot(str(SNAPSHOT_PATH), SNAPSHOT_PATH.stat().st_mtime) if SNAPSHOT_PATH.exists() else {}

st.sidebar.header("Research filters")
symbols = sorted(history["symbol"].dropna().astype(str).unique()) if "symbol" in history else []
frames = sorted(history["timeframe"].dropna().astype(str).unique()) if "timeframe" in history else []
selected_symbol = st.sidebar.selectbox("Market pair / instrument", ["All"] + symbols)
selected_frame = st.sidebar.selectbox("Timeframe", ["All"] + frames)
view = st.sidebar.selectbox("Research view", ["Technical observations", "Multi-timeframe records", "Historical outcomes"])

filtered = history.copy()
if selected_symbol != "All" and "symbol" in filtered:
    filtered = filtered[filtered["symbol"].astype(str) == selected_symbol]
if selected_frame != "All" and "timeframe" in filtered:
    filtered = filtered[filtered["timeframe"].astype(str) == selected_frame]
if view == "Multi-timeframe records" and "mtf_cohort" in filtered:
    filtered = filtered[filtered["mtf_cohort"].astype(str) != "LEGACY_UNKNOWN"]
elif view == "Historical outcomes" and "outcome_status" in filtered:
    filtered = filtered[filtered["outcome_status"].isin(["CORRECT", "INCORRECT"])]

sort_col = "recorded_at_utc" if "recorded_at_utc" in filtered else "signal_time"
latest = filtered.sort_values(sort_col, ascending=False, na_position="last") if sort_col in filtered else filtered
latest_rows = latest.head(12)
resolved = filtered[filtered["outcome_status"].isin(["CORRECT", "INCORRECT"])] if "outcome_status" in filtered else filtered.iloc[0:0]
correct = int((resolved["outcome_status"] == "CORRECT").sum()) if len(resolved) else 0
accuracy = correct / len(resolved) * 100 if len(resolved) else None

last_record = pd.to_datetime(history["recorded_at_utc"], errors="coerce", utc=True).max() if "recorded_at_utc" in history else pd.NaT
if pd.notna(last_record):
    age_hours = max(0.0, (datetime.now(timezone.utc) - last_record.to_pydatetime()).total_seconds() / 3600)
    freshness = "Recent" if age_hours <= 1 else ("Aging" if age_hours <= 24 else "Stale")
    freshness_detail = f"{last_record.strftime('%Y-%m-%d %H:%M UTC')} · {age_hours:.1f} hours ago"
else:
    freshness, freshness_detail = "Unknown", "No valid recorded timestamp"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Recorded observations", f"{len(filtered):,}")
c2.metric("Resolved historical samples", f"{len(resolved):,}")
c3.metric("Historical outcome ratio", f"{accuracy:.1f}%" if accuracy is not None else "N/A")
c4.metric("Data freshness", freshness, help="Based on the newest recorded_at_utc value in the CSV")
st.caption(f"Last recorded observation: {freshness_detail}")
if freshness == "Stale":
    st.warning("The newest saved observation is over 24 hours old. This page shows historical records, not live market prices.")
elif freshness == "Aging":
    st.info("The newest saved observation is more than one hour old. Check the scanner's data collection process before treating it as current.")
elif freshness == "Unknown":
    st.warning("A reliable recorded timestamp is unavailable, so data freshness cannot be confirmed.")

st.subheader("Latest market observations")
if latest_rows.empty:
    st.info("No records match these filters.")
else:
    cols = [c for c in ("symbol", "timeframe", "signal_time", "direction", "price", "rsi", "macd", "macd_signal", "macd_hist", "adx", "bull_score", "bear_score", "outcome_status") if c in latest_rows]
    st.dataframe(latest_rows[cols], width="stretch", hide_index=True)

st.subheader("Recorded price history")
if "price" in filtered and "signal_time" in filtered:
    chart = filtered.dropna(subset=["price", "signal_time"]).copy()
    if not chart.empty:
        order = ["signal_time"] + (["recorded_at_utc"] if "recorded_at_utc" in chart else [])
        chart = chart.sort_values(order).drop_duplicates(subset=["signal_time"], keep="last")
        chart = chart.sort_values("signal_time").set_index("signal_time")
        st.line_chart(chart["price"], height=300, x_label="Signal time (UTC)", y_label="Recorded price")
        st.caption("One saved value per signal timestamp; timestamps are shown in UTC.")
    else:
        st.info("No valid price/time pairs are available for these filters.")
else:
    st.info("Price history requires price and signal_time columns.")

st.subheader("Technical indicator history")
indicators = [c for c in ("rsi", "macd", "macd_signal", "macd_hist") if c in filtered]
if indicators and "signal_time" in filtered:
    data = filtered.dropna(subset=["signal_time"]).sort_values("signal_time")
    data = data.drop_duplicates(subset=["signal_time"], keep="last").set_index("signal_time")
    for col in indicators:
        series = data[col].dropna()
        if not series.empty:
            st.markdown(f"**{col.upper()}**")
            st.line_chart(series, height=190, x_label="Signal time (UTC)")
        else:
            st.caption(f"{col.upper()}: no recorded values for this selection.")
else:
    st.info("RSI/MACD history is not present in the selected records.")

if snapshot:
    st.subheader("Latest scanner snapshot")
    st.write("Generated:", snapshot.get("generated_at", "Unknown"))
    health = snapshot.get("scanner_health", {})
    if isinstance(health, dict) and health:
        st.json(health)
    observations = snapshot.get("observations", [])
    if observations:
        st.dataframe(pd.DataFrame(observations), width="stretch", hide_index=True)

st.caption("Historical results are descriptive, may contain incomplete or legacy records, and do not predict future market behaviour. Data freshness refers to saved scanner records only. This dashboard is not financial advice.")
