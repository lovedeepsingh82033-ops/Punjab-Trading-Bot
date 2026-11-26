"""Punjab Market Scanner — paper-trading demo UI.

BUY/SELL controls below only record hypothetical paper trades entered by the
user. They are not generated market recommendations and never place orders.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Punjab Scanner | Paper Demo",
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
    .demo-banner {
        padding: 14px 16px; border-radius: 10px;
        background: #332615; border: 1px solid #8b672c;
        color: #ffedc2; margin-bottom: 18px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🤖 PUNJAB MARKET SCANNER")
st.subheader("Paper Trading Demo")
st.markdown(
    '<div class="demo-banner"><b>DEMO ONLY.</b> BUY and SELL are manual '
    'paper-trade logging controls. They are not live signals, financial '
    'recommendations, broker orders, or predictions. No real money is used.</div>',
    unsafe_allow_html=True,
)

if "paper_trades" not in st.session_state:
    st.session_state.paper_trades = []

symbols = ["XAU/USD", "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "NZD/USD"]
with st.sidebar:
    st.header("Demo settings")
    symbol = st.selectbox("Instrument", symbols)
    timeframe = st.selectbox("Timeframe", ["M5", "M15", "M30", "H1", "H4", "D1"])
    st.caption("This demo does not fetch live prices or connect to a broker.")
    if st.button("Clear demo history", use_container_width=True):
        st.session_state.paper_trades = []
        st.rerun()

st.markdown("### Record a hypothetical paper trade")
st.caption("Enter example prices yourself. The app only calculates the result of this simulated record.")
col1, col2, col3 = st.columns(3)
with col1:
    side = st.radio("Demo action", ["BUY", "SELL"], horizontal=True)
with col2:
    entry = st.number_input("Entry price (example)", min_value=0.0, value=1.0, format="%.5f")
with col3:
    exit_price = st.number_input("Exit / review price (example)", min_value=0.0, value=1.0, format="%.5f")

units = st.number_input("Demo units", min_value=0.01, value=1.0, step=0.1)
if st.button("Save demo record", type="primary", use_container_width=True):
    if entry <= 0 or exit_price <= 0:
        st.error("Enter prices greater than zero.")
    else:
        move = (exit_price - entry) if side == "BUY" else (entry - exit_price)
        pct = move / entry * 100.0
        st.session_state.paper_trades.insert(
            0,
            {
                "Recorded (UTC)": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "Instrument": symbol,
                "Timeframe": timeframe,
                "Demo action": side,
                "Entry": entry,
                "Review price": exit_price,
                "Demo units": units,
                "Hypothetical P/L": move * units,
                "Move (%)": pct,
                "Result": "Positive" if move > 0 else ("Negative" if move < 0 else "Flat"),
            },
        )
        st.success("Hypothetical demo record saved in this browser session.")

trades = st.session_state.paper_trades
if trades:
    frame = pd.DataFrame(trades)
    total = float(frame["Hypothetical P/L"].sum())
    positive = int((frame["Result"] == "Positive").sum())
    a, b, c = st.columns(3)
    a.metric("Demo records", len(frame))
    b.metric("Hypothetical net P/L", f"{total:.5f}")
    c.metric("Positive records", positive)
    st.markdown("### Demo history")
    st.dataframe(frame, use_container_width=True, hide_index=True)
    csv = frame.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download demo history (CSV)",
        data=csv,
        file_name="punjab_paper_demo_history.csv",
        mime="text/csv",
        use_container_width=True,
    )
else:
    st.info("No demo records yet. Add a hypothetical BUY or SELL record above to see how the paper log works.")

st.markdown("---")
st.caption(
    "Educational software demo only. Results are arithmetic on user-entered "
    "example prices, exclude spreads, fees, slippage and financing, and do not "
    "represent actual trading performance. Records are session-only and may "
    "disappear when the app session resets."
)
