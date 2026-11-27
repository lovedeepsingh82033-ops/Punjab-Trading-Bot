# PUNJAB AI ALGO

A separate Telegram companion and mobile-friendly Streamlit research dashboard.

## Safety and scope
Educational research / paper-demo only. No broker integration, real-money trading, order placement, or trading recommendations. Dashboard rows are clearly illustrative sample data.

## Web dashboard
```bash
pip install -r requirements.txt
streamlit run app.py
```
For Streamlit Community Cloud, select this repository and branch `feature/punjab-ai-algo-platform`, with main file path `punjab_ai_algo_app/app.py`.

## Telegram bot
Create a bot using Telegram's official BotFather. Add its token as a hosting secret named `TELEGRAM_BOT_TOKEN`. Do not commit the token or paste it into chat.
```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="..."
python bot.py
```
Commands: `/start`, `/status`, `/research`, `/markets`, `/help`.

## Not yet configured
Verified live data source, database, authentication, Telegram Mini App linking, monitoring, and deployment.
