import os
import time
import logging
from datetime import datetime, timezone, timedelta

import requests
import pandas as pd
import numpy as np

# Punjab Market Scanner
# Educational market-data observations only.
# No trading instructions, broker connection, or order placement.

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "").strip()

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

OUTPUT_SIZE = 100
MIN_CANDLES = 100
HISTORY_FILE = "signal_history.csv"
API_URL = "https://api.twelvedata.com/time_series"

# Twelve Data request protection
API_MIN_INTERVAL = 20.0
LAST_API_REQUEST = 0.0
API_RATE_LIMITED = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

session = requests.Session()


def wait_for_api_slot():
    global LAST_API_REQUEST

    elapsed = time.monotonic() - LAST_API_REQUEST
    remaining = API_MIN_INTERVAL - elapsed

    if remaining > 0:
        logging.info(
            "Twelve Data request spacing: waiting %.1f seconds",
            remaining
        )
        time.sleep(remaining)

    LAST_API_REQUEST = time.monotonic()


def is_rate_limit_message(message):
    message = str(message).lower()

    keywords = [
        "rate limit",
        "too many requests",
        "api credits",
        "credits exhausted",
        "quota",
        "limit exceeded",
        "thank you for using twelve data",
    ]

    return any(keyword in message for keyword in keywords)


def get_retry_after(response):
    value = response.headers.get("Retry-After", "").strip()

    if not value:
        return 60

    try:
        return max(1, int(float(value)))
    except (TypeError, ValueError):
        return 60


def telegram(message):
    if not TOKEN or not CHAT_ID:
        logging.warning("Telegram secrets are missing.")
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
            logging.error(
                "Telegram rejected the message: %s",
                result.get("description", result)
            )
            return False

        return True

    except (requests.RequestException, ValueError) as exc:
        logging.error("Telegram error: %s", exc)
        if getattr(exc, "response", None) is not None:
            logging.error(
                "Telegram response body: %s",
                exc.response.text[:500]
            )
        return False


