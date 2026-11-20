import os
import time
import logging
from datetime import datetime, timezone, timedelta

import requests
import pandas as pd
import numpy as np

# Punjab Market Scanner
# Educational market-data analysis and Telegram alerts only.
# No broker connection, no order placement, and no profit guarantee.

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()

SYMBOLS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD",
    "USD/CAD", "NZD/USD", "XAU/USD"
]
TIMEFRAMES = {
    "M5": ("5min", 5),
    "M15": ("15min", 15),
    "M30": ("30min", 30),
    "H1": ("1h", 60),
}
OUTPUT_SIZE = 250
MIN_CANDLES = 100
HISTORY_FILE = "signal_history.csv"
API_URL = "https://api.twelvedata.com/time_series"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

session = requests.Session()


def telegram(message):
    if not TOKEN or not CHAT_ID:
        logging.error("Telegram secrets are missing.")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        response = session.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=25,
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            logging.error("Telegram rejected message: %s", result)
        return bool(result.get("ok"))
    except requests.RequestException as exc:
        logging.error("Telegram send failed: %s", exc)
        return False


def fetch_candles(symbol, interval):
    if not API_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY is missing.")

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": OUTPUT_SIZE,
        "apikey": API_KEY,
        "format": "JSON",
        "timezone": "UTC",
    }

    last_error = None
    for attempt in range(3):
        try:
            response = session.get(API_URL, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()

            if "values" not in payload:
                message = payload.get("message") or payload.get("code") or str(payload)
                raise RuntimeError(f"Twelve Data response: {message}")

            df = pd.DataFrame(payload["values"])
            required = ["datetime", "open", "high", "low", "close"]
            if any(column not in df.columns for column in required):
                raise RuntimeError("API response is missing required candle columns.")

            for column in ["open", "high", "low", "close"]:
                df[column] = pd.to_numeric(df[column], errors="coerce")

            df["datetime"] = pd.to_datetime(
                df["datetime"], utc=True, errors="coerce"
            )
            df = (
                df.dropna(subset=required)
                  .sort_values("datetime")
                  .drop_duplicates(subset=["datetime"])
                  .reset_index(drop=True)
            )

            # Exclude a candle that may still be forming.
            minutes = next(v[1] for v in TIMEFRAMES.values()
                           if v[0] == interval)
            now = datetime.now(timezone.utc)
            df = df[df["datetime"] + timedelta(minutes=minutes) <= now]
            return df.reset_index(drop=True)

        except (requests.RequestException, RuntimeError, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(4 * (attempt + 1))

    raise RuntimeError(f"Could not fetch {symbol} {interval}: {last_error}")


def add_indicators(df):
    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]

    df["ema9"] = close.ewm(span=9, adjust=False).mean()
    df["ema21"] = close.ewm(span=21, adjust=False).mean()
    df["ema50"] = close.ewm(span=50, adjust=False).mean()

    change = close.diff()
    gains = change.clip(lower=0)
    losses = -change.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = losses.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    df.loc[(avg_loss == 0) & (avg_gain > 0), "rsi"] = 100
    df.loc[(avg_gain == 0) & (avg_loss > 0), "rsi"] = 0

    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    df["macd"] = ema_fast - ema_slow
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    previous_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    atr_safe = df["atr"].replace(0, np.nan)
    plus_di = 100 * plus_dm.ewm(
        alpha=1 / 14, adjust=False, min_periods=14
    ).mean() / atr_safe
    minus_di = 100 * minus_dm.ewm(
        alpha=1 / 14, adjust=False, min_periods=14
    ).mean() / atr_safe
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["adx"] = dx.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di

    # Previous-candle rolling levels avoid using the current candle itself.
    df["support"] = low.shift(1).rolling(20, min_periods=10).min()
    df["resistance"] = high.shift(1).rolling(20, min_periods=10).max()
    return df


def analyze(symbol, timeframe, interval):
    df = fetch_candles(symbol, interval)
    if len(df) < MIN_CANDLES:
        raise RuntimeError(
            f"Only {len(df)} completed candles; need at least {MIN_CANDLES}."
        )

    df = add_indicators(df)
    row = df.iloc[-1]

    required = [
        "ema9", "ema21", "ema50", "rsi", "macd",
        "macd_signal", "macd_hist", "atr", "adx",
        "plus_di", "minus_di", "support", "resistance",
    ]
    if any(pd.isna(row[key]) for key in required):
        raise RuntimeError("Indicator values are not ready.")

    price = float(row["close"])
    atr = float(row["atr"])
    if not np.isfinite(price) or not np.isfinite(atr) or price <= 0 or atr <= 0:
        raise RuntimeError("Invalid price or volatility data.")

    bull = 0
    bear = 0
    reasons = []

    if row["ema9"] > row["ema21"] > row["ema50"]:
        bull += 2
        reasons.append("EMA alignment bullish")
    elif row["ema9"] < row["ema21"] < row["ema50"]:
        bear += 2
        reasons.append("EMA alignment bearish")

    if row["macd"] > row["macd_signal"] and row["macd_hist"] > 0:
        bull += 1
        reasons.append("MACD momentum positive")
    elif row["macd"] < row["macd_signal"] and row["macd_hist"] < 0:
        bear += 1
        reasons.append("MACD momentum negative")

    if 50 < row["rsi"] < 70:
        bull += 1
        reasons.append("RSI supports upward momentum")
    elif 30 < row["rsi"] < 50:
        bear += 1
        reasons.append("RSI supports downward momentum")
    elif row["rsi"] >= 70:
        reasons.append("RSI elevated; upside may be stretched")
    elif row["rsi"] <= 30:
        reasons.append("RSI low; downside may be stretched")

    if row["adx"] >= 20:
        if row["plus_di"] > row["minus_di"]:
            bull += 1
            reasons.append("ADX confirms directional strength upward")
        elif row["minus_di"] > row["plus_di"]:
            bear += 1
            reasons.append("ADX confirms directional strength downward")
    else:
        reasons.append("ADX indicates a weak or non-trending market")

    if price > row["support"] and price > row["resistance"]:
        reasons.append("Price is above the recent resistance zone")
    elif price < row["resistance"] and price < row["support"]:
        reasons.append("Price is below the recent support zone")
    else:
        reasons.append("Price is within the recent support/resistance range")

    if bull >= 4 and bull > bear:
        label = "BUY ANALYSIS"
        direction = "BULLISH"
    elif bear >= 4 and bear > bull:
        label = "SELL ANALYSIS"
        direction = "BEARISH"
    else:
        label = "WAIT / MIXED"
        direction = "MIXED"

    max_score = 5
    score = max(bull, bear)
    score_text = f"{score}/{max_score} indicator points (not a probability)"

    candle_time = row["datetime"].strftime("%Y-%m-%d %H:%M UTC")
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "interval": interval,
        "signal": label,
        "direction": direction,
        "price": price,
        "rsi": float(row["rsi"]),
        "adx": float(row["adx"]),
        "atr": atr,
        "support": float(row["support"]),
        "resistance": float(row["resistance"]),
        "bull_score": bull,
        "bear_score": bear,
        "score": score_text,
        "reasons": reasons,
        "candle_time": candle_time,
        "signal_time": row["datetime"].isoformat(),
    }


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return pd.DataFrame(columns=[
            "symbol", "timeframe", "signal_time", "signal",
            "direction", "price", "rsi", "adx", "atr",
            "support", "resistance", "bull_score", "bear_score",
            "recorded_at_utc",
        ])
    try:
        return pd.read_csv(HISTORY_FILE)
    except (pd.errors.EmptyDataError, OSError, ValueError):
        logging.exception("Could not read history file; starting a new local history.")
        return pd.DataFrame()


