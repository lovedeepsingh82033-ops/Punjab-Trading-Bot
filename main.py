
import os
import time
import logging
import requests
import pandas as pd

# =====================================================
# PUNJAB TRADING SIGNALS - PRO QUANT V1
# Signal-only engine. No automatic trade execution.
# =====================================================

TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")

SYMBOLS = os.getenv(
    "SYMBOLS",
    "EUR/USD,GBP/USD,USD/JPY,AUD/USD,USD/CAD,"
    "NZD/USD, XAU/USD"
).split(",")

TIMEFRAMES = os.getenv(
    "TIMEFRAMES", "M15,H1,H4"
).split(",")

MIN_SCORE = int(os.getenv("MIN_SIGNAL_SCORE", "70"))
DELAY = float(os.getenv("API_CALL_DELAY_SECONDS", "8"))

BASE_URL = "https://api.twelvedata.com/time_series"

INTERVALS = {
    "M1": "1min",
    "M5": "5min",
    "M15": "15min",
    "M30": "30min",
    "H1": "1h",
    "H4": "4h",
    "D1": "1day",
    "W1": "1week"
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

log = logging.getLogger("PunjabQuant")


# ---------------- TELEGRAM ----------------

def send_message(message):

    if not TOKEN or not CHAT_ID:
        log.error("Telegram credentials missing")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=20
        )

        response.raise_for_status()
        return response.json().get("ok", False)

    except requests.RequestException as error:
        log.error("Telegram error: %s", error)
        return False


# ---------------- MARKET DATA ----------------

# FOREX LEARNING MODE

FOREX_LESSONS = [
    "Lesson 1: What is Forex? Forex is the market where one currency is exchanged for another.",
    "Lesson 2: What is a Currency Pair? EUR/USD shows the Euro against the US Dollar.",
    "Lesson 3: What is a Pip? A pip is a standard unit used to measure price movement.",
    "Lesson 4: What is Spread? Spread is the difference between the buying and selling price.",
    "Lesson 5: What is Stop Loss? A stop loss helps limit potential trading losses."
]

def send_forex_lesson():
    lesson_number = int(time.time() // 86400) % len(FOREX_LESSONS)
    message = "🎓 <b>PUNJAB FOREX ACADEMY</b>\n\n" + FOREX_LESSONS[lesson_number]
    send_message(message)


def fetch_data(symbol, timeframe):

    if timeframe == "M2":
        df = fetch_data(symbol, "M1")

        if df is None:
            return None

        return df.resample(
            "2min", label="right", closed="right"
        ).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum"
        }).dropna()

    interval = INTERVALS.get(timeframe)

    if interval is None:
        return None

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": 300,
        "apikey": API_KEY,
        "timezone": "UTC"
    }

    try:
        response = requests.get(
            BASE_URL, params=params, timeout=25
        )

        response.raise_for_status()
        result = response.json()

        if "values" not in result:
            log.warning(
                "%s: %s",
                symbol,
                result.get("message", "No data")
            )
            return None

        df = pd.DataFrame(result["values"])

        df["datetime"] = pd.to_datetime(
            df["datetime"], utc=True
        )

        df.set_index("datetime", inplace=True)
        df.sort_index(inplace=True)

        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(
                df[col], errors="coerce"
            )

        if "volume" not in df:
            df["volume"] = 0

        df["volume"] = pd.to_numeric(
            df["volume"], errors="coerce"
        ).fillna(0)

        df = df[
            ["open", "high", "low", "close", "volume"]
        ].dropna()

        # Ignore the latest potentially unfinished candle.
        if len(df) > 1:
            df = df.iloc[:-1]

        if len(df) < 60:
            return None

        return df

    except (requests.RequestException, ValueError, KeyError) as error:
        log.error("Market data error: %s", error)
        return None


# ---------------- INDICATORS ----------------