def discord(message):
    if not DISCORD_TOKEN or not DISCORD_CHANNEL_ID:
        logging.warning("Discord secrets are missing.")
        return False

    url = (
        "https://discord.com/api/v10/channels/"
        f"{DISCORD_CHANNEL_ID}/messages"
    )

    try:
        response = session.post(
            url,
            headers={
                "Authorization": f"Bot {DISCORD_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"content": message},
            timeout=25,
        )
        response.raise_for_status()
        return True

    except requests.RequestException as exc:
        logging.error("Discord error: %s", exc)

        if exc.response is not None:
            logging.error(
                "Discord response status: %s",
                exc.response.status_code
            )
            logging.error(
                "Discord response body: %s",
                exc.response.text
            )

        return False


def fetch_candles(symbol, interval):
    global API_RATE_LIMITED

    if not API_KEY:
        raise RuntimeError("Twelve Data API key is missing.")

    if API_RATE_LIMITED:
        raise RuntimeError(
            "Twelve Data rate limit reached. Scan paused."
        )

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
            wait_for_api_slot()

            response = session.get(
                API_URL,
                params=params,
                timeout=30
            )

            if response.status_code == 429:
                retry_after = get_retry_after(response)
                API_RATE_LIMITED = True

                # A 429 can mean a per-minute limit or exhausted plan credits.
                # Stop this run instead of repeating requests and worsening the limit.
                try:
                    error_detail = response.text[:500]
                except Exception:
                    error_detail = "No response details available."

                logging.error(
                    "Twelve Data HTTP 429 for %s %s. "
                    "Retry-After: %s seconds. API response: %s",
                    symbol,
                    interval,
                    retry_after,
                    error_detail
                )

                raise RuntimeError(
                    "Twelve Data HTTP 429 rate limit/quota reached. "
                    "Remaining scan paused; check API usage and plan limits."
                )

            response.raise_for_status()
            payload = response.json()

            if "values" not in payload:
                message = payload.get(
                    "message",
                    payload.get("code", str(payload))
                )

                if is_rate_limit_message(message):
                    API_RATE_LIMITED = True

                    raise RuntimeError(
                        "Twelve Data quota/rate limit reached: "
                        + str(message)
                    )

                raise RuntimeError(str(message))

            df = pd.DataFrame(payload["values"])

            required = [
                "datetime", "open", "high", "low", "close"
            ]

            if any(c not in df.columns for c in required):
                raise RuntimeError("Missing candle columns.")

            for col in ["open", "high", "low", "close"]:
                df[col] = pd.to_numeric(
                    df[col], errors="coerce"
                )

            df["datetime"] = pd.to_datetime(
                df["datetime"], utc=True, errors="coerce"
            )

            df = (
                df.dropna(subset=required)
                .sort_values("datetime")
                .drop_duplicates(subset=["datetime"])
                .reset_index(drop=True)
            )

            minutes = next(
                v[1] for v in TIMEFRAMES.values()
                if v[0] == interval
            )

            now = datetime.now(timezone.utc)

            df = df[
                df["datetime"] + timedelta(minutes=minutes) <= now
            ]

            return df.reset_index(drop=True)

        except RuntimeError:
            raise

        except (
            requests.RequestException,
            ValueError
        ) as exc:
            last_error = exc

            if isinstance(exc, requests.HTTPError):
                if (
                    exc.response is not None
                    and exc.response.status_code == 429
                ):
                    API_RATE_LIMITED = True
                    raise RuntimeError(
                        "Twelve Data HTTP 429 rate limit reached."
                    )

            if attempt < 2:
                wait_seconds = 5 * (attempt + 1)

                logging.warning(
                    "API request failed for %s %s. "
                    "Retrying in %s seconds: %s",
                    symbol,
                    interval,
                    wait_seconds,
                    exc
                )

                time.sleep(wait_seconds)

    raise RuntimeError(
        f"Could not fetch {symbol}: {last_error}"
    )


def add_indicators(df):
    df = df.copy()

    close = df["close"]
    high = df["high"]
    low = df["low"]

    df["ema9"] = close.ewm(
        span=9, adjust=False
    ).mean()

    df["ema21"] = close.ewm(
        span=21, adjust=False
    ).mean()

    df["ema50"] = close.ewm(
        span=50, adjust=False
    ).mean()

    change = close.diff()

    gains = change.clip(lower=0)
    losses = -change.clip(upper=0)

    avg_gain = gains.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14
    ).mean()

    avg_loss = losses.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    df["rsi"] = 100 - (100 / (1 + rs))

    df.loc[
        (avg_loss == 0) & (avg_gain > 0), "rsi"
    ] = 100

    df.loc[
        (avg_gain == 0) & (avg_loss > 0), "rsi"
    ] = 0

    ema_fast = close.ewm(
        span=12, adjust=False
    ).mean()

    ema_slow = close.ewm(
        span=26, adjust=False
    ).mean()

    df["macd"] = ema_fast - ema_slow

    df["macd_signal"] = df["macd"].ewm(
        span=9, adjust=False
    ).mean()

    df["macd_hist"] = (
        df["macd"] - df["macd_signal"]
    )

    previous_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df["atr"] = tr.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14
    ).mean()

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = up_move.where(
        (up_move > down_move) & (up_move > 0), 0.0
    )

    minus_dm = down_move.where(
        (down_move > up_move) & (down_move > 0), 0.0
    )

    atr_safe = df["atr"].replace(0, np.nan)

    plus_di = 100 * plus_dm.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14
    ).mean() / atr_safe

    minus_di = 100 * minus_dm.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14
    ).mean() / atr_safe

    dx = (
        100 * (plus_di - minus_di).abs()
        / (plus_di + minus_di).replace(0, np.nan)
    )

    df["adx"] = dx.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14
    ).mean()

    df["plus_di"] = plus_di
    df["minus_di"] = minus_di

    df["support"] = (
        low.shift(1).rolling(20, min_periods=10).min()
    )

    df["resistance"] = (
        high.shift(1).rolling(20, min_periods=10).max()
    )

    return df


