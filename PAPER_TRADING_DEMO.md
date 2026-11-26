# Punjab Paper Trading Demo

This is a separate, manual paper-trading interface. Its BUY and SELL controls
only save hypothetical records entered by the user. They do not generate
market recommendations, fetch live prices, connect to a broker, or place
orders.

## Run locally

Use Python 3.11 and install the dashboard dependencies:

```bash
pip install -r dashboard_requirements.txt
streamlit run paper_trading_demo.py
```

The demo records are kept in Streamlit session state only. They are not
persisted to the repository or a database and may disappear when the session
resets. The hypothetical P/L is simple price arithmetic and excludes spread,
fees, slippage, swaps, and other execution effects.