def calculate_indicators(df):

    d = df.copy()
    close = d["close"]
    high = d["high"]
    low = d["low"]

    for period in [9, 21, 50, 100, 200]:
        d[f"ema{period}"] = close.ewm(
            span=period, adjust=False
        ).mean()

    # RSI 14
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1/14, adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1/14, adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(0, float("nan"))

    d["rsi"] = (
        100 - (100 / (1 + rs))
    ).fillna(50)

    # MACD
    ema12 = close.ewm(
        span=12, adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26, adjust=False
    ).mean()

    d["macd"] = ema12 - ema26

    d["macd_signal"] = d["macd"].ewm(
        span=9, adjust=False
    ).mean()

    # ATR
    previous = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - previous).abs(),
        (low - previous).abs()
    ], axis=1).max(axis=1)

    d["atr"] = tr.ewm(
        alpha=1/14, adjust=False
    ).mean()

    # ADX
    up = high.diff()
    down = -low.diff()

    plus_dm = up.where(
        (up > down) & (up > 0), 0
    )

    minus_dm = down.where(
        (down > up) & (down > 0), 0
    )

    plus_di = (
        100 * plus_dm.ewm(alpha=1/14).mean()
        / d["atr"].replace(0, float("nan"))
    )

    minus_di = (
        100 * minus_dm.ewm(alpha=1/14).mean()
        / d["atr"].replace(0, float("nan"))
    )

    dx = (
        100 * (plus_di - minus_di).abs()
        / (plus_di + minus_di).replace(0, float("nan"))
    )

    d["adx"] = dx.ewm(
        alpha=1/14
    ).mean().fillna(0)

    d["plus_di"] = plus_di.fillna(0)
    d["minus_di"] = minus_di.fillna(0)

    # Bollinger Bands
    middle = close.rolling(20).mean()
    deviation = close.rolling(20).std()

    d["bb_upper"] = middle + 2 * deviation
    d["bb_lower"] = middle - 2 * deviation

    # Support and resistance
    d["support"] = low.rolling(20).min()
    d["resistance"] = high.rolling(20).max()

    return d


# ---------------- SIGNAL ANALYSIS ----------------

def analyze(symbol, timeframe, df):

    d = calculate_indicators(df).dropna()

    if len(d) < 5:
        return None

    last = d.iloc[-1]
    previous = d.iloc[-2]

    price = float(last["close"])
    atr = float(last["atr"])

    if atr <= 0:
        return None

    buy = 0
    sell = 0

    buy_reasons = []
    sell_reasons = []

    # EMA trend
    if last["ema9"] > last["ema21"]:
        buy += 15
        buy_reasons.append("EMA bullish")

    elif last["ema9"] < last["ema21"]:
        sell += 15
        sell_reasons.append("EMA bearish")

    if last["ema21"] > last["ema50"]:
        buy += 10
        buy_reasons.append("Medium trend bullish")

    elif last["ema21"] < last["ema50"]:
        sell += 10
        sell_reasons.append("Medium trend bearish")

    if price > last["ema200"]:
        buy += 10
        buy_reasons.append("Above EMA200")

    elif price < last["ema200"]:
        sell += 10
        sell_reasons.append("Below EMA200")

    # RSI
    if 50 < last["rsi"] < 70:
        buy += 15
        buy_reasons.append("Bullish RSI")

    elif 30 < last["rsi"] < 50:
        sell += 15
        sell_reasons.append("Bearish RSI")

    # MACD
    if last["macd"] > last["macd_signal"]:
        buy += 15
        buy_reasons.append("MACD bullish")

    elif last["macd"] < last["macd_signal"]:
        sell += 15
        sell_reasons.append("MACD bearish")

    # ADX direction
    if last["adx"] >= 20:
        if last["plus_di"] > last["minus_di"]:
            buy += 10
            buy_reasons.append("ADX bullish trend")

        elif last["minus_di"] > last["plus_di"]:
            sell += 10
            sell_reasons.append("ADX bearish trend")

    # Bollinger confirmation
    if price > last["bb_upper"]:
        buy += 5
        buy_reasons.append("Upper band breakout")

    elif price < last["bb_lower"]:
        sell += 5
        sell_reasons.append("Lower band breakout")

    # Extreme momentum penalty
    if last["rsi"] >= 75:
        buy -= 15

    if last["rsi"] <= 25:
        sell -= 15

    if buy >= MIN_SCORE and buy > sell:

        direction = "BUY"
        score = buy
        reasons = buy_reasons

        stop = price - 1.5 * atr
        risk = price - stop

        targets = (
            price + risk,
            price + 2 * risk,
            price + 3 * risk
        )

    elif sell >= MIN_SCORE and sell > buy:

        direction = "SELL"
        score = sell
        reasons = sell_reasons

        stop = price + 1.5 * atr
        risk = stop - price

        targets = (
            price - risk,
            price - 2 * risk,
            price - 3 * risk
        )

    else:

        direction = "WAIT"
        score = max(buy, sell)
        reasons = ["No confirmed setup"]

        stop = price
        targets = (price, price, price)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "score": min(max(int(score), 0), 100),
        "entry": price,
        "stop": stop,
        "targets": targets,
        "rsi": float(last["rsi"]),
        "macd": float(last["macd"]),
        "adx": float(last["adx"]),
        "atr": atr,
        "support": float(last["support"]),
        "resistance": float(last["resistance"]),
        "reasons": reasons
    }