def analyze(symbol, timeframe, interval):
    df = fetch_candles(symbol, interval)

    if len(df) < MIN_CANDLES:
        raise RuntimeError(
            f"Only {len(df)} completed candles available."
        )

    df = add_indicators(df)
    row = df.iloc[-1]

    required = [
        "ema9", "ema21", "ema50",
        "rsi", "macd", "macd_signal",
        "macd_hist", "atr", "adx",
        "plus_di", "minus_di",
        "support", "resistance",
    ]

    if any(pd.isna(row[key]) for key in required):
        raise RuntimeError("Indicator values are not ready.")

    price = float(row["close"])
    atr = float(row["atr"])
    ema9 = float(row["ema9"])
    ema21 = float(row["ema21"])
    ema50 = float(row["ema50"])
    rsi = float(row["rsi"])
    macd = float(row["macd"])
    macd_signal = float(row["macd_signal"])
    macd_hist = float(row["macd_hist"])
    adx = float(row["adx"])
    plus_di = float(row["plus_di"])
    minus_di = float(row["minus_di"])

    values = [
        price, atr, ema9, ema21, ema50,
        rsi, macd, macd_signal, macd_hist,
        adx, plus_di, minus_di
    ]

    if not all(np.isfinite(v) for v in values):
        raise RuntimeError("Invalid indicator data.")

    if price <= 0 or atr <= 0:
        raise RuntimeError("Invalid market data.")

    bull_score = sum([
        ema9 > ema21 > ema50,
        price > ema21,
        50 < rsi < 68,
        macd > macd_signal,
        macd_hist > 0,
        plus_di > minus_di,
    ])

    bear_score = sum([
        ema9 < ema21 < ema50,
        price < ema21,
        32 < rsi < 50,
        macd < macd_signal,
        macd_hist < 0,
        minus_di > plus_di,
    ])

    signal = "NEUTRAL"
    direction = "NEUTRAL"

    if (
        adx >= 18
        and bull_score >= 4
        and bull_score - bear_score >= 2
    ):
        signal = "BUY"
        direction = "BULLISH"

    elif (
        adx >= 18
        and bear_score >= 4
        and bear_score - bull_score >= 2
    ):
        signal = "SELL"
        direction = "BEARISH"

    candle_time = row["datetime"].strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "signal": signal,
        "direction": direction,
        "bull_score": int(bull_score),
        "bear_score": int(bear_score),
        "price": price,
        "ema9": ema9,
        "ema21": ema21,
        "ema50": ema50,
        "rsi": rsi,
        "macd": macd,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
        "adx": adx,
        "atr": atr,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "support": float(row["support"]),
        "resistance": float(row["resistance"]),
        "candle_time": candle_time,
        "signal_time": row["datetime"].isoformat(),
    }


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return pd.DataFrame()

    try:
        return pd.read_csv(HISTORY_FILE)

    except (
        pd.errors.EmptyDataError,
        OSError,
        ValueError
    ):
        logging.exception("History file could not be read.")
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
            (history["symbol"].astype(str) == key[0])
            & (history["timeframe"].astype(str) == key[1])
            & (history["signal_time"].astype(str) == key[2])
        ).any()

        if duplicate:
            return history, False

    record = {
        "symbol": result["symbol"],
        "timeframe": result["timeframe"],
        "signal_time": result["signal_time"],
        "signal": result["signal"],
        "direction": result["direction"],
        "bull_score": result["bull_score"],
        "bear_score": result["bear_score"],
        "price": result["price"],
        "rsi": result["rsi"],
        "adx": result["adx"],
        "atr": result["atr"],
        "support": result["support"],
        "resistance": result["resistance"],
        "ema9": result["ema9"],
        "ema21": result["ema21"],
        "ema50": result["ema50"],
        "macd": result["macd"],
        "macd_signal": result["macd_signal"],
        "macd_hist": result["macd_hist"],
        "recorded_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    history = pd.concat(
        [history, pd.DataFrame([record])],
        ignore_index=True
    )

    history = history.drop_duplicates(
        subset=["symbol", "timeframe", "signal_time"],
        keep="first"
    )

    history.to_csv(HISTORY_FILE, index=False)

    return history, True


def format_report(r):
    if r["signal"] == "BUY":
        signal_display = "BUY ▲"
    elif r["signal"] == "SELL":
        signal_display = "SELL ▼"
    else:
        signal_display = "NEUTRAL"

    return (
        "<b>Punjab Market Scanner</b>\n\n"
        f"Market: <b>{r['symbol']}</b>\n"
        f"Timeframe: <b>{r['timeframe']}</b>\n\n"
        f"Signal: <b>{signal_display}</b>\n"
        f"Direction: <b>{r['direction']}</b>\n"
        f"Bull Score: {r['bull_score']}/6\n"
        f"Bear Score: {r['bear_score']}/6\n\n"
        f"Last completed candle: <code>{r['price']:.6f}</code>\n"
        f"EMA 9: {r['ema9']:.6f}\n"
        f"EMA 21: {r['ema21']:.6f}\n"
        f"EMA 50: {r['ema50']:.6f}\n"
        f"RSI 14: {r['rsi']:.2f}\n"
        f"MACD: {r['macd']:.6f}\n"
        f"MACD Signal: {r['macd_signal']:.6f}\n"
        f"MACD Histogram: {r['macd_hist']:.6f}\n"
        f"ADX 14: {r['adx']:.2f}\n"
        f"ATR 14: {r['atr']:.6f}\n"
        f"Support reference: <code>{r['support']:.6f}</code>\n"
        f"Resistance reference: <code>{r['resistance']:.6f}</code>\n\n"
        f"Candle time: {r['candle_time']}\n\n"
        "<i>Educational market data only. "
        "Not a trading instruction or prediction. "
        "Indicators can be wrong. No orders are placed.</i>"
    )


