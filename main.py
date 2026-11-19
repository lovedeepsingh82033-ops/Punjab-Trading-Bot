
import os
import time
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# ================= CONFIGURATION =================

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

MIN_SCORE = 70
DELAY = 2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)
log = logging.getLogger(__name__)

# ================= TELEGRAM =================

def send_message(message):
    if not TOKEN or not CHAT_ID:
        log.error("Telegram settings are missing")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=20
        )
        response.raise_for_status()
        return response.json().get("ok", False)

    except Exception as error:
        log.error("Telegram error: %s", error)
        return False


# ================= MARKET DATA =================

def fetch_data(symbol):
    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": symbol,
        "interval": "1min",
        "outputsize": 500,
        "apikey": API_KEY,
        "timezone": "UTC"
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        if "values" not in data:
            log.error(
                "Twelve Data error for %s: %s",
                symbol,
                data.get("message", data)
            )
            return None

        df = pd.DataFrame(data["values"])

        df["datetime"] = pd.to_datetime(
            df["datetime"],
            utc=True
        )

        df = df.set_index("datetime").sort_index()

        for column in ["open", "high", "low", "close"]:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

        df = df.dropna()

        return df

    except Exception as error:
        log.error("Data error %s: %s", symbol, error)
        return None


# ================= TIMEFRAME CONVERSION =================

def make_timeframe(df, timeframe):
    rule = TIMEFRAMES[timeframe]

    candles = df.resample(
        rule,
        label="right",
        closed="right"
    ).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last"
    })

    candles = candles.dropna()

    if len(candles) < 60:
        return None

    return candles


# ================= INDICATORS =================

def calculate_indicators(df):
    df = df.copy()

    close = df["close"]
    high = df["high"]
    low = df["low"]

    # EMA
    df["ema9"] = close.ewm(
        span=9, adjust=False
    ).mean()

    df["ema21"] = close.ewm(
        span=21, adjust=False
    ).mean()

    df["ema50"] = close.ewm(
        span=50, adjust=False
    ).mean()

    # RSI
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1/14, adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1/14, adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    df["rsi"] = 100 - (100 / (1 + rs))
    df["rsi"] = df["rsi"].fillna(50)

    # MACD
    ema12 = close.ewm(
        span=12, adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26, adjust=False
    ).mean()

    df["macd"] = ema12 - ema26

    df["macd_signal"] = df["macd"].ewm(
        span=9, adjust=False
    ).mean()

    # ATR
    previous_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs()
        ],
        axis=1
    ).max(axis=1)

    df["atr"] = tr.ewm(
        alpha=1/14, adjust=False
    ).mean()

    # ADX
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where(
            (up_move > down_move) & (up_move > 0),
            up_move,
            0
        ),
        index=df.index
    )

    minus_dm = pd.Series(
        np.where(
            (down_move > up_move) & (down_move > 0),
            down_move,
            0
        ),
        index=df.index
    )

    atr_safe = df["atr"].replace(0, np.nan)

    plus_di = (
        100 * plus_dm.ewm(alpha=1/14, adjust=False).mean()
        / atr_safe
    )

    minus_di = (
        100 * minus_dm.ewm(alpha=1/14, adjust=False).mean()
        / atr_safe
    )

    dx = (
        100 * (plus_di - minus_di).abs()
        / (plus_di + minus_di).replace(0, np.nan)
    )

    df["adx"] = dx.ewm(
        alpha=1/14, adjust=False
    ).mean()

    # Bollinger Bands
    middle = close.rolling(20).mean()
    deviation = close.rolling(20).std()

    df["bb_upper"] = middle + 2 * deviation
    df["bb_lower"] = middle - 2 * deviation

    # Support and resistance
    df["support"] = low.rolling(20).min()
    df["resistance"] = high.rolling(20).max()

    return df.dropna()


# ================= SIGNAL ANALYSIS =================

