"""Punjab AI Robot — visual scanner and paper-research dashboard.

Market observations are read-only descriptions of saved scanner data.
BUY/SELL controls only create user-entered hypothetical paper records.
No broker connection, live order execution, or generated trade instruction.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

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
.block-container { padding-top: 1.25rem; max-width: 1600px; }
h1, h2, h3 { color: #f4f8ff !important; }
div[data-testid="stMetric"] {
  background: linear-gradient(145deg, #10243a, #0a1728);
  border: 1px solid #1c3b5c; border-radius: 14px; padding: 14px 16px;
}
div[data-testid="stMetricLabel"] { color: #a9bdd5; }
div[data-testid="stMetricValue"] { color: #f4f8ff; }
.punjab-header {
  background: linear-gradient(100deg, #08182c, #102d49 55%, #071525);
  border: 1px solid #1e496d; border-radius: 18px;
  padding: 18px 22px; margin-bottom: 16px;
}
.brand { font-size: 29px; font-weight: 850; letter-spacing: .7px; color: #f8fbff; }
.brand span { color: #f4c542; }
.subbrand { color: #a9c1db; font-size: 13px; margin-top: 4px; }
.panel {
  background: linear-gradient(150deg, rgba(15,34,55,.96), rgba(7,18,32,.96));
  border: 1px solid #1b3a59; border-radius: 15px; padding: 16px;
  min-height: 110px; margin-bottom: 10px;
}
.panel-title { color: #a9bdd5; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }
.panel-value { color: #f4f8ff; font-size: 23px; font-weight: 750; margin-top: 8px; }
.green { color: #23e58b !important; }
.yellow { color: #f4c542 !important; }
.red { color: #ff6868 !important; }
.robot-wrap {
  background: radial-gradient(circle at 50% 28%, #103b49, #071a2a 66%);
  border: 1px solid #14634f; border-radius: 18px; padding: 22px;
  text-align: center; min-height: 270px;
}
.robot-orb {
  width: 112px; height: 112px; margin: 8px auto 14px; border-radius: 100%;
  border: 4px solid #18e68b; box-shadow: 0 0 28px rgba(24,230,139,.32);
  display: flex; align-items: center; justify-content: center;
  font-size: 58px; background: #082b36;
}
.robot-status { font-size: 25px; font-weight: 850; color: #24e995; }
.muted { color: #9bb0c7; font-size: 12px; }
.logline { padding: 7px 0; border-bottom: 1px solid #17314c; color: #cbd8e8; font-size: 13px; }
.notice {
  border: 1px solid #8b672c; background: #302513; color: #ffe7b1;
  border-radius: 10px; padding: 12px 15px; margin: 10px 0 18px;
}
div.stButton > button[kind="primary"] {
  background: linear-gradient(90deg, #087e58, #10b981); border: 0; color: white;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="punjab-header">
  <div class="brand">🐅 <span>PUNJAB AI</span> TRADING ROBOT</div>
  <div class="subbrand">SMART SCANNER&nbsp; • &nbsp;MARKET OBSERVATIONS&nbsp; • &nbsp;PAPER RESEARCH</div>
</div>
<div class="notice"><b>RESEARCH / DEMO MODE.</b> Market labels are descriptive observations only.
The BUY/SELL controls below only save hypothetical records you enter; they are not trading
recommendations, live signals, or broker orders. No real-money trading is available.</div>
""", unsafe_allow_html=True)

