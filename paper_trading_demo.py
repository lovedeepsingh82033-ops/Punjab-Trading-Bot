"""Punjab AI Robot — refreshed visual scanner and paper-research dashboard.

This dashboard reads saved scanner files only. Auto-refresh reloads those files
when the existing scanner updates them; it does not create market data.
Market observations are descriptive, and the journal is hypothetical only.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

ROOT = Path(__file__).resolve().parent
HISTORY_PATH = ROOT / "signal_history.csv"
SNAPSHOT_PATH = ROOT / "bot_state.json"

st.set_page_config(
    page_title="Punjab AI Trading Robot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
:root { color-scheme: dark; }
.stApp {
  background: radial-gradient(ellipse at 12% 0%, #102b49 0%, #07111f 42%, #050b16 100%);
  color: #e8f0fb;
}
[data-testid="stSidebar"] { background: #091629; border-right: 1px solid #183657; }
.block-container { padding-top: 1rem; max-width: 1600px; padding-bottom: 2rem; }
h1, h2, h3 { color: #f4f8ff !important; }
div[data-testid="stMetric"] {
  background: linear-gradient(145deg, #10243a, #0a1728);
  border: 1px solid #1c3b5c; border-radius: 14px; padding: 12px 14px;
}
div[data-testid="stMetricLabel"] { color: #a9bdd5; }
div[data-testid="stMetricValue"] { color: #f4f8ff; }
.punjab-header {
  background: linear-gradient(100deg, #08182c, #102d49 55%, #071525);
  border: 1px solid #1e496d; border-radius: 18px;
  padding: 18px 22px; margin-bottom: 14px;
}
.brand { font-size: clamp(21px, 3vw, 29px); font-weight: 850; letter-spacing: .7px; color: #f8fbff; }
.brand span { color: #f4c542; }
.subbrand { color: #a9c1db; font-size: 12px; margin-top: 5px; }
.robot-wrap {
  background: radial-gradient(circle at 50% 28%, #103b49, #071a2a 66%);
  border: 1px solid #14634f; border-radius: 18px; padding: 18px;
  text-align: center; min-height: 245px;
}
.robot-orb {
  width: 100px; height: 100px; margin: 6px auto 12px; border-radius: 100%;
  border: 4px solid #18e68b; box-shadow: 0 0 28px rgba(24,230,139,.32);
  display: flex; align-items: center; justify-content: center;
  font-size: 52px; background: #082b36;
}
.robot-status { font-size: 22px; font-weight: 850; color: #24e995; }
.muted { color: #9bb0c7; font-size: 12px; }
.notice {
  border: 1px solid #8b672c; background: #302513; color: #ffe7b1;
  border-radius: 10px; padding: 11px 14px; margin: 8px 0 16px;
}
div.stButton > button[kind="primary"], div.stFormSubmitButton > button {
  background: linear-gradient(90deg, #087e58, #10b981); border: 0; color: white;
}
@media (max-width: 700px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; }
  .robot-wrap { min-height: 210px; }
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="punjab-header">
  <div class="brand">🐅 <span>PUNJAB AI</span> TRADING ROBOT</div>
  <div class="subbrand">SCANNER MONITOR &nbsp;•&nbsp; MARKET OBSERVATIONS &nbsp;•&nbsp; PAPER RESEARCH</div>
</div>
<div class="notice"><b>RESEARCH / DEMO MODE.</b> Market labels describe saved historical observations only.
The journal stores hypothetical examples entered by the user. No live trading, broker connection,
trade recommendations, or order execution is provided.</div>
""", unsafe_allow_html=True)


