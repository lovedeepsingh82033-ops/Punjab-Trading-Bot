"""Punjab AI Robot — refreshed visual scanner and paper-research dashboard.

This dashboard reads saved scanner files only. Auto-refresh reloads those files
when the existing scanner updates them; it does not create market data.
Market observations are descriptive, and the journal is hypothetical only.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from snapshot_bridge import download_snapshot

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
  background: radial-gradient(ellipse at 12% 0%, #173c5d 0%, #08182a 38%, #040a13 100%);
  color: #e8f0fb;
}
[data-testid="stSidebar"] { background: linear-gradient(180deg,#09182b,#06101d); border-right: 1px solid #214363; }
.block-container { padding-top: 1.1rem; max-width: 1700px; padding-bottom: 2.4rem; }
[data-testid="stVerticalBlockBorderWrapper"] { border-color: #21415e !important; }
div[data-testid="stDataFrame"] { border: 1px solid #1b3853; border-radius: 12px; overflow: hidden; }
hr { border-color: #1b3853 !important; }
[data-testid="stMetricDelta"] { display: none; }
h1, h2, h3 { color: #f4f8ff !important; }
div[data-testid="stMetric"] {
  background: linear-gradient(145deg, #10243a, #0a1728);
  border: 1px solid #1c3b5c; border-radius: 14px; padding: 12px 14px;
}
div[data-testid="stMetricLabel"] { color: #a9bdd5; }
div[data-testid="stMetricValue"] { color: #f4f8ff; }
.punjab-header {
  background: linear-gradient(100deg, #08182c, #102d49 55%, #071525);
  border: 1px solid #286087; border-radius: 20px;
  padding: 22px 24px; margin-bottom: 14px;
  box-shadow: 0 12px 38px rgba(0,0,0,.24);
}
.brand { font-size: clamp(21px, 3vw, 29px); font-weight: 850; letter-spacing: .7px; color: #f8fbff; }
.brand span { color: #f4c542; }
.subbrand { color: #a9c1db; font-size: 12px; margin-top: 5px; }
.robot-wrap {
  background: radial-gradient(circle at 50% 28%, #103b49, #071a2a 66%);
  border: 1px solid #1a8064; border-radius: 20px; padding: 20px;
  text-align: center; min-height: 265px;
  box-shadow: inset 0 0 35px rgba(20,190,130,.06), 0 12px 30px rgba(0,0,0,.18);
}
.robot-orb {
  width: 100px; height: 100px; margin: 6px auto 12px; border-radius: 100%;
  border: 3px solid #18e68b; box-shadow: 0 0 32px rgba(24,230,139,.4), inset 0 0 20px rgba(24,230,139,.12);
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
  <div class="subbrand">INTELLIGENCE CONSOLE &nbsp;•&nbsp; SCANNER MONITOR &nbsp;•&nbsp; PAPER RESEARCH</div>
  <div class="header-tags">
    <span class="header-tag gold">● RESEARCH / DEMO MODE</span>
    <span class="header-tag">XAU/USD WORKSPACE</span>
    <span class="header-tag">HISTORICAL DATA VIEW</span>
    <span class="header-tag">NO BROKER CONNECTION</span>
  </div>
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


def demo_signal_label(value) -> str:
    """Translate historical direction labels into clear demo-board labels."""
    raw = str(value or "").strip().upper()
    if raw in {"BULLISH", "UP", "BUY"}:
        return "BUY"
    if raw in {"BEARISH", "DOWN", "SELL"}:
        return "SELL"
    return "NEUTRAL"


with st.sidebar:
    st.markdown("## 🧭 Navigation")
    page = st.radio(
        "Dashboard section",
        ["Console", "Overview", "Scanner data", "Paper trading demo", "System information"],
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

# Streamlit Cloud runs separately from the scanner. Read the same private
# snapshot bridge credentials from Streamlit Secrets, then fetch the scanner's
# latest published snapshot. Never display an old snapshot as current.
for secret_name in ("BOT_STATE_BRIDGE_URL", "BOT_STATE_BRIDGE_KEY", "BOT_STATE_BRIDGE_BUCKET"):
    try:
        secret_value = st.secrets.get(secret_name, "")
    except Exception:
        secret_value = ""
    if secret_value and not os.getenv(secret_name):
        os.environ[secret_name] = str(secret_value).strip()

snapshot = {}
snapshot_source = "MISSING"
snapshot_error = ""
try:
    snapshot = download_snapshot() or {}
    if snapshot:
        snapshot_source = "REMOTE BRIDGE"
except Exception as exc:
    # Keep credentials, URLs, and provider response bodies out of the UI.
    snapshot_error = type(exc).__name__

if not snapshot and SNAPSHOT_PATH.exists():
    snapshot = load_snapshot(str(SNAPSHOT_PATH), file_mtime(SNAPSHOT_PATH))
    if snapshot:
        snapshot_source = "LOCAL FILE"

snapshot_age_hours = None
snapshot_time = snapshot.get("generated_at") if snapshot else None
if snapshot_time:
    try:
        parsed_snapshot_time = pd.to_datetime(snapshot_time, utc=True, errors="coerce")
        if pd.notna(parsed_snapshot_time):
            snapshot_age_hours = max(
                0.0,
                (datetime.now(timezone.utc) - parsed_snapshot_time.to_pydatetime()).total_seconds() / 3600,
            )
    except (TypeError, ValueError):
        snapshot_age_hours = None

snapshot_status = "MISSING"
if snapshot:
    snapshot_status = "AVAILABLE"
    if snapshot_age_hours is not None and snapshot_age_hours > 24:
        snapshot_status = "STALE"

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

# The board displays every directional observation already saved by the scanner.
# It does not invent signals or relax the scanner's validation rules.
signal_view = filtered.copy()
if not signal_view.empty:
    source_direction = signal_view["direction"] if "direction" in signal_view.columns else signal_view.get("signal", pd.Series(index=signal_view.index, dtype=object))
    signal_view["demo_signal"] = source_direction.map(demo_signal_label)
    signal_view = signal_view[signal_view["demo_signal"].isin(["BUY", "SELL"])].copy()
    if time_col:
        signal_view = signal_view.sort_values(time_col, ascending=False, na_position="last")
buy_count = int((signal_view["demo_signal"] == "BUY").sum()) if not signal_view.empty else 0
sell_count = int((signal_view["demo_signal"] == "SELL").sum()) if not signal_view.empty else 0

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

if page == "Console":
    st.markdown("### 🟢🔴 DEMO BUY / SELL SIGNAL BOARD")
    st.caption("Historical scanner observations only · labels are educational, not trading instructions. Only signals actually saved by the scanner are shown.")
    sb1, sb2, sb3 = st.columns(3)
    sb1.metric("BUY observations", f"{buy_count:,}")
    sb2.metric("SELL observations", f"{sell_count:,}")
    sb3.metric("TOTAL directional", f"{buy_count + sell_count:,}")
    if not signal_view.empty and "timeframe" in signal_view.columns:
        st.markdown("**Historical BUY / SELL count by timeframe**")
        timeframe_counts = signal_view.pivot_table(index="timeframe", columns="demo_signal", values="symbol" if "symbol" in signal_view.columns else "demo_signal", aggfunc="count", fill_value=0)
        for label in ("BUY", "SELL"):
            if label not in timeframe_counts.columns:
                timeframe_counts[label] = 0
        timeframe_counts = timeframe_counts[["BUY", "SELL"]].sort_index()
        st.dataframe(timeframe_counts, use_container_width=True)
    if not signal_view.empty and "symbol" in signal_view.columns:
        with st.expander("Breakdown by instrument"):
            symbol_counts = signal_view.pivot_table(index="symbol", columns="demo_signal", values="timeframe" if "timeframe" in signal_view.columns else "demo_signal", aggfunc="count", fill_value=0)
            for label in ("BUY", "SELL"):
                if label not in symbol_counts.columns:
                    symbol_counts[label] = 0
            st.dataframe(symbol_counts[["BUY", "SELL"]].sort_index(), use_container_width=True)
    if not signal_view.empty:
        signal_cols = [c for c in (time_col, "symbol", "timeframe", "demo_signal", "price", "rsi", "adx", "bull_score", "bear_score") if c and c in signal_view.columns]
        st.dataframe(signal_view[signal_cols].head(100).rename(columns={"demo_signal": "DEMO SIGNAL"}), use_container_width=True, hide_index=True)
        st.caption(f"Showing up to 100 of {len(signal_view):,} saved BUY/SELL observations across the selected filters.")
    else:
        st.info("No saved BUY/SELL observations match these filters yet. The scanner must complete a run and save qualifying historical observations first.")
    st.divider()
    st.markdown("### 📡 MARKET INTELLIGENCE")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("INSTRUMENT", str(latest_row.get("symbol", "—")) if latest_row is not None else "—")
    m2.metric("LAST SAVED PRICE", value_of(latest_row, "price", ".5f"))
    m3.metric("OBSERVATION", direction)
    m4.metric("DATA FRESHNESS", freshness)
    m5.metric("SAVED RECORDS", f"{len(filtered):,}")
    st.caption(f"{fresh_detail} · Timeframes: {filtered['timeframe'].nunique() if 'timeframe' in filtered.columns else 0} · Snapshot: {snapshot_status} ({snapshot_source})")
    left, right = st.columns([1, 2.1], gap="large")
    with left:
        st.markdown("### 🤖 ROBOT STATUS")
        robot_text = "WAITING FOR DATA" if freshness == "NO DATA" else ("CHECK DATA AGE" if freshness in {"AGING", "STALE"} else "SCANNING SAVED DATA")
        st.markdown(f"""<div class="robot-wrap"><div class="robot-orb">🤖</div><div class="robot-status">{robot_text}</div><div class="muted">Punjab Intelligence Monitor</div><p class="muted">Research / Demo · Saved files only</p><hr><div class="muted">LAST OBSERVATION</div><b>{fresh_detail}</b></div>""", unsafe_allow_html=True)
        st.markdown("**SYSTEM HEALTH**")
        for label, ok in [("History file has records", not history.empty), ("Snapshot available", snapshot_status == "AVAILABLE"), ("Latest observation recent", freshness == "RECENT")]:
            st.write(("🟢 " if ok else "🟡 ") + label)
    with right:
        st.markdown("### 📈 MARKET CHART")
        if not filtered.empty and time_col and "price" in filtered.columns:
            chart = filtered.dropna(subset=["price", time_col]).copy()
            chart = chart[chart["price"] > 0].sort_values(time_col)
            if not chart.empty:
                plot = chart.set_index(time_col)[["price"]].rename(columns={"price": "Recorded price"})
                st.line_chart(plot, height=330, x_label="Recorded time (UTC)", y_label="Saved price")
                st.caption("Historical saved prices only · no live market feed")
            else:
                st.warning("No valid positive saved prices are available.")
        else:
            st.warning("Waiting for saved scanner history.")
    st.markdown("### 🧠 TECHNICAL ANALYSIS")
    i1, i2, i3, i4, i5, i6 = st.columns(6)
    i1.metric("RSI (14)", value_of(latest_row, "rsi"))
    i2.metric("MACD", value_of(latest_row, "macd"))
    i3.metric("MACD SIGNAL", value_of(latest_row, "macd_signal"))
    i4.metric("EMA 9", value_of(latest_row, "ema9", ".5f"))
    i5.metric("EMA 21", value_of(latest_row, "ema21", ".5f"))
    i6.metric("EMA 50", value_of(latest_row, "ema50", ".5f"))
    st.markdown("### 🛰️ SCANNER & ROBOT ACTIVITY")
    scanner, activity = st.columns([1.2, 1], gap="large")
    with scanner:
        st.markdown("**Latest scanner observations**")
        if not latest.empty:
            show_cols = [x for x in ("recorded_at_utc", "signal_time", "symbol", "timeframe", "direction", "price", "rsi") if x in latest.columns]
            st.dataframe(latest[show_cols].head(12), use_container_width=True, hide_index=True)
        else:
            st.info("No scanner activity has been recorded.")
    with activity:
        st.markdown("**Robot activity monitor**")
        for label, status in [("Load saved history", "OK" if not history.empty else "WAITING"), ("Read latest snapshot", snapshot_status), ("Check observation age", freshness), ("Validate chart values", "OK" if latest_row is not None and pd.notna(latest_row.get("price")) else "WAITING")]:
            st.write(f"• {label} — **{status}**")
    with st.expander("🧪 PAPER RESEARCH JOURNAL — hypothetical examples only"):
        st.caption("Learning examples only. No recommendations, broker connection, or real orders.")
        if "paper_records" not in st.session_state:
            st.session_state.paper_records = []
        with st.form("console_paper_record"):
            c1, c2, c3 = st.columns(3)
            with c1:
                demo_symbol = st.selectbox("Example instrument", ["XAU/USD", "EUR/USD", "GBP/USD", "USD/JPY"])
                example_label = st.selectbox("Scenario label", ["Example A", "Example B"])
            with c2:
                entry = st.number_input("Example starting value", min_value=0.0, value=1.0, format="%.5f")
                review = st.number_input("Example review value", min_value=0.0, value=1.0, format="%.5f")
            with c3:
                units = st.number_input("Demo units", min_value=0.01, value=1.0, step=0.1)
                note = st.text_input("Note")
            save = st.form_submit_button("Save hypothetical example", use_container_width=True)
        if save and entry > 0 and review > 0:
            st.session_state.paper_records.insert(0, {"UTC": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "Instrument": demo_symbol, "Scenario": example_label, "Start": entry, "Review": review, "Demo units": units, "Illustrative difference": (review-entry)*units, "Note": note})
            st.success("Hypothetical example saved for this session.")
        elif save:
            st.error("Example values must be greater than zero.")
        if st.session_state.paper_records:
            st.dataframe(pd.DataFrame(st.session_state.paper_records), use_container_width=True, hide_index=True)
    st.caption("Punjab AI Robot · Research dashboard · Historical observations only · No broker connection or order execution.")

elif page == "Overview":
    st.markdown('<div class="section-kicker">Punjab intelligence console</div>', unsafe_allow_html=True)
    st.markdown("### 📡 Market overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Instrument", str(latest_row.get("symbol", "—")) if latest_row is not None else "—")
    c2.metric("Last saved price", value_of(latest_row, "price", ".5f"))
    c3.metric("Market observation", direction)
    c4.metric("Data freshness", freshness)
    st.caption(fresh_detail)

    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Saved observations", f"{len(filtered):,}")
    q2.metric("Instruments tracked", str(filtered["symbol"].nunique()) if "symbol" in filtered.columns else "—")
    q3.metric("Timeframes found", str(filtered["timeframe"].nunique()) if "timeframe" in filtered.columns else "—")
    q4.metric("Snapshot status", snapshot_status)

    left, right = st.columns([1.7, 1])
    with left:
        st.markdown("### 📈 Recorded market history")
        if not filtered.empty and "price" in filtered.columns and time_col:
            chart = filtered.dropna(subset=["price", time_col]).copy()
            chart = chart[chart["price"] > 0].sort_values(time_col)
            if not chart.empty:
                # Keep the price chart on one instrument/scale. Indicators are listed below.
                plot = chart.set_index(time_col)[["price"]].rename(columns={"price": "Saved price"})
                st.line_chart(plot, height=360, x_label="Recorded time (UTC)", y_label="Price as recorded")
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
    st.markdown('<div class="section-kicker">Read-only market data</div>', unsafe_allow_html=True)
    st.markdown("### 🔎 Scanner observations")
    st.caption("Read-only historical scanner output. Direction labels describe recorded data; they are not instructions.")
    if filtered.empty:
        st.warning("No scanner records found. The existing scanner workflow must create signal_history.csv.")
    else:
        st.metric("Matching observations", f"{len(filtered):,}")
        display_latest = latest.copy()
        if not display_latest.empty:
            source_direction = display_latest["direction"] if "direction" in display_latest.columns else display_latest.get("signal", pd.Series(index=display_latest.index, dtype=object))
            display_latest["DEMO SIGNAL"] = source_direction.map(demo_signal_label)
        st.dataframe(display_latest.head(300), use_container_width=True, hide_index=True)
        st.download_button(
            "Download filtered observations (CSV)",
            filtered.to_csv(index=False).encode("utf-8"),
            "punjab_scanner_observations.csv",
            "text/csv",
            use_container_width=True,
        )


elif page == "Paper trading demo":
    from virtual_demo_account import render_virtual_demo_account
    render_virtual_demo_account()

else:
    st.markdown('<div class="section-kicker">Platform diagnostics</div>', unsafe_allow_html=True)
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