def save_new_record(result, history):
    key = (
        result["symbol"],
        result["timeframe"],
        result["signal_time"],
    )

    if not history.empty:
        for col in ["symbol", "timeframe", "signal_time"]:
            if col not in history.columns:
                history[col] = ""
        duplicate = (
            (history["symbol"].astype(str) == key[0]) &
            (history["timeframe"].astype(str) == key[1]) &
            (history["signal_time"].astype(str) == key[2])
        ).any()
        if duplicate:
            return history, False

    record = {
        "symbol": result["symbol"],
        "timeframe": result["timeframe"],
        "signal_time": result["signal_time"],
        "signal": result["signal"],
        "direction": result["direction"],
        "price": result["price"],
        "rsi": result["rsi"],
        "adx": result["adx"],
        "atr": result["atr"],
        "support": result["support"],
        "resistance": result["resistance"],
        "bull_score": result["bull_score"],
        "bear_score": result["bear_score"],
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    history = pd.concat([history, pd.DataFrame([record])], ignore_index=True)
    history = history.drop_duplicates(
        subset=["symbol", "timeframe", "signal_time"], keep="first"
    )
    history.to_csv(HISTORY_FILE, index=False)
    return history, True


def format_report(r):
    reasons = "\n".join(f"â¢ {reason}" for reason in r["reasons"])
    return (
        f"<b>Punjab Market Scanner</b>\n\n"
        f"Market: <b>{r['symbol']}</b>\n"
        f"Timeframe: <b>{r['timeframe']}</b>\n"
        f"Analysis: <b>{r['signal']}</b>\n"
        f"Direction: {r['direction']}\n"
        f"Last completed candle close: <code>{r['price']:.6f}</code>\n"
        f"RSI(14): {r['rsi']:.2f}\n"
        f"ADX(14): {r['adx']:.2f}\n"
        f"ATR(14): {r['atr']:.6f}\n"
        f"Recent support: <code>{r['support']:.6f}</code>\n"
        f"Recent resistance: <code>{r['resistance']:.6f}</code>\n"
        f"Indicator score: {r['score']}\n\n"
        f"<b>Why:</b>\n{reasons}\n\n"
        f"Candle time: {r['candle_time']}\n\n"
        f"<i>Educational indicator analysis only. Not a trade instruction, "
        f"not a probability, and not a guarantee. Indicators can be wrong. "
        f"No broker orders are placed.</i>"
    )


def main():
    if not TOKEN or not CHAT_ID or not API_KEY:
        raise RuntimeError(
            "Missing GitHub Secrets: TELEGRAM_TOKEN, CHAT_ID, or TWELVE_DATA_API_KEY."
        )

    history = load_history()
    checked = 0
    new_records = 0
    alerts_sent = 0
    errors = 0

    telegram(
        "<b>Punjab Market Scanner started</b>\n"
        "Checking completed candles and technical indicators."
    )

    for symbol in SYMBOLS:
        for timeframe, (interval, _) in TIMEFRAMES.items():
            try:
                result = analyze(symbol, timeframe, interval)
                checked += 1
                history, is_new = save_new_record(result, history)

                if is_new:
                    new_records += 1
                    # Alert only on a new completed candle's analysis record.
                    if result["signal"] != "WAIT / MIXED":
                        if telegram(format_report(result)):
                            alerts_sent += 1
                logging.info(
                    "%s %s: %s (new=%s)",
                    symbol, timeframe, result["signal"], is_new
                )

            except Exception as exc:
                errors += 1
                logging.exception("Analysis failed for %s %s", symbol, timeframe)
                telegram(
                    f"<b>Scanner data issue</b>\n"
                    f"{symbol} {timeframe}\n{str(exc)[:300]}"
                )

            # Gentle pacing for API rate limits.
            time.sleep(2)

    try:
        history.to_csv(HISTORY_FILE, index=False)
    except OSError:
        logging.exception("Could not save signal history.")
        errors += 1

    telegram(
        "<b>Punjab Scan Complete</b>\n\n"
        f"Markets: {len(SYMBOLS)}\n"
        f"Timeframes per market: {len(TIMEFRAMES)}\n"
        f"Analyses completed: {checked}\n"
        f"New history records: {new_records}\n"
        f"New directional alerts sent: {alerts_sent}\n"
        f"Data/processing issues: {errors}\n\n"
        "<i>Historical records are indicator observations, not verified "
        "profitable trades. No orders were placed.</i>"
    )


if __name__ == "__main__":
    main()
