import streamlit as st
import pandas as pd
from datetime import datetime, timezone

st.set_page_config(
    page_title="PUNJAB AI ALGO",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
:root { color-scheme: dark; }
.stApp {
  background: radial-gradient(circle at 15% 0%, #082b48 0, #050912 42%, #03060c 100%);
  color: #eaf7ff;
}
.block-container {max-width: 1180px; padding-top: 1.2rem; padding-bottom: 3rem;}
h1, h2, h3 {color: #eafaff !important;}
.hero {
  border: 1px solid #12d8f2; border-radius: 22px; padding: 22px;
  background: linear-gradient(120deg, rgba(0,190,255,.17), rgba(0,255,190,.07));
  box-shadow: 0 0 24px rgba(0,210,255,.12);
}
.brand {font-size: 1.7rem; font-weight: 850; letter-spacing: .12em;}
.sub {color: #8daec4; letter-spacing: .12em; font-size: .78rem;}
.panel {
  border: 1px solid #15566b; border-radius: 18px; padding: 18px;
  background: rgba(9,19,34,.88); min-height: 132px;
}
.pill {
  display:inline-block; border:1px solid #13d9ef; color:#65efff;
  border-radius:999px; padding:5px 11px; font-size:.78rem;
}
div[data-testid="stMetric"] {
  background: rgba(10,25,43,.9); border:1px solid #14566b;
  border-radius:15px; padding:13px;
}
.stButton > button {
  border: 1px solid #12d9ef; border-radius: 13px;
  background: linear-gradient(90deg,#0877ff,#00cce8);
  color: white; font-weight: 800; min-height: 46px;
}
[data-testid="stSelectbox"] > div > div {
  background: #0b1728; border-color: #15566b; border-radius: 12px;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <div class="brand">⚡ PUNJAB <span style="color:#27e7d1">AI ALGO</span></div>
  <div class="sub">MARKET INTELLIGENCE · EDUCATIONAL RESEARCH / PAPER DEMO</div>
  <br><span class="pill">● DEMO MODE · EXECUTION DISABLED</span>
</div>
""", unsafe_allow_html=True)

st.warning(
    "EDUCATIONAL DEMO ONLY — this dashboard does not provide trading instructions, "
    "verified market signals, financial advice, broker access, or order execution. "
    "Any sample observations are illustrative, not live market data."
)

m1, m2, m3, m4 = st.columns(4)
m1.metric("SYSTEM", "DEMO", "Illustrative research")
m2.metric("MARKETS", "28 planned", "Coverage roadmap")
m3.metric("RESEARCH VIEWS", "4", "M15 · M30 · H1 · H4")
m4.metric("EXECUTION", "DISABLED", "No broker connection")

st.markdown("### 🌐 Market Research Terminal")
category = st.radio(
    "Market category",
    ["Currencies", "Crypto", "Commodities"],
    horizontal=True,
    label_visibility="collapsed",
)
market_map = {
    "Currencies": ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "EUR/JPY"],
    "Crypto": ["BTC/USD", "ETH/USD", "SOL/USD"],
    "Commodities": ["XAU/USD", "XAG/USD", "WTI/USD"],
}
c1, c2 = st.columns([1.4, 1])
with c1:
    symbol = st.selectbox("Instrument", market_map[category])
with c2:
    timeframe = st.selectbox("Research timeframe", ["M15", "M30", "H1", "H4"])

st.markdown(
    '<div class="panel"><b>Research workspace</b><br>'
    '<span style="color:#8daec4">Select a market and timeframe to view an educational '
    'research note. No BUY/SELL instruction is generated.</span></div>',
    unsafe_allow_html=True,
)
if st.button("✦ Generate Research Snapshot", use_container_width=True):
    st.session_state["research_selection"] = (category, symbol, timeframe)

if "research_selection" in st.session_state:
    selected_category, selected_symbol, selected_tf = st.session_state["research_selection"]
    st.info(
        f"Research snapshot selected: {selected_category} · {selected_symbol} · {selected_tf}. "
        "Live data is not connected. Add a verified historical dataset before drawing "
        "any market conclusions."
    )

st.markdown("### 📊 Observation Board")
observations = pd.DataFrame([
    {"Instrument": "EUR/USD", "View": "Trend structure study", "Timeframe": "H1", "Label": "DEMO"},
    {"Instrument": "GBP/USD", "View": "Range behaviour study", "Timeframe": "M30", "Label": "DEMO"},
    {"Instrument": "USD/JPY", "View": "Volatility study", "Timeframe": "H4", "Label": "DEMO"},
    {"Instrument": "XAU/USD", "View": "Macro context study", "Timeframe": "H1", "Label": "DEMO"},
    {"Instrument": "BTC/USD", "View": "Historical movement study", "Timeframe": "M15", "Label": "DEMO"},
])
st.dataframe(observations, use_container_width=True, hide_index=True)

st.markdown("### 🧩 Platform Modules")
a, b, c = st.columns(3)
with a:
    st.markdown('<div class="panel"><h3>📈 Research Library</h3><p>Educational market concepts, chart terminology and historical study notes.</p></div>', unsafe_allow_html=True)
with b:
    st.markdown('<div class="panel"><h3>🗂️ Paper Journal</h3><p>Record hypothetical observations and review them without real-money activity.</p></div>', unsafe_allow_html=True)
with c:
    st.markdown('<div class="panel"><h3>🤖 Telegram Updates</h3><p>Planned bot notices for platform status and educational research summaries.</p></div>', unsafe_allow_html=True)

st.markdown("### 🛡️ System & Data Status")
s1, s2 = st.columns(2)
with s1:
    st.success("App interface: deployed starter dashboard")
    st.write("Market feed: not connected")
    st.write("Persistent research history: not configured")
with s2:
    st.info("Telegram integration: pending secure hosting setup")
    st.write("Broker connection: disabled")
    st.write("Order execution: disabled")

st.divider()
st.caption(
    "PUNJAB AI ALGO · Educational research / paper demo only · "
    "Updated (UTC): " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
)
