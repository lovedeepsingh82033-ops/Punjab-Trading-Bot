
import os
import time
import html
import logging
from pathlib import Path
from datetime import datetime, timezone

import requests
import pandas as pd
import numpy as np
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================================================
# PUNJAB TRADING SCANNER - ADVANCED PAPER EDITION
# Educational market analysis and historical paper testing.
# NO broker connection. NO live orders.
# ==========================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")

SYMBOLS = [
    "EUR/USD", "GBP/USD", "USD/JPY",
    "AUD/USD", "USD/CAD", "NZD/USD",
    "XAU/USD",
]

TIMEFRAMES = {
    "M1": ("1min", 1),
    "M2": ("2min", 2),
    "M5": ("5min", 5),
    "M10": ("10min", 10),
}

OUTPUT_SIZE = 500
MIN_CANDLES = 45
REQUEST_DELAY = 1.5

SIGNAL_FILE = Path("signal_history.csv")
HISTORY_DIR = Path("market_history")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# ---------------- HTTP SESSION ----------------

session = requests.Session()

retry = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST"],
)

adapter = HTTPAdapter(max_retries=retry)
session.mount("https://", adapter)


# ---------------- TELEGRAM ----------------

def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logging.warning("Telegram credentials missing.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        response = session.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get("ok", False)

    except requests.RequestException as error:
        logging.error("Telegram error: %s", error)
        return False


# ---------------- MARKET DATA ----------------

def fetch_market_data(symbol):
    if not API_KEY:
        logging.error("Twelve Data API key missing.")
        return None

    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": symbol,
        "interval": "1min",
        "outputsize": OUTPUT_SIZE,
        "apikey": API_KEY,
        "format": "JSON",
        "timezone": "UTC",
    }

    try:
        response = session.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if "values" not in data:
            logging.warning(
                "%s API response: %s",
                symbol,
                data.get("message", data),
            )
            return None

        df = pd.DataFrame(data["values"])

        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["datetime"] = pd.to_datetime(
            df["datetime"], utc=True, errors="coerce"
        )

        df = df.dropna(
            subset=["datetime", "open", "high", "low", "close"]
        )

        df = (
            df.sort_values("datetime")
            .drop_duplicates("datetime")
            .set_index("datetime")
        )

        return df

    except (requests.RequestException, ValueError, KeyError) as error:
        logging.error("%s data error: %s", symbol, error)
        return None


# ---------------- HISTORY ----------------

def save_market_history(symbol, df):
    if df is None or df.empty:
        return

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    filename = symbol.replace("/", "_") + "_1min.csv"
    path = HISTORY_DIR / filename

    new = df.reset_index()
    new["symbol"] = symbol

    if path.exists():
        try:
            old = pd.read_csv(path)
            old["datetime"] = pd.to_datetime(
                old["datetime"], utc=True, errors="coerce"
            )
            new = pd.concat([old, new], ignore_index=True)
        except (OSError, ValueError, KeyError) as error:
            logging.warning("History read issue: %s", error)

    new["datetime"] = pd.to_datetime(
        new["datetime"], utc=True, errors="coerce"
    )

    new = (
        new.dropna(subset=["datetime"])
        .drop_duplicates(["datetime", "symbol"], keep="last")
        .sort_values("datetime")
        .tail(10000)
    )

    new.to_csv(path, index=False)


# ---------------- TIMEFRAMES ----------------

def prepare_timeframe(df, timeframe):
    interval, minutes = TIMEFRAMES[timeframe]

    if timeframe == "M1":
        result = df.copy()
    else:
        result = df.resample(interval).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
        }).dropna()

    # Use completed candles only.
    now = pd.Timestamp.now(tz="UTC")
    result = result[
        result.index + pd.Timedelta(minutes=minutes) <= now
    ]

    if len(result) < MIN_CANDLES:
        logging.info(
            "%s: insufficient completed candles for %s",
            timeframe,
            len(result),
        )
        return None

    return result