def format_discord_report(r):
    return (
        "**Punjab Market Scanner — Educational Update**\n\n"
        f"**Market:** {r['symbol']}\n"
        f"**Timeframe:** {r['timeframe']}\n"
        f"**Last completed candle:** {r['price']:.6f}\n\n"
        f"EMA 9: {r['ema9']:.6f}\n"
        f"EMA 21: {r['ema21']:.6f}\n"
        f"EMA 50: {r['ema50']:.6f}\n"
        f"RSI 14: {r['rsi']:.2f}\n"
        f"MACD: {r['macd']:.6f}\n"
        f"MACD Signal: {r['macd_signal']:.6f}\n"
        f"MACD Histogram: {r['macd_hist']:.6f}\n"
        f"ADX 14: {r['adx']:.2f}\n"
        f"ATR 14: {r['atr']:.6f}\n"
        f"Support reference: {r['support']:.6f}\n"
        f"Resistance reference: {r['resistance']:.6f}\n\n"
        f"Candle time: {r['candle_time']}\n\n"
        "*Educational market data only. Not a trading instruction "
        "or prediction. No orders are placed.*"
    )


def main():
    if not API_KEY:
        raise RuntimeError(
            "Missing GitHub Secret: TWELVE_DATA_API_KEY."
        )

    if not TOKEN or not CHAT_ID:
        raise RuntimeError(
            "Missing Telegram secrets: TELEGRAM_TOKEN or CHAT_ID."
        )

    # Save Twelve Data daily credits: scheduled scans run every 2 hours.
    # Manual workflow_dispatch runs are still allowed at any time.
    event_name = os.getenv("GITHUB_EVENT_NAME", "")
    current_utc_hour = datetime.now(timezone.utc).hour

    if event_name == "schedule" and current_utc_hour % 2 == 1:
        logging.info(
            "Scheduled scan skipped to conserve API credits. "
            "The next scheduled scan is in the next even UTC hour."
        )
        return

    history = load_history()

    checked = 0
    new_records = 0
    telegram_sent = 0
    discord_sent = 0
    errors = 0

    telegram(
        "<b>Punjab Market Scanner Started</b>\n"
        "Educational market-data scan is running."
    )

    for symbol in SYMBOLS:
        if API_RATE_LIMITED:
            break

        for timeframe, (interval, _) in TIMEFRAMES.items():

            if API_RATE_LIMITED:
                break

            try:
                result = analyze(
                    symbol, timeframe, interval
                )

                checked += 1

                history, is_new = save_new_record(
                    result, history
                )

                if is_new:
                    new_records += 1

                    report = format_report(result)

                    if telegram(report):
                        telegram_sent += 1

                    if discord(
                        format_discord_report(result)
                    ):
                        discord_sent += 1

                logging.info(
                    "%s %s: observation completed (new=%s)",
                    symbol, timeframe, is_new
                )

            except Exception as exc:
                errors += 1

                logging.exception(
                    "Analysis failed for %s %s",
                    symbol, timeframe
                )

                if API_RATE_LIMITED:
                    logging.warning(
                        "Stopping remaining market scan "
                        "because Twelve Data rate limit was reached."
                    )
                    break

            time.sleep(2)

    if API_RATE_LIMITED:
        logging.warning(
            "Scan ended early because the Twelve Data API limit "
            "was reached."
        )

    try:
        history.to_csv(HISTORY_FILE, index=False)

    except OSError:
        logging.exception("Could not save history.")
        errors += 1

    summary = (
        "<b>Punjab Scan Complete</b>\n\n"
        f"Markets: {len(SYMBOLS)}\n"
        f"Timeframes per market: {len(TIMEFRAMES)}\n"
        f"Analyses completed: {checked}\n"
        f"New history records: {new_records}\n"
        f"Telegram updates sent: {telegram_sent}\n"
        f"Discord updates sent: {discord_sent}\n"
        f"Data/processing issues: {errors}\n\n"
        "<i>Historical records are observations, "
        "not verified profitable trades. "
        "No orders were placed.</i>"
    )

    telegram(summary)

    discord(
        "**Punjab Scan Complete**\n\n"
        f"Markets: {len(SYMBOLS)}\n"
        f"Timeframes per market: {len(TIMEFRAMES)}\n"
        f"Analyses completed: {checked}\n"
        f"New history records: {new_records}\n"
        f"Telegram updates sent: {telegram_sent}\n"
        f"Discord updates sent: {discord_sent}\n"
        f"Data/processing issues: {errors}\n\n"
        "Educational observations only. No orders placed."
    )


if __name__ == "__main__":
    main()