def analyze(symbol, timeframe, candles):
    df = calculate_indicators(candles)

    if df is None or len(df) < 5:
        return None

    last = df.iloc[-1]

    price = float(last["close"])
    atr = float(last["atr"])

    if not np.isfinite(atr) or atr <= 0:
        return None

    buy_score = 0
    sell_score = 0

    # EMA trend
    if last["ema9"] > last["ema21"]:
        buy_score += 20
    elif last["ema9"] < last["ema21"]:
        sell_score += 20

    if last["ema21"] > last["ema50"]:
        buy_score += 15
    elif last["ema21"] < last["ema50"]:
        sell_score += 15

    # RSI
    if 50 < last["rsi"] < 70:
        buy_score += 15
    elif 30 < last["rsi"] < 50:
        sell_score += 15

    # MACD
    if last["macd"] > last["macd_signal"]:
        buy_score += 20
    elif last["macd"] < last["macd_signal"]:
        sell_score += 20

    # ADX trend strength
    if last["adx"] >= 20:
        if buy_score > sell_score:
            buy_score += 15
        elif sell_score > buy_score:
            sell_score += 15

    # Bollinger position
    if price > last["bb_upper"]:
        sell_score += 10
    elif price < last["bb_lower"]:
        buy_score += 10

    # Support and resistance
    if price > last["support"]:
        buy_score += 5

    if price < last["resistance"]:
        sell_score += 5

    if buy_score >= MIN_SCORE and buy_score > sell_score:
        direction = "BUY"
        score = buy_score
        stop_loss = price - (1.5 * atr)
        take_profit = price + (3 * atr)

    elif sell_score >= MIN_SCORE and sell_score > buy_score:
        direction = "SELL"
        score = sell_score
        stop_loss = price + (1.5 * atr)
        take_profit = price - (3 * atr)

    else:
        return None

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "score": score,
        "entry": price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "rsi": float(last["rsi"]),
        "adx": float(last["adx"]),
        "support": float(last["support"]),
        "resistance": float(last["resistance"])
    }


# ================= SIGNAL REPORT =================

def make_report(signal):
    return (
        "🚨 <b>PUNJAB FOREX SIGNAL</b>\n\n"
        f"📊 Pair: <b>{signal['symbol']}</b>\n"
        f"⏱ Timeframe: <b>{signal['timeframe']}</b>\n"
        f"📈 Signal: <b>{signal['direction']}</b>\n"
        f"🎯 Signal Score: <b>{signal['score']}%</b>\n\n"
        f"💰 Entry: <code>{signal['entry']:.5f}</code>\n"
        f"🛑 Stop Loss: <code>{signal['stop_loss']:.5f}</code>\n"
        f"🏆 Take Profit: <code>{signal['take_profit']:.5f}</code>\n\n"
        f"RSI: {signal['rsi']:.2f}\n"
        f"ADX: {signal['adx']:.2f}\n"
        f"Support: {signal['support']:.5f}\n"
        f"Resistance: {signal['resistance']:.5f}\n\n"
        "⚠️ Educational signal only. Not financial advice."
    )


# ================= FOREX LEARNING =================

FOREX_LESSONS = [
    "Lesson 1: Forex is the market where currencies are exchanged.",
    "Lesson 2: EUR/USD shows the Euro against the US Dollar.",
    "Lesson 3: A pip measures movement in a currency pair.",
    "Lesson 4: Spread is the difference between bid and ask price.",
    "Lesson 5: Stop Loss helps limit potential losses.",
    "Lesson 6: Take Profit is a target for closing a trade.",
    "Lesson 7: RSI helps measure market momentum.",
    "Lesson 8: EMA helps identify the market trend.",
    "Lesson 9: Risk management is important in trading.",
    "Lesson 10: Never risk money you cannot afford to lose."
]


def send_forex_lesson():
    day = datetime.now(timezone.utc).timetuple().tm_yday
    lesson = FOREX_LESSONS[day % len(FOREX_LESSONS)]

    send_message(
        "🎓 <b>PUNJAB FOREX ACADEMY</b>\n\n" + lesson
    )


# ================= MAIN SCAN =================

def main():
    if not API_KEY or not TOKEN or not CHAT_ID:
        raise SystemExit(
            "Missing TELEGRAM_TOKEN, CHAT_ID or TWELVE_DATA_API_KEY."
        )

    sent = 0
    issues = 0

    for symbol in SYMBOLS:
        log.info("Getting data for %s", symbol)

        raw_data = fetch_data(symbol)

        if raw_data is None:
            issues += 1
            continue

        for timeframe in TIMEFRAMES:
            candles = make_timeframe(raw_data, timeframe)

            if candles is None:
                issues += 1
                continue

            signal = analyze(
                symbol,
                timeframe,
                candles
            )

            if signal:
                if send_message(make_report(signal)):
                    sent += 1

            time.sleep(DELAY)

    send_message(
        "<b>Punjab Forex Scan Complete</b>\n\n"
        f"Signals sent: {sent}\n"
        f"Data/analysis issues: {issues}\n\n"
        "No signal means no setup passed the filter."
    )

    send_forex_lesson()

    log.info(
        "Scan complete. Signals=%s Issues=%s",
        sent,
        issues
    )


if __name__ == "__main__":
    main()
