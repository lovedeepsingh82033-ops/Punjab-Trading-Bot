
import os
import time
import logging
from pathlib import Path
from datetime import datetime, timezone

import requests
import pandas as pd
import numpy as np

# =========================================================
# PUNJAB TRADING SCANNER
# Educational analysis and paper testing only.
# NO broker connection. NO real-money orders.
# =========================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")

SYMBOLS = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "AUD/USD",
    "USD/CAD",
    "NZD/USD",
    "XAU/USD",
]

TIMEFRAMES = {
    "M1": "1min",
    "M2": "2min",
    "M5": "5min",
    "M10": "10min",
}

OUTPUT_SIZE = 500
HISTORY_FOLDER = Path("market_history")
SIGNAL_FILE = Path("signal_history.csv")
REQUEST_DELAY = 1.2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

session = requests.Session()


def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logging.warning("Telegram credentials are missing.")
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

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


def fetch_market_data(symbol):
    if not TWELVE_DATA_API_KEY:
        logging.error("Twelve Data API key is missing.")
        return None

    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": symbol,
        "interval": "1min",
        "outputsize": OUTPUT_SIZE,
        "apikey": TWELVE_DATA_API_KEY,
        "format": "JSON",
        "timezone": "UTC",
    }

    try:
        response = session.get(
            url,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        if "values" not in data:
            logging.warning(
                "%s: API response: %s",
                symbol,
                data.get("message", data),
            )
            return None

        df = pd.DataFrame(data["values"])

        for column in ["open", "high", "low", "close"]:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

        df["datetime"] = pd.to_datetime(
            df["datetime"],
            utc=True,
            errors="coerce",
        )

        df = df.dropna(
            subset=[
                "datetime",
                "open",
                "high",
                "low",
                "close",
            ]
        )

        df = df.sort_values("datetime")
        df = df.drop_duplicates("datetime")
        df = df.set_index("datetime")

        return df

    except (requests.RequestException, ValueError, KeyError) as error:
        logging.error("%s data error: %s", symbol, error)
        return None


def save_market_history(symbol, df):
    if df is None or df.empty:
        return

    HISTORY_FOLDER.mkdir(
        parents=True,
        exist_ok=True,
    )

    safe_symbol = symbol.replace("/", "_")
    file_path = HISTORY_FOLDER / f"{safe_symbol}_1min.csv"

    saved = df.reset_index()
    saved["symbol"] = symbol

    if file_path.exists():
        try:
            old = pd.read_csv(file_path)
            old["datetime"] = pd.to_datetime(
                old["datetime"],
                utc=True,
                errors="coerce",
            )
            saved = pd.concat(
                [old, saved],
                ignore_index=True,
            )
        except (OSError, ValueError, KeyError) as error:
            logging.warning(
                "Could not read old history for %s: %s",
                symbol,
                error,
            )

    saved = saved.dropna(subset=["datetime"])
    saved = saved.drop_duplicates(
        subset=["datetime", "symbol"],
        keep="last",
    )
    saved = saved.sort_values("datetime")
    saved = saved.tail(10000)

    saved.to_csv(file_path, index=False)


def add_indicators(df):
    df = df.copy()

    close = df["close"]
    high = df["high"]
    low = df["low"]

    df["ema9"] = close.ewm(
        span=9,
        adjust=False,
    ).mean()

    df["ema21"] = close.ewm(
        span=21,
        adjust=False,
    ).mean()

    df["ema50"] = close.ewm(
        span=50,
        adjust=False,
    ).mean()

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / 14,
        adjust=False,
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / 14,
        adjust=False,
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    df["rsi"] = df["rsi"].fillna(50)

    ema12 = close.ewm(
        span=12,
        adjust=False,
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False,
    ).mean()

    df["macd"] = ema12 - ema26

    df["macd_signal"] = df["macd"].ewm(
        span=9,
        adjust=False,
    ).mean()

    previous_close = close.shift(1)

    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df["atr"] = true_range.ewm(
        alpha=1 / 14,
        adjust=False,
    ).mean()

    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where(
        (plus_dm > minus_dm) & (plus_dm > 0),
        0,
    )

    minus_dm = minus_dm.where(
        (minus_dm > plus_dm) & (minus_dm > 0),
        0,
    )

    atr_safe = df["atr"].replace(0, np.nan)

    plus_di = (
        100
        * plus_dm.ewm(alpha=1 / 14, adjust=False).mean()
        / atr_safe
    )

    minus_di = (
        100
        * minus_dm.ewm(alpha=1 / 14, adjust=False).mean()
        / atr_safe
    )

    dx = (
        100
        * (plus_di - minus_di).abs()
        / (plus_di + minus_di).replace(0, np.nan)
    )

    df["adx"] = dx.ewm(
        alpha=1 / 14,
        adjust=False,
    ).mean()

    df["adx"] = df["adx"].fillna(0)

    df["support"] = low.rolling(20).min()
    df["resistance"] = high.rolling(20).max()

    return df


def prepare_timeframe(df, timeframe):
    if timeframe == "M1":
        result = df.copy()
    else:
        rule = TIMEFRAMES[timeframe]

        result = df.resample(rule).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
        })

        result = result.dropna()

    if len(result) < 60:
        return None

    return add_indicators(result)


