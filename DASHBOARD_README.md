# Punjab Market Research Dashboard

This is an **optional, read-only local dashboard**. It does not replace or modify the existing scanner, Telegram bot, scheduled workflow, or signal-history process.

## Run locally

1. Download or clone the repository.
2. Install the optional dashboard dependencies:

   ```bash
   python -m pip install -r dashboard_requirements.txt
   ```

3. Make sure `signal_history.csv` is in the repository folder. If available, place the latest `bot_state.json` snapshot beside it.
4. Start the dashboard:

   ```bash
   streamlit run research_web_dashboard.py
   ```

5. Open the local URL printed by Streamlit (normally `http://localhost:8501`).

## Included

- Market/instrument and timeframe filters
- Technical-observation, multi-timeframe, and historical-outcome views
- Historical observation table and price chart
- Summary of recorded and resolved historical samples
- Latest scanner snapshot, when present

## Safety and limitations

- Read-only research display; no broker connection, order placement, or trade execution.
- Direction fields are historical scanner observations, not instructions.
- Historical outcome ratios are descriptive only. Legacy, pending, and incomplete records may affect sample quality.
- The dashboard runs locally. It is not automatically hosted on the public internet.
- The optional Streamlit dependency is separate from the scanner's existing `requirements.txt` and GitHub Actions workflow.
