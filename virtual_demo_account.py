"""Educational virtual-account simulator. No live prices or real order execution."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st


def render_virtual_demo_account() -> None:
    st.markdown("### 🧪 Virtual demo account")
    st.caption("Practice-only simulator. Prices are entered manually; nothing is sent to a broker or exchange.")

    if "virtual_demo_balance" not in st.session_state:
        st.session_state.virtual_demo_balance = 10_000.0
    if "virtual_demo_history" not in st.session_state:
        st.session_state.virtual_demo_history = []

    balance = float(st.session_state.virtual_demo_balance)
    records = st.session_state.virtual_demo_history

    a, b, c = st.columns(3)
    a.metric("Starting virtual balance", "10,000.00")
    b.metric("Current virtual balance", f"{balance:,.2f}")
    net = balance - 10_000.0
    c.metric("Simulated net result", f"{net:+,.2f}")

    st.info("All figures are fictional learning values. This page does not display live quotes, give trading advice, or place real orders.")

    with st.form("virtual_trade_simulator"):
        st.markdown("#### Record a hypothetical trade")
        left, right = st.columns(2)
        with left:
            instrument = st.selectbox("Instrument", ["XAU/USD", "EUR/USD", "GBP/USD", "USD/JPY", "BTC/USD"])
            side = st.radio("Scenario you want to test", ["BUY", "SELL"], horizontal=True)
            units = st.number_input("Virtual units", min_value=0.01, value=1.0, step=0.1)
        with right:
            entry = st.number_input("Fictional entry price", min_value=0.00001, value=100.0, format="%.5f")
            exit_price = st.number_input("Fictional closing price", min_value=0.00001, value=101.0, format="%.5f")
            note = st.text_input("Learning note (optional)")
        submitted = st.form_submit_button("Calculate demo result", type="primary", use_container_width=True)

    if submitted:
        change = (exit_price - entry) if side == "BUY" else (entry - exit_price)
        result = change * units
        if balance + result < 0:
            st.error("This example would take the virtual balance below zero, so it was not recorded.")
        else:
            st.session_state.virtual_demo_balance = balance + result
            records.insert(0, {
                "Recorded (UTC)": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "Instrument": instrument,
                "Scenario": side,
                "Virtual units": units,
                "Fictional entry": entry,
                "Fictional close": exit_price,
                "Illustrative result": result,
                "Virtual balance after": balance + result,
                "Learning note": note,
            })
            st.success(f"Simulation recorded. Illustrative result: {result:+,.2f} virtual units.")
            st.rerun()

    st.markdown("#### Demo history")
    if records:
        history = pd.DataFrame(records)
        st.dataframe(history, use_container_width=True, hide_index=True)
        st.download_button(
            "Download demo history (CSV)",
            history.to_csv(index=False).encode("utf-8"),
            "punjab_virtual_demo_history.csv",
            "text/csv",
        )
    else:
        st.caption("No hypothetical trades recorded in this session yet.")

    if st.button("Reset virtual account to 10,000", use_container_width=False):
        st.session_state.virtual_demo_balance = 10_000.0
        st.session_state.virtual_demo_history = []
        st.rerun()

    st.caption("Session-only demo: the virtual balance and history reset when the session is cleared. No real funds, deposits, withdrawals, leverage, or broker connection.");
