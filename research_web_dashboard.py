"""Read-only local web dashboard for Punjab Market Scanner research data.

This interface displays historical observations and scanner snapshots only.
It has no broker integration, order controls, or live trade execution.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
HISTORY_PATH = ROOT / "signal_history.csv"
SNAPSHOT_PATH = ROOT / "bot_state.json"

st.set_page_config(
    page_title="Punjab Market Research Dashboard",
    page_icon="📊",
    layout="wide",
)

st.markdown(
    """
    <style>
      .stApp { background: #0b1220; color: #e5e7eb; }
      [data-testid="stSidebar"] { background: #111b2d; }
      div[data-testid="stMetric"] {
        background: #142238; border: 1px solid #263852;
        padding: 14px; border-radius: 12px;
      }
      .notice {
        padding: 12px 16px; border-radius: 10px;
        background: #172b3d; border: 1px solid #31516a;
        color: #dbeafe; margin-bottom: 16px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📊 PUNJAB MARKET RESEARCH")
st.caption("Read-only scanner dashboard · Historical observations · Paper research")

st.markdown(
    '<div class="notice"><b>Research mode only.</b> Labels describe recorded '
    'market observations, not instructions to buy, sell, or place an order. '
    'No broker connection or order execution is available.</div>',
    unsafe_allow_html=True,
)

@st.cache_data(ttl=30)
def load_history(path: str, modified: float) -> pd.DataFrame:
    del modified
    frame = pd.read_csv(path)
    for column in ("signal_time", "recorded_at_utc", "evaluated_at"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce", utc=True)
    for column in ("price", "rsi", "adx", "bull_score", "bear_score", "outcome_pct"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame

@st.cache_data(ttl=15)
def load_snapshot(path: str, modified: float):
    del modified
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

if not HISTORY_PATH.exists():
    st.warning("signal_history.csv was not found. Run the scanner first.")
    st.stop()

history = load_history(str(HISTORY_PATH), HISTORY_PATH.stat().st_mtime)
snapshot = (
    load_snapshot(str(SNAPSHOT_PATH), SNAPSHOT_PATH.stat().st_mtime)
    if SNAPSHOT_PATH.exists() else {}
)

st.sidebar.header("Research filters")
symbols = sorted(history["symbol"].dropna().astype(str).unique()) if "symbol" in history else []
frames = sorted(history["timeframe"].dropna().astype(str).unique()) if "timeframe" in history else []
selected_symbol = st.sidebar.selectbox("Market pair / instrument", ["All"] + symbols)
selected_frame = st.sidebar.selectbox("Timeframe", ["All"] + frames)
view = st.sidebar.selectbox(
    "Research view",
    ["Technical observations", "Multi-timeframe records", "Historical outcomes"],
)

filtered = history.copy()
if selected_symbol != "All":
    filtered = filtered[filtered["symbol"].astype(str) == selected_symbol]
if selected_frame != "All":
    filtered = filtered[filtered["timeframe"].astype(str) == selected_frame]

if view == "Multi-timeframe records" and "mtf_cohort" in filtered:
    filtered = filtered[filtered["mtf_cohort"].astype(str) != "LEGACY_UNKNOWN"]
elif view == "Historical outcomes" and "outcome_status" in filtered:
    filtered = filtered[filtered["outcome_status"].isin(["CORRECT", "INCORRECT"])]

latest = filtered.sort_values("recorded_at_utc", ascending=False) if "recorded_at_utc" in filtered else filtered
latest_rows = latest.head(12)

total = len(filtered)
resolved = filtered[filtered["outcome_status"].isin(["CORRECT", "INCORRECT"])] if "outcome_status" in filtered else filtered.iloc[0:0]
correct = int((resolved["outcome_status"] == "CORRECT").sum()) if len(resolved) else 0
accuracy = (correct / len(resolved) * 100) if len(resolved) else None

c1, c2, c3, c4 = st.columns(4)
c1.metric("Recorded observations", f"{total:,}")
c2.metric("Resolved historical samples", f"{len(resolved):,}")
c3.metric("Historical outcome ratio", f"{accuracy:.1f}%" if accuracy is not None else "N/A")
c4.metric("Scanner snapshot", "Available" if snapshot else "Not found")

st.subheader("Latest market observations")
if latest_rows.empty:
    st.info("No records match these filters.")
else:
    display_columns = [
        c for c in (
            "symbol", "timeframe", "signal_time", "direction", "price",
            "rsi", "adx", "bull_score", "bear_score", "outcome_status",
        ) if c in latest_rows.columns
    ]
    st.dataframe(latest_rows[display_columns], use_container_width=True, hide_index=True)

if "price" in filtered and "signal_time" in filtered:
    chart_data = filtered.dropna(subset=["price", "signal_time"]).sort_values("signal_time")
    if not chart_data.empty:
        st.subheader("Recorded price history")
        chart_data = chart_data.set_index("signal_time")
        st.line_chart(chart_data["price"], height=260)

if snapshot:
    st.subheader("Latest scanner snapshot")
    st.write("Generated:", snapshot.get("generated_at", "Unknown"))
    health = snapshot.get("scanner_health", {})
    if isinstance(health, dict) and health:
        st.json(health)
    observations = snapshot.get("observations", [])
    if observations:
        st.dataframe(pd.DataFrame(observations), use_container_width=True, hide_index=True)

st.caption(
    "Historical results are descriptive, may contain incomplete or legacy records, "
    "and do not predict future market behaviour. This dashboard is not financial advice."
)