@st.cache_data(ttl=5, show_spinner=False)
def load_history(path: str, modified: float) -> pd.DataFrame:
    del modified
    try:
        df = pd.read_csv(path)
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()
    for col in ("signal_time", "recorded_at_utc", "evaluated_at"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
    numeric_cols = (
        "price", "rsi", "adx", "atr", "bull_score", "bear_score",
        "ema9", "ema21", "ema50", "ema200", "macd", "macd_signal", "macd_hist",
    )
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=5, show_spinner=False)
def load_snapshot(path: str, modified: float) -> dict:
    del modified
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def file_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def value_of(row, key: str, fmt: str = ".2f", fallback: str = "—") -> str:
    if row is None:
        return fallback
    val = row.get(key)
    if val is None or pd.isna(val):
        return fallback
    try:
        return format(float(val), fmt)
    except (TypeError, ValueError):
        return str(val)


with st.sidebar:
    st.markdown("## 🧭 Navigation")
    page = st.radio(
        "Dashboard section",
        ["Overview", "Scanner data", "Paper trading demo", "System information"],
        label_visibility="collapsed",
    )
    st.divider()
    st.markdown("### ⚙️ Display settings")
    auto_refresh = st.toggle("Auto-refresh dashboard", value=True)
    refresh_seconds = st.selectbox("Refresh interval", [15, 30, 60], index=1, format_func=lambda x: f"{x} seconds")
    if st.button("↻ Refresh now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.caption("Auto-refresh reloads saved files. It does not start the scanner or fetch live market prices.")

if auto_refresh:
    st_autorefresh(interval=refresh_seconds * 1000, limit=None, key="punjab_dashboard_refresh")

history = load_history(str(HISTORY_PATH), file_mtime(HISTORY_PATH)) if HISTORY_PATH.exists() else pd.DataFrame()
snapshot = load_snapshot(str(SNAPSHOT_PATH), file_mtime(SNAPSHOT_PATH)) if SNAPSHOT_PATH.exists() else {}

with st.sidebar:
    st.markdown("### 🔎 Scanner filters")
    symbols = sorted(history["symbol"].dropna().astype(str).unique()) if "symbol" in history.columns else []
    frames = sorted(history["timeframe"].dropna().astype(str).unique()) if "timeframe" in history.columns else []
    symbol_options = ["All"] + symbols
    frame_options = ["All"] + frames
    default_symbol = symbol_options.index("XAU/USD") if "XAU/USD" in symbol_options else 0
    default_frame = frame_options.index("H1") if "H1" in frame_options else 0
    selected_symbol = st.selectbox("Instrument", symbol_options, index=default_symbol)
    selected_frame = st.selectbox("Timeframe", frame_options, index=default_frame)

filtered = history.copy()
if selected_symbol != "All" and "symbol" in filtered.columns:
    filtered = filtered[filtered["symbol"].astype(str) == selected_symbol]
if selected_frame != "All" and "timeframe" in filtered.columns:
    filtered = filtered[filtered["timeframe"].astype(str) == selected_frame]

time_col = next((c for c in ("recorded_at_utc", "signal_time", "evaluated_at") if c in filtered.columns), None)
latest = filtered.sort_values(time_col, ascending=False, na_position="last") if time_col else filtered
latest_row = latest.iloc[0] if not latest.empty else None

freshness = "NO DATA"
fresh_detail = "No saved scanner observations found."
age_hours = None
if latest_row is not None and time_col and pd.notna(latest_row.get(time_col)):
    age_hours = max(0.0, (datetime.now(timezone.utc) - latest_row[time_col].to_pydatetime()).total_seconds() / 3600)
    freshness = "RECENT" if age_hours <= 1 else ("AGING" if age_hours <= 24 else "STALE")
    fresh_detail = f"Last saved observation: {latest_row[time_col].strftime('%Y-%m-%d %H:%M UTC')} · {age_hours:.1f} hours ago"

direction = str(latest_row.get("direction", "UNKNOWN")).upper() if latest_row is not None else "WAITING"
if direction not in {"UP", "DOWN", "BULLISH", "BEARISH", "NEUTRAL", "RANGE", "UNKNOWN"}:
    direction = "OBSERVATION"

if page == "Overview":
    st.markdown("### 📡 Market overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Instrument", str(latest_row.get("symbol", "—")) if latest_row is not None else "—")
    c2.metric("Last saved price", value_of(latest_row, "price", ".5f"))
    c3.metric("Market observation", direction)
    c4.metric("Data freshness", freshness)
    st.caption(fresh_detail)

    left, right = st.columns([1.7, 1])
    with left:
        st.markdown("### 📈 Recorded market history")
        if not filtered.empty and "price" in filtered.columns and time_col:
            chart_cols = [c for c in ("price", "ema9", "ema21", "ema50", "ema200") if c in filtered.columns]
            chart = filtered.dropna(subset=["price", time_col]).copy()
            chart = chart[chart["price"] > 0].sort_values(time_col)
            if not chart.empty:
                # Keep the price chart on one instrument/scale. Indicators are listed below.
                plot = chart.set_index(time_col)[["price"]].rename(columns={"price": "Saved price"})
                st.line_chart(plot, height=330, x_label="Recorded time (UTC)", y_label="Saved values")
            else:
                st.info("No valid positive saved prices are available for this filter.")
        else:
            st.info("Waiting for scanner history. Recorded prices will appear after the scanner writes signal_history.csv.")

    with right:
        st.markdown("### 🤖 Robot monitor")
        robot_text = "WAITING FOR DATA" if freshness == "NO DATA" else ("CHECK DATA AGE" if freshness in {"AGING", "STALE"} else "OBSERVING")
        st.markdown(f"""
        <div class="robot-wrap">
          <div class="robot-orb">🤖</div>
          <div class="robot-status">{robot_text}</div>
          <div class="muted">Saved-data monitor</div>
          <p class="muted">{fresh_detail}</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("**System checks**")
        for label, ok in [
            ("History file has records", not history.empty),
            ("Snapshot file available", bool(snapshot)),
            ("Latest observation recent", freshness == "RECENT"),
        ]:
            st.write(("🟢 " if ok else "🟡 ") + label)

    a, b, c, d = st.columns(4)
    a.metric("RSI (14)", value_of(latest_row, "rsi"))
    b.metric("MACD", value_of(latest_row, "macd"))
    c.metric("EMA 50", value_of(latest_row, "ema50", ".5f"))
    d.metric("EMA 200", value_of(latest_row, "ema200", ".5f"))

    low, high = st.columns([1.2, 1])
    with low:
        st.markdown("### 🧪 Latest technical observations")
        if latest_row is not None:
            indicator_rows = [
                {"Indicator": label, "Recorded value": value_of(latest_row, key, ".5f")}
                for label, key in [
                    ("RSI (14)", "rsi"), ("ADX", "adx"), ("MACD", "macd"),
                    ("MACD signal", "macd_signal"), ("EMA 9", "ema9"),
                    ("EMA 21", "ema21"), ("EMA 50", "ema50"), ("EMA 200", "ema200"),
                ]
            ]
            st.dataframe(pd.DataFrame(indicator_rows), use_container_width=True, hide_index=True)
        else:
            st.info("Technical observations will appear when scanner data is saved.")
    with high:
        st.markdown("### 🕒 Recent scanner activity")
        if not latest.empty:
            show_cols = [x for x in ("recorded_at_utc", "signal_time", "symbol", "timeframe", "direction", "price") if x in latest.columns]
            st.dataframe(latest[show_cols].head(10), use_container_width=True, hide_index=True)
        else:
            st.info("No scanner activity has been recorded.")

elif page == "Scanner data":
    st.markdown("### 🔎 Scanner observations")
    st.caption("Read-only historical scanner output. Direction labels describe recorded data; they are not instructions.")
    if filtered.empty:
        st.warning("No scanner records found. The existing scanner workflow must create signal_history.csv.")
    else:
        st.metric("Matching observations", f"{len(filtered):,}")
        st.dataframe(latest.head(300), use_container_width=True, hide_index=True)
        st.download_button(
            "Download filtered observations (CSV)",
            filtered.to_csv(index=False).encode("utf-8"),
            "punjab_scanner_observations.csv",
            "text/csv",
            use_container_width=True,
        )

elif page == "Paper trading demo":
    st.markdown("### 🧾 Manual paper-research journal")
    st.caption("Hypothetical learning records only. No market recommendation, broker connection, or real order.")
    if "paper_records" not in st.session_state:
        st.session_state.paper_records = []
    with st.form("paper_record_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            demo_symbol = st.selectbox("Example instrument", ["XAU/USD", "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD"])
            example_side = st.radio("Example scenario", ["BUY", "SELL"], horizontal=True)
        with c2:
            entry = st.number_input("Example entry value", min_value=0.0, value=1.0, format="%.5f")
            review = st.number_input("Example review value", min_value=0.0, value=1.0, format="%.5f")
        with c3:
            units = st.number_input("Demo units", min_value=0.01, value=1.0, step=0.1)
            note = st.text_input("Optional note")
        save = st.form_submit_button("Save hypothetical example", type="primary", use_container_width=True)
    if save:
        if entry <= 0 or review <= 0:
            st.error("Enter example values greater than zero.")
        else:
            difference = (review - entry) if example_side == "BUY" else (entry - review)
            st.session_state.paper_records.insert(0, {
                "Recorded UTC": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "Instrument": demo_symbol,
                "Scenario": example_side,
                "Example entry": entry,
                "Review value": review,
                "Demo units": units,
                "Hypothetical difference": difference * units,
                "Outcome": "Positive" if difference > 0 else ("Negative" if difference < 0 else "Flat"),
                "Note": note,
            })
            st.success("Hypothetical example saved in this session.")
    records = st.session_state.paper_records
    if records:
        journal = pd.DataFrame(records)
        x, y, z = st.columns(3)
        x.metric("Demo records", len(journal))
        y.metric("Hypothetical total", f"{journal['Hypothetical difference'].sum():.5f}")
        z.metric("Positive examples", int((journal["Outcome"] == "Positive").sum()))
        st.dataframe(journal, use_container_width=True, hide_index=True)
        st.download_button("Download demo journal (CSV)", journal.to_csv(index=False).encode("utf-8"),
                           "punjab_paper_journal.csv", "text/csv")
    else:
        st.info("The example journal is empty. Add a hypothetical example to test the calculations.")
    if st.button("Clear this session's journal"):
        st.session_state.paper_records = []
        st.rerun()

else:
    st.markdown("### ⚙️ System information")
    st.write("**Dashboard:** Punjab AI Trading Robot")
    st.write("**Mode:** Saved scanner observations + manual hypothetical journal")
    st.write("**Auto-refresh:**", f"On · every {refresh_seconds}s" if auto_refresh else "Off")
    st.write("**History file:**", "Found" if HISTORY_PATH.exists() else "Not found")
    st.write("**Snapshot file:**", "Found" if SNAPSHOT_PATH.exists() else "Not found")
    st.write("**Rows loaded:**", f"{len(history):,}")
    st.write("**Latest data status:**", freshness)
    for label, path in (("History file", HISTORY_PATH), ("Snapshot file", SNAPSHOT_PATH)):
        if path.exists():
            modified_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            st.write(f"**{label} updated (UTC):**", modified_at.strftime("%Y-%m-%d %H:%M:%S"))
    st.info("Important: this dashboard does not run the scanner. Auto-refresh only displays new records after the separate scanner process updates the saved files.")
    if snapshot:
        st.markdown("#### Latest saved scanner snapshot")
        st.json(snapshot)
    else:
        st.info("No bot_state.json snapshot is available in this app's current filesystem.")

st.divider()
st.caption(
    "Punjab AI Robot · Educational research dashboard only. Historical observations are not forecasts. "
    "The journal uses user-entered hypothetical values, is session-only, and excludes real-world execution costs."
)
