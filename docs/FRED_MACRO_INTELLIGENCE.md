# FRED Macro Intelligence

Punjab Trading Bot can optionally retrieve a small set of published U.S.
macroeconomic observations from the Federal Reserve Bank of St. Louis FRED API.

## Configuration

Add a GitHub Actions secret named `FRED_API_KEY` only if you want to enable
this optional data source. Obtain a key from the official FRED API site:
https://fred.stlouisfed.org/docs/api/api_key.html

Without the secret, the module returns `NOT CONFIGURED` and makes no network
request. No API key is stored in source code.

## Included series

- `FEDFUNDS` — Federal Funds Effective Rate
- `CPIAUCSL` — Consumer Price Index for All Urban Consumers
- `UNRATE` — Civilian Unemployment Rate
- `DGS10` — 10-Year Treasury Constant Maturity Rate
- `DTWEXBGS` — Nominal Broad U.S. Dollar Index

## Python usage

```python
from fred_macro import fetch_fred_macro_context

context = fetch_fred_macro_context()
print(context["status"])
for item in context["series"]:
    print(item["series_id"], item["latest"], item["previous"], item["change"])
```

The function is intentionally opt-in and bounded: at most ten observations per
series, a timeout no longer than 30 seconds, and no import-time network access.
FRED observations are published economic data, not real-time prices; release
dates and frequencies differ by series. Values are descriptive context only,
not forecasts or trading instructions. The module does not connect to brokers,
place orders, or alter scanner eligibility.