@st.cache_data(ttl=20)
def load_history(path: str, modified: float) -> pd.DataFrame:
    del modified
    try:
        df = pd.read_csv(path)
    except (OSError, pd.errors.EmptyDataError):
        return pd.DataFrame()
    for col in ("signal_time", "recorded_at_utc", "evaluated_at"):
        if col in df:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
    for col in ("price", "rsi", "adx", "atr", "bull_score", "bear_score",
                "ema9", "ema21", "ema50", "macd", "macd_signal", "macd_hist"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

@st.cache_data(ttl=15)
def load_snapshot(path: str, modified: float):
    del modified
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

history = load_history(str(HISTORY_PATH), HISTORY_PATH.stat().st_mtime) if HISTORY_PATH.exists() else pd.DataFrame()
snapshot = load_snapshot(str(SNAPSHOT_PATH), SNAPSHOT_PATH.stat().st_mtime) if SNAPSHOT_PATH.exists() else {}

with st.sidebar:
    st.markdown("## 🧭 Navigation")
    page = st.radio("Dashboard section", ["Overview", "Scanner data", "Paper trading demo", "System information"], label_visibility="collapsed")
    st.divider()
    st.markdown("### Scanner filters")
    symbols = sorted(history["symbol"].dropna().astype(str).unique()) if "symbol" in history else []
    frames = sorted(history["timeframe"].dropna().astype(str).unique()) if "timeframe" in history else []
    selected_symbol = st.selectbox("Instrument", ["All"] + symbols)
    selected_frame = st.selectbox("Timeframe", ["All"] + frames)
    if st.button("↻ Refresh dashboard", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Data is read from the repository's saved scanner files. This page does not invent live prices.")

filtered = history.copy()
if selected_symbol != "All" and "symbol" in filtered:
    filtered = filtered[filtered["symbol"].astype(str) == selected_symbol]
if selected_frame != "All" and "timeframe" in filtered:
    filtered = filtered[filtered["timeframe"].astype(str) == selected_frame]

sort_col = "recorded_at_utc" if "recorded_at_utc" in filtered else ("signal_time" if "signal_time" in filtered else None)
latest = filtered.sort_values(sort_col, ascending=False, na_position="last") if sort_col else filtered
latest_row = latest.iloc[0] if not latest.empty else None

freshness = "NO DATA"
fresh_detail = "No saved scanner observations found"
if latest_row is not None and sort_col and pd.notna(latest_row.get(sort_col)):
    age = max(0.0, (datetime.now(timezone.utc) - latest_row[sort_col].to_pydatetime()).total_seconds() / 3600)
    freshness = "RECENT" if age <= 1 else ("AGING" if age <= 24 else "STALE")
    fresh_detail = f"Last saved observation: {latest_row[sort_col].strftime('%Y-%m-%d %H:%M UTC')} · {age:.1f}h ago"

def value_of(row, key, fmt=".2f", fallback="—"):
    if row is None:
        return fallback
    val = row.get(key)
    if pd.isna(val):
        return fallback
    try:
        return format(float(val), fmt)
    except (TypeError, ValueError):
        return str(val)

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

    left, right = st.columns([1.8, 1])
    with left:
        st.markdown("### 📈 Recorded price chart")
        if not filtered.empty and {"price", "signal_time"}.issubset(filtered.columns):
            chart = filtered.dropna(subset=["price", "signal_time"]).sort_values("signal_time")
            if not chart.empty:
                st.line_chart(chart.set_index("signal_time")["price"], height=330,
                              x_label="Recorded time (UTC)", y_label="Saved price")
            else:
                st.info("No valid saved price/time pairs are available for these filters.")
        else:
            st.info("Waiting for scanner history. Once signal_history.csv is available, recorded prices will appear here. No sample prices are presented as live data.")
    with right:
        st.markdown("### 🤖 Robot monitor")
        robot_text = "WAITING FOR DATA" if freshness == "NO DATA" else ("CHECK DATA AGE" if freshness in {"AGING", "STALE"} else "OBSERVING")
        st.markdown(f"""
        <div class="robot-wrap">
          <div class="robot-orb">🤖</div>
          <div class="robot-status">{robot_text}</div>
          <div class="muted">Scanner observation monitor</div>
          <p class="muted">{fresh_detail}</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("**System checks**")
        for label, ok in [
            ("History file", not history.empty),
            ("Snapshot file", bool(snapshot)),
            ("Recent observation", freshness == "RECENT"),
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
            rows = []
            for label, key in [("RSI (14)", "rsi"), ("MACD", "macd"), ("MACD signal", "macd_signal"),
                               ("EMA 9", "ema9"), ("EMA 21", "ema21"), ("EMA 50", "ema50")]:
                rows.append({"Indicator": label, "Recorded value": value_of(latest_row, key, ".5f")})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("Technical indicators will appear when scanner observations are saved.")
    with high:
        st.markdown("### 🕒 Recent scanner activity")
        if not latest.empty:
            show_cols = [x for x in ["recorded_at_utc", "symbol", "timeframe", "direction", "price"] if x in latest]
            st.dataframe(latest[show_cols].head(8), use_container_width=True, hide_index=True)
        else:
            st.info("No activity has been recorded yet.")

elif page == "Scanner data":
    st.markdown("### 🔎 Scanner observations")
    st.caption("Read-only historical scanner output; direction labels are observations, not trade instructions.")
    if filtered.empty:
        st.warning("No scanner records found. Run the existing scanner workflow to create signal_history.csv.")
    else:
        st.metric("Matching observations", f"{len(filtered):,}")
        st.dataframe(latest.head(250), use_container_width=True, hide_index=True)
        st.download_button("Download filtered observations (CSV)", filtered.to_csv(index=False).encode("utf-8"),
                           "punjab_scanner_observations.csv", "text/csv")

elif page == "Paper trading demo":
    st.markdown("### 🧾 Manual paper-trading journal")
    st.caption("Enter hypothetical values to learn how a journal calculates a simulated result. This does not generate a signal or place an order.")
    if "paper_records" not in st.session_state:
        st.session_state.paper_records = []
    with st.form("paper_record_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            demo_symbol = st.selectbox("Instrument", ["XAU/USD", "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD"])
            action = st.radio("Hypothetical side", ["BUY", "SELL"], horizontal=True)
        with c2:
            entry = st.number_input("Example entry price", min_value=0.0, value=1.0, format="%.5f")
            review = st.number_input("Example review price", min_value=0.0, value=1.0, format="%.5f")
        with c3:
            units = st.number_input("Demo units", min_value=0.01, value=1.0, step=0.1)
            note = st.text_input("Optional note")
        save = st.form_submit_button("Save hypothetical demo record", type="primary", use_container_width=True)
    if save:
        if entry <= 0 or review <= 0:
            st.error("Enter example prices greater than zero.")
        else:
            delta = (review - entry) if action == "BUY" else (entry - review)
            st.session_state.paper_records.insert(0, {
                "Recorded UTC": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "Instrument": demo_symbol, "Side": action, "Example entry": entry,
                "Review price": review, "Demo units": units,
                "Hypothetical P/L": delta * units,
                "Result": "Positive" if delta > 0 else ("Negative" if delta < 0 else "Flat"),
                "Note": note,
            })
            st.success("Hypothetical record saved for this app session.")
    records = st.session_state.paper_records
    if records:
        df = pd.DataFrame(records)
        x, y, z = st.columns(3)
        x.metric("Demo records", len(df))
        y.metric("Hypothetical net P/L", f"{df['Hypothetical P/L'].sum():.5f}")
        z.metric("Positive records", int((df["Result"] == "Positive").sum()))
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("Download demo journal (CSV)", df.to_csv(index=False).encode("utf-8"),
                           "punjab_paper_journal.csv", "text/csv")
    else:
        st.info("Your paper journal is empty. Add a hypothetical record above to test the journal.")
    if st.button("Clear this session's demo journal"):
        st.session_state.paper_records = []
        st.rerun()

else:
    st.markdown("### ⚙️ System information")
    st.write("**Dashboard:** Punjab AI Trading Robot")
    st.write("**Mode:** Read-only scanner observations + manual paper journal")
    st.write("**History file:**", "Found" if HISTORY_PATH.exists() else "Not found")
    st.write("**Snapshot file:**", "Found" if SNAPSHOT_PATH.exists() else "Not found")
    st.write("**Python data rows loaded:**", len(history))
    if snapshot:
        st.markdown("#### Latest saved scanner snapshot")
        st.json(snapshot)
    else:
        st.info("No bot_state.json snapshot is available in this app's current filesystem.")

st.divider()
st.caption("Punjab AI Trading Robot · Educational research dashboard only. Historical observations are not forecasts. Paper journal calculations use user-entered example prices and exclude spreads, fees, slippage and financing. Demo records are session-only.")
