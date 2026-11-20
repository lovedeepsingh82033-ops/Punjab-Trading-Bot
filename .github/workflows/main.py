
import os
import time
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# ==================================================
# PUNJAB TRADING BOT — EDUCATIONAL / PAPER TESTING
# ==================================================

TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")

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
    "M2": "2min",
    "M5": "5min",
    "M10": "10min",
}

API_URL = "https://api.twelvedata.com/time_series"
DELAY = 2
HISTORY_FILE = "signal_history.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


# ==================================================
# TELEGRAM
# ==================================================

def send_message(message):
    if not TOKEN or not CHAT_ID:
        logging.error("Telegram secrets are missing.")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
            },
            timeout=20,
        )
        response.raise_for_status()

        result = response.json()
        if not result.get("ok"):
            logging.error("Telegram API returned an error.")
            return False

        return True

    except requests.RequestException as error:
        logging.error("Telegram error: %s", error)
        return False


# ==================================================
# MARKET DATA
# ==================================================

def fetch_data(symbol):
    if not API_KEY:
        logging.error("Twelve Data API key is missing.")
        return None

    params = {
        "symbol": symbol,
        "interval": "1min",
        "outputsize": 500,
        "timezone": "UTC",
        "apikey": API_KEY,
    }

    try:
        response = requests.get(
            API_URL,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()

        if "values" not in result:
            logging.error(
                "No market data for %s: %s",
                symbol,
                result.get("message", "Unknown API response"),
            )
            return None

        df = pd.DataFrame(result["values"])

        required = ["datetime", "open", "high", "low", "close"]
        if not all(column in df.columns for column in required):
            logging.error("Missing columns for %s", symbol)
            return None

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
            subset=["datetime", "open", "high", "low", "close"]
        )

        df = df.set_index("datetime")
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="last")]

        if len(df) < 50:
            logging.warning("Not enough candles for %s", symbol)
            return None

        return df

    except (requests.RequestException, ValueError, KeyError) as error:
        logging.error("Data error for %s: %s", symbol, error)
        return None


# ==================================================
# TIMEFRAME CONVERSION
# ==================================================

def convert_timeframe(df, timeframe):
    rule = TIMEFRAMES.get(timeframe)

    if rule is None:
        return None

    try:
        converted = df.resample(rule).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
        })

        converted = converted.dropna()

        if len(converted) < 30:
            return None

        return converted

    except (ValueError, KeyError) as error:
        logging.error("Resampling error: %s", error)
        return None


# ==================================================
# TECHNICAL INDICATORS
# ==================================================

def calculate_indicators(df):
    df = df.copy()

    close = df["close"]
    high = df["high"]
    low = df["low"]

    # EMA
    df["EMA_9"] = close.ewm(
        span=9, adjust=False
    ).mean()

    df["EMA_21"] = close.ewm(
        span=21, adjust=False
    ).mean()

    df["EMA_50"] = close.ewm(
        span=50, adjust=False
    ).mean()

    # RSI
    change = close.diff()

    gain = change.clip(lower=0)
    loss = -change.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / 14,
        min_periods=14,
        adjust=False,
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / 14,
        min_periods=14,
        adjust=False,
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))
    df["RSI"] = df["RSI"].fillna(50)

    # MACD
    ema12 = close.ewm(
        span=12, adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26, adjust=False
    ).mean()

    df["MACD"] = ema12 - ema26

    df["MACD_SIGNAL"] = df["MACD"].ewm(
        span=9, adjust=False
    ).mean()

    # ATR
    previous_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df["ATR"] = tr.rolling(14).mean()

    # ADX
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where(
            (up_move > down_move) & (up_move > 0),
            up_move,
            0,
        ),
        index=df.index,
    )

    minus_dm = pd.Series(
        np.where(
            (down_move > up_move) & (down_move > 0),
            down_move,
            0,
        ),
        index=df.index,
    )

    atr_safe = df["ATR"].replace(0, np.nan)

    plus_di = (
        100 * plus_dm.rolling(14).mean() / atr_safe
    )

    minus_di = (
        100 * minus_dm.rolling(14).mean() / atr_safe
    )

    dx = (
        100
        * (plus_di - minus_di).abs()
        / (plus_di + minus_di).replace(0, np.nan)
    )

    df["ADX"] = dx.rolling(14).mean()

    # Bollinger Bands
    middle = close.rolling(20).mean()
    deviation = close.rolling(20).std()

    df["BB_MIDDLE"] = middle
    df["BB_UPPER"] = middle + (2 * deviation)
    df["BB_LOWER"] = middle - (2 * deviation)

    # Support and resistance
    df["SUPPORT"] = low.rolling(20).min()
    df["RESISTANCE"] = high.rolling(20).max()

    return df.dropna()