# ---------------- INDICATORS ----------------

def add_indicators(df):
    df = df.copy()

    close = df["close"]
    high = df["high"]
    low = df["low"]

    df["ema9"] = close.ewm(span=9, adjust=False).mean()
    df["ema21"] = close.ewm(span=21, adjust=False).mean()
    df["ema50"] = close.ewm(span=50, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    df.loc[(avg_loss == 0) & (avg_gain > 0), "rsi"] = 100
    df.loc[(avg_gain == 0) & (avg_loss > 0), "rsi"] = 0
    df["rsi"] = df["rsi"].fillna(50)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()

    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(
        span=9, adjust=False
    ).mean()

    previous_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - previous_close).abs(),
        (low - previous_close).abs(),
    ], axis=1).max(axis=1)

    df["atr"] = tr.ewm(alpha=1/14, adjust=False).mean()

    up = high.diff()
    down = -low.diff()

    plus_dm = up.where((up > down) & (up > 0), 0)
    minus_dm = down.where((down > up) & (down > 0), 0)

    atr_safe = df["atr"].replace(0, np.nan)

    plus_di = (
        100 * plus_dm.ewm(alpha=1/14, adjust=False).mean()
        / atr_safe
    )

    minus_di = (
        100 * minus_dm.ewm(alpha=1/14, adjust=False).mean()
        / atr_safe
    )

    denominator = (plus_di + minus_di).replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / denominator

    df["adx"] = dx.ewm(alpha=1/14, adjust=False).mean()
    df["adx"] = df["adx"].fillna(0)

    df["support"] = low.rolling(20).min()
    df["resistance"] = high.rolling(20).max()

    return df


# ---------------- MARKET ANALYSIS ----------------

def analyze_market(df):
    if df is None or len(df) < MIN_CANDLES:
        return None

    df = add_indicators(df)
    row = df.iloc[-1]

    fields = [
        "close", "ema9", "ema21", "ema50",
        "rsi", "macd", "macd_signal",
        "atr", "adx", "support", "resistance",
    ]

    if not np.isfinite(row[fields].to_numpy(dtype=float)).all():
        return None

    buy = 0
    sell = 0
    reasons = []

    if row["ema9"] > row["ema21"]:
        buy += 1
        reasons.append("Short EMA bullish")
    elif row["ema9"] < row["ema21"]:
        sell += 1
        reasons.append("Short EMA bearish")

    if row["ema21"] > row["ema50"]:
        buy += 1
        reasons.append("Trend alignment bullish")
    elif row["ema21"] < row["ema50"]:
        sell += 1
        reasons.append("Trend alignment bearish")

    if row["macd"] > row["macd_signal"]:
        buy += 1
        reasons.append("MACD bullish")
    elif row["macd"] < row["macd_signal"]:
        sell += 1
        reasons.append("MACD bearish")

    if 50 < row["rsi"] < 70:
        buy += 1
        reasons.append("RSI bullish zone")
    elif 30 < row["rsi"] < 50:
        sell += 1
        reasons.append("RSI bearish zone")

    if row["adx"] >= 20:
        if buy > sell:
            buy += 1
        elif sell > buy:
            sell += 1
        reasons.append("Trend strength elevated")

    direction = "WAIT"

    if buy >= 4 and buy > sell:
        direction = "BUY ANALYSIS"
    elif sell >= 4 and sell > buy:
        direction = "SELL ANALYSIS"

    return {
        "direction": direction,
        "buy_score": buy,
        "sell_score": sell,
        "score": max(buy, sell),
        "price": float(row["close"]),
        "rsi": float(row["rsi"]),
        "adx": float(row["adx"]),
        "atr": float(row["atr"]),
        "support": float(row["support"]),
        "resistance": float(row["resistance"]),
        "time": df.index[-1].isoformat(),
        "reasons": "; ".join(reasons),
    }