# ---------------- TELEGRAM REPORT ----------------

def format_price(value):
    return f"{value:.6f}".rstrip("0").rstrip(".")


def make_report(s):

    icon = (
        "🟢" if s["direction"] == "BUY"
        else "🔴" if s["direction"] == "SELL"
        else "🟡"
    )

    if s["direction"] == "WAIT":
        levels = "No confirmed entry, SL or TP."
    else:
        levels = (
            f"Entry: {format_price(s['entry'])}\n"
            f"Stop Loss: {format_price(s['stop'])}\n"
            f"TP1: {format_price(s['targets'][0])}\n"
            f"TP2: {format_price(s['targets'][1])}\n"
            f"TP3: {format_price(s['targets'][2])}"
        )

    reasons = "\n".join(
        "• " + reason for reason in s["reasons"]
    )

    return (
        f"{icon} <b>PUNJAB QUANT SIGNAL</b>\n\n"
        f"<b>{s['symbol']} | {s['timeframe']}</b>\n"
        f"<b>Signal: {s['direction']}</b>\n"
        f"Setup score: {s['score']}/100\n\n"
        f"{levels}\n\n"
        f"<b>INDICATORS</b>\n"
        f"RSI: {s['rsi']:.2f}\n"
        f"MACD: {s['macd']:.6f}\n"
        f"ADX: {s['adx']:.2f}\n"
        f"ATR: {format_price(s['atr'])}\n"
        f"Support: {format_price(s['support'])}\n"
        f"Resistance: {format_price(s['resistance'])}\n\n"
        f"<b>ANALYSIS</b>\n{reasons}\n\n"
        "⚠️ Educational signal only. Not a profit guarantee. "
        "Check spread, news and execution risk."
    )


# ---------------- MAIN SCAN ----------------

def main():

    if not API_KEY or not TOKEN or not CHAT_ID:
        raise SystemExit(
            "Set TELEGRAM_TOKEN, CHAT_ID and TWELVE_DATA_API_KEY secrets."
        )

    sent = 0
    issues = 0

    for symbol in SYMBOLS:
            log.info("Scan complete. Alerts=%s Issues=%s", sent, issues)
        symbol = symbol.strip().upper()

        for timeframe in TIMEFRAMES:

            timeframe = timeframe.strip().upper()

            if timeframe not in set(INTERVALS) | {"M2"}:
                log.warning("Unsupported timeframe %s", timeframe)
                continue

            log.info("Scanning %s %s", symbol, timeframe)

            df = fetch_data(symbol, timeframe)

            if df is None:
                issues += 1
                time.sleep(DELAY)
                continue

            signal = analyze(symbol, timeframe, df)

            if signal is None:
                issues += 1

            elif signal["direction"] in ("BUY", "SELL"):
                if send_message(make_report(signal)):
                    sent += 1

            time.sleep(DELAY)

    send_message(
        "<b>Punjab Quant Scan Complete</b>\n"
        f"Alerts sent: {sent}\n"
        f"Data/analysis issues: {issues}\n"
        "No alert means no setup passed the configured filter."
    )

                
        log.info("Scan complete. Alerts=%s Issues=%s", sent, issues)


if __name__ == "__main__":
    main()