# ==================================================
# SIGNAL ANALYSIS
# ==================================================

def analyze(df, symbol, timeframe):
    if df is None or len(df) < 30:
        return None

    try:
        data = calculate_indicators(df)

        if data.empty:
            return None

        last = data.iloc[-1]
        previous = data.iloc[-2]

        score_buy = 0
        score_sell = 0
        reasons = []

        # EMA trend
        if last["EMA_9"] > last["EMA_21"]:
            score_buy += 20
            reasons.append("EMA trend bullish")

        elif last["EMA_9"] < last["EMA_21"]:
            score_sell += 20
            reasons.append("EMA trend bearish")

        # RSI
        if 50 < last["RSI"] < 70:
            score_buy += 15
            reasons.append("RSI bullish")

        elif 30 < last["RSI"] < 50:
            score_sell += 15
            reasons.append("RSI bearish")

        # MACD
        if last["MACD"] > last["MACD_SIGNAL"]:
            score_buy += 15
            reasons.append("MACD bullish")

        elif last["MACD"] < last["MACD_SIGNAL"]:
            score_sell += 15
            reasons.append("MACD bearish")

        # EMA 50 trend
        if last["close"] > last["EMA_50"]:
            score_buy += 15
            reasons.append("Above EMA 50")

        elif last["close"] < last["EMA_50"]:
            score_sell += 15
            reasons.append("Below EMA 50")

        # ADX trend strength
        if last["ADX"] >= 25:
            if score_buy > score_sell:
                score_buy += 10
            elif score_sell > score_buy:
                score_sell += 10

        # Bollinger position
        if last["close"] > last["BB_MIDDLE"]:
            score_buy += 10

        elif last["close"] < last["BB_MIDDLE"]:
            score_sell += 10

        # Recent candle direction
        if last["close"] > previous["close"]:
            score_buy += 5

        elif last["close"] < previous["close"]:
            score_sell += 5

        if score_buy >= 60 and score_buy > score_sell:
            direction = "BUY"
            score = score_buy

        elif score_sell >= 60 and score_sell > score_buy:
            direction = "SELL"
            score = score_sell

        else:
            return None

        return {
            "time": datetime.now(timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            ),
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "score": int(score),
            "price": float(last["close"]),
            "rsi": float(last["RSI"]),
            "adx": float(last["ADX"]),
            "atr": float(last["ATR"]),
            "support": float(last["SUPPORT"]),
            "resistance": float(last["RESISTANCE"]),
            "reasons": reasons,
        }

    except (ValueError, KeyError, IndexError, TypeError) as error:
        logging.error(
            "Analysis error for %s %s: %s",
            symbol,
            timeframe,
            error,
        )
        return None


# ==================================================
# SIGNAL REPORT
# ==================================================