# ---------------- SIGNAL HISTORY ----------------

def save_signal(symbol, timeframe, result):
    record = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "timeframe": timeframe,
        **result,
    }

    new = pd.DataFrame([record])

    if SIGNAL_FILE.exists():
        try:
            old = pd.read_csv(SIGNAL_FILE)
            new = pd.concat([old, new], ignore_index=True)
        except (OSError, ValueError) as error:
            logging.warning("Signal history read issue: %s", error)

    new = new.drop_duplicates(
        subset=["symbol", "timeframe", "time"],
        keep="last",
    )

    new.to_csv(SIGNAL_FILE, index=False)


# ---------------- REPORT ----------------

def make_report(symbol, timeframe, result):
    safe_symbol = html.escape(symbol)
    direction = html.escape(result["direction"])
    reasons = html.escape(result["reasons"])

    return (
        "📊 <b>PUNJAB ADVANCED SCANNER</b>\n\n"
        f"<b>Symbol:</b> {safe_symbol}\n"
        f"<b>Timeframe:</b> {timeframe}\n"
        f"<b>Analysis:</b> {direction}\n\n"
        f"<b>Observed price:</b> {result['price']:.5f}\n"
        f"<b>Indicator alignment:</b> {result['score']}/5\n"
        f"<b>BUY score:</b> {result['buy_score']}\n"
        f"<b>SELL score:</b> {result['sell_score']}\n\n"
        f"<b>RSI:</b> {result['rsi']:.2f}\n"
        f"<b>ADX:</b> {result['adx']:.2f}\n"
        f"<b>ATR:</b> {result['atr']:.5f}\n"
        f"<b>Support estimate:</b> {result['support']:.5f}\n"
        f"<b>Resistance estimate:</b> {result['resistance']:.5f}\n\n"
        f"<b>Analysis reasons:</b>\n{reasons}\n\n"
        f"<b>Candle time:</b> {result['time']}\n\n"
        "<i>Educational paper analysis only. "
        "Indicator alignment is not a win probability. "
        "No real orders are placed.</i>"
    )


# ---------------- MAIN ----------------

def main():
    logging.info("Punjab Advanced Scanner started.")

    sent = 0
    saved = 0
    issues = 0
    scanned = 0

    for symbol in SYMBOLS:
        logging.info("Scanning %s", symbol)

        market = fetch_market_data(symbol)

        if market is None or market.empty:
            issues += 1
            time.sleep(REQUEST_DELAY)
            continue

        try:
            save_market_history(symbol, market)
        except (OSError, ValueError) as error:
            logging.error("History error for %s: %s", symbol, error)
            issues += 1

        for timeframe in TIMEFRAMES:
            try:
                prepared = prepare_timeframe(market, timeframe)

                if prepared is None:
                    continue

                result = analyze_market(prepared)

                if result is None:
                    continue

                scanned += 1
                save_signal(symbol, timeframe, result)
                saved += 1

                if result["direction"] != "WAIT":
                    if send_telegram(
                        make_report(symbol, timeframe, result)
                    ):
                        sent += 1

            except Exception:
                logging.exception(
                    "Analysis failed: %s %s",
                    symbol,
                    timeframe,
                )
                issues += 1

        time.sleep(REQUEST_DELAY)

    summary = (
        "✅ <b>PUNJAB SCAN COMPLETE</b>\n\n"
        f"Markets checked: {len(SYMBOLS)}\n"
        f"Timeframe analyses: {scanned}\n"
        f"Records saved: {saved}\n"
        f"Analysis alerts sent: {sent}\n"
        f"Data or analysis issues: {issues}\n\n"
        "<i>Paper analysis only. No real orders placed.</i>"
    )

    send_telegram(summary)

    logging.info(
        "Completed | Scanned=%s Saved=%s Sent=%s Issues=%s",
        scanned, saved, sent, issues,
    )


if __name__ == "__main__":
    main()