def analyze_market(df):
    if df is None or len(df) < 60:
        return None

    row = df.iloc[-1]

    values = [
        row["close"],
        row["ema9"],
        row["ema21"],
        row["ema50"],
        row["rsi"],
        row["macd"],
        row["macd_signal"],
        row["atr"],
        row["adx"],
    ]

    if not np.isfinite(values).all():
        return None

    buy_score = 0
    sell_score = 0

    if row["ema9"] > row["ema21"]:
        buy_score += 1
    elif row["ema9"] < row["ema21"]:
        sell_score += 1

    if row["ema21"] > row["ema50"]:
        buy_score += 1
    elif row["ema21"] < row["ema50"]:
        sell_score += 1

    if row["macd"] > row["macd_signal"]:
        buy_score += 1
    elif row["macd"] < row["macd_signal"]:
        sell_score += 1

    if 50 < row["rsi"] < 70:
        buy_score += 1
    elif 30 < row["rsi"] < 50:
        sell_score += 1

    if row["adx"] >= 20:
        if buy_score > sell_score:
            buy_score += 1
        elif sell_score > buy_score:
            sell_score += 1

    direction = "WAIT"

    if buy_score >= 4 and buy_score > sell_score:
        direction = "BUY ANALYSIS"
    elif sell_score >= 4 and sell_score > buy_score:
        direction = "SELL ANALYSIS"

    return {
        "direction": direction,
        "score": max(buy_score, sell_score),
        "price": float(row["close"]),
        "rsi": float(row["rsi"]),
        "adx": float(row["adx"]),
        "atr": float(row["atr"]),
        "support": float(row["support"]),
        "resistance": float(row["resistance"]),
        "time": df.index[-1].isoformat(),
    }


def save_signal(symbol, timeframe, result):
    record = {
        "recorded_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "symbol": symbol,
        "timeframe": timeframe,
        **result,
    }

    new_row = pd.DataFrame([record])

    if SIGNAL_FILE.exists():
        try:
            old = pd.read_csv(SIGNAL_FILE)
            new_row = pd.concat(
                [old, new_row],
                ignore_index=True,
            )
        except (OSError, ValueError) as error:
            logging.warning("Signal history read error: %s", error)

    new_row = new_row.drop_duplicates(
        subset=["symbol", "timeframe", "time"],
        keep="last",
    )

    new_row.to_csv(SIGNAL_FILE, index=False)


def make_report(symbol, timeframe, result):
    direction = result["direction"]

    return (
        "<b>Punjab Trading Scanner</b>\n\n"
        f"<b>Symbol:</b> {symbol}\n"
        f"<b>Timeframe:</b> {timeframe}\n"
        f"<b>Analysis:</b> {direction}\n"
        f"<b>Indicator score:</b> {result['score']}/5\n"
        f"<b>Observed price:</b> {result['price']:.5f}\n"
        f"<b>RSI:</b> {result['rsi']:.2f}\n"
        f"<b>ADX:</b> {result['adx']:.2f}\n"
        f"<b>ATR:</b> {result['atr']:.5f}\n"
        f"<b>Support estimate:</b> {result['support']:.5f}\n"
        f"<b>Resistance estimate:</b> {result['resistance']:.5f}\n\n"
        "<i>Educational indicator analysis only. "
        "Not a trade instruction or guarantee. "
        "No real orders are placed.</i>"
    )


def main():
    logging.info("Punjab Trading Scanner started.")

    sent = 0
    saved = 0
    issues = 0

    for symbol in SYMBOLS:
        logging.info("Scanning %s", symbol)

        market_data = fetch_market_data(symbol)

        if market_data is None or market_data.empty:
            issues += 1
            time.sleep(REQUEST_DELAY)
            continue

        try:
            save_market_history(symbol, market_data)
        except (OSError, ValueError) as error:
            logging.error(
                "History save failed for %s: %s",
                symbol,
                error,
            )
            issues += 1

        for timeframe in TIMEFRAMES:
            try:
                prepared = prepare_timeframe(
                    market_data,
                    timeframe,
                )

                result = analyze_market(prepared)

                if result is None:
                    continue

                save_signal(
                    symbol,
                    timeframe,
                    result,
                )
                saved += 1

                if result["direction"] != "WAIT":
                    if send_telegram(
                        make_report(
                            symbol,
                            timeframe,
                            result,
                        )
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
        "<b>Punjab Scanner Complete</b>\n\n"
        f"Alerts sent: {sent}\n"
        f"Records saved: {saved}\n"
        f"Issues: {issues}\n\n"
        "<i>Paper analysis only. No real orders placed.</i>"
    )

    send_telegram(summary)

    logging.info(
        "Scan complete | Sent=%s Saved=%s Issues=%s",
        sent,
        saved,
        issues,
    )


if __name__ == "__main__":
    main()