def make_report(signal):
    reasons = "\n".join(
        f"• {reason}" for reason in signal["reasons"]
    )

    return (
        "<b>Punjab Forex Scan</b>\n\n"
        f"<b>Symbol:</b> {signal['symbol']}\n"
        f"<b>Timeframe:</b> {signal['timeframe']}\n"
        f"<b>Direction:</b> {signal['direction']}\n"
        f"<b>Score:</b> {signal['score']}/100\n"
        f"<b>Observed price:</b> {signal['price']:.5f}\n"
        f"<b>RSI:</b> {signal['rsi']:.2f}\n"
        f"<b>ADX:</b> {signal['adx']:.2f}\n"
        f"<b>ATR:</b> {signal['atr']:.5f}\n"
        f"<b>Support:</b> {signal['support']:.5f}\n"
        f"<b>Resistance:</b> {signal['resistance']:.5f}\n\n"
        f"<b>Analysis:</b>\n{reasons}\n\n"
        "<i>Educational paper-testing signal only. "
        "Score is a heuristic, not a probability or guarantee. "
        "Not a real trade instruction.</i>"
    )


# ==================================================
# SIGNAL HISTORY
# ==================================================

def save_signal_history(signal):
    record = {
        "time": signal["time"],
        "symbol": signal["symbol"],
        "timeframe": signal["timeframe"],
        "direction": signal["direction"],
        "score": signal["score"],
        "price": signal["price"],
        "rsi": signal["rsi"],
        "adx": signal["adx"],
        "atr": signal["atr"],
        "support": signal["support"],
        "resistance": signal["resistance"],
    }

    try:
        pd.DataFrame([record]).to_csv(
            HISTORY_FILE,
            mode="a",
            header=not os.path.exists(HISTORY_FILE),
            index=False,
        )
        return True

    except (OSError, ValueError) as error:
        logging.error("History save error: %s", error)
        return False


# ==================================================
# DAILY FOREX LEARNING
# ==================================================

FOREX_LESSONS = [
    "Learn the basics of currency pairs and pips.",
    "Understand support and resistance.",
    "Study EMA and moving averages.",
    "Learn RSI and momentum.",
    "Understand MACD signals.",
    "Study ATR and market volatility.",
    "Learn risk management concepts.",
    "Understand trend and sideways markets.",
    "Study candlestick patterns.",
    "Practice with historical charts.",
    "Learn why news affects currency markets.",
    "Understand trading psychology.",
    "Study spread and transaction costs.",
    "Learn the limitations of technical indicators.",
]


def get_daily_lesson():
    day = datetime.now(timezone.utc).timetuple().tm_yday
    index = (day - 1) % len(FOREX_LESSONS)
    return FOREX_LESSONS[index]


# ==================================================
# MAIN SCAN
# ==================================================

def main():
    logging.info("Punjab Forex Scan Started")

    if not API_KEY:
        logging.error("Missing TWELVE_DATA_API_KEY.")
        send_message(
            "<b>Punjab Forex Bot Error</b>\n"
            "Twelve Data API key is missing."
        )
        return

    if not TOKEN or not CHAT_ID:
        logging.error("Missing Telegram secrets.")
        return

    sent = 0
    saved = 0
    issues = 0

    for symbol in SYMBOLS:
        logging.info("Fetching %s", symbol)

        market_data = fetch_data(symbol)

        if market_data is None:
            issues += 1
            continue

        for timeframe in TIMEFRAMES:
            candles = convert_timeframe(
                market_data,
                timeframe,
            )

            if candles is None:
                issues += 1
                continue

            signal = analyze(
                candles,
                symbol,
                timeframe,
            )

            if signal:
                if save_signal_history(signal):
                    saved += 1

                if send_message(make_report(signal)):
                    sent += 1

            time.sleep(DELAY)

    summary = (
        "<b>Punjab Forex Scan Complete</b>\n\n"
        f"Signals sent: {sent}\n"
        f"History records saved: {saved}\n"
        f"Data/analysis issues: {issues}\n\n"
        "<b>Daily Learning:</b>\n"
        f"{get_daily_lesson()}\n\n"
        "<i>Educational paper testing only. "
        "No real trades are executed.</i>"
    )

    send_message(summary)

    logging.info(
        "Scan complete. Sent=%s Saved=%s Issues=%s",
        sent,
        saved,
        issues,
    )


# ==================================================
# PROGRAM START
# ==================================================

if __name__ == "__main__":
    main()
