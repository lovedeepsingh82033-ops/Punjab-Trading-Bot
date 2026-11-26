import os
import time
import logging
import html
import re
from datetime import datetime, timezone, timedelta

import requests
import pandas as pd
import numpy as np

from market_context import volatility_context
from research_context import market_regime_context
from institutional_research import quantitative_research_context, risk_management_context, algorithmic_system_context, validation_context
from advanced_research import anomaly_research_context, cross_market_correlation_context
from data_quality import data_quality_context
from walk_forward import walk_forward_research_context
from scanner_health import scanner_health_context
from economic_calendar import economic_calendar_context
from research_dashboard import advanced_research_dashboard, format_research_dashboard
from intelligence_hub import build_intelligence_hub, format_intelligence_hub
from quant_intelligence import build_quant_intelligence, format_quant_intelligence
from bot_state import write_bot_snapshot
from snapshot_bridge import upload_snapshot

# Punjab Market Scanner
# Educational market-data observations only.
# No trading instructions, broker connection, or order placement.

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "").strip()
DISCORD_ACCESS_BLOCKED = False

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

# Fetch extra candles because the newest API candle may still be open.
OUTPUT_SIZE = 500
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


def telegram_plain_text(message):
    # Convert the existing HTML-formatted report to readable plain text.
    text = re.sub(
        r'<a\s+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        r'\2 (\1)',
        str(message),
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:b|strong|i|em|u|code|pre)>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<(?:b|strong|i|em|u|code|pre)[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def split_telegram_text(message, limit=3900):
    # Stay below Telegram's 4096-character sendMessage limit.
    chunks = []
    current = ""
    for line in message.splitlines():
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = line if not current else current + "\n" + line
        if len(candidate) > limit:
            if current:
                chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [""]


def telegram(message, reply_markup=None):
    if not TOKEN or not CHAT_ID:
        logging.warning("Telegram secrets are missing.")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    chunks = split_telegram_text(telegram_plain_text(message))

    try:
        for index, chunk in enumerate(chunks):
            payload = {
                "chat_id": CHAT_ID,
                "text": chunk,
                "disable_web_page_preview": True,
            }
            if reply_markup is not None and index == len(chunks) - 1:
                payload["reply_markup"] = reply_markup

            response = session.post(url, json=payload, timeout=25)
            response.raise_for_status()
            result = response.json()

            if not result.get("ok"):
                # Do not log API-provided descriptions or response payloads.
                logging.error("Telegram API rejected the message (ok=false).")
                return False

        return True

    except (requests.RequestException, ValueError) as exc:
        logging.error("Telegram request failed: %s", safe_request_error(exc))
        return False


def discord(message):
    global DISCORD_ACCESS_BLOCKED

    if DISCORD_ACCESS_BLOCKED:
        return False

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

        if response.status_code == 403:
            DISCORD_ACCESS_BLOCKED = True
            logging.error(
                "Discord access denied (403 / Missing Access). "
                "Discord notifications are disabled for the rest "
                "of this run. Check that the bot is in the server, "
                "the channel ID is correct, and the bot has View "
                "Channel and Send Messages permissions."
            )
            return False

        if response.status_code == 429:
            retry_after = 1.0
            try:
                retry_after = max(
                    0.5,
                    float(response.json().get("retry_after", 1.0))
                )
            except (ValueError, TypeError):
                pass

            logging.warning(
                "Discord rate limit reached. Waiting %.2f seconds "
                "before one retry.",
                retry_after
            )
            time.sleep(min(retry_after, 5.0))
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
        logging.error("Discord request failed: %s", safe_request_error(exc))
        return False


def filter_completed_candles(df, interval, as_of):
    """Keep only candles fully closed at one shared UTC scan cutoff."""
    minutes = next(
        (value[1] for value in TIMEFRAMES.values() if value[0] == interval),
        None,
    )
    if minutes is None:
        raise ValueError(f"Unsupported candle interval: {interval}")

    cutoff = pd.Timestamp(as_of)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    else:
        cutoff = cutoff.tz_convert("UTC")

    candle_times = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
    completed = candle_times + pd.Timedelta(minutes=minutes) <= cutoff
    return df.loc[completed].reset_index(drop=True)


def safe_request_error(exc):
    """Describe request failures without exposing URLs or query-string secrets."""
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    description = type(exc).__name__
    if status_code is not None:
        description += f" (HTTP {status_code})"
    return description


def fetch_candles(symbol, interval, as_of=None):
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
                error_detail = "response body redacted"

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

            # Reject malformed OHLC rows before calculating indicators.
            valid_ohlc = (
                (df["open"] > 0)
                & (df["high"] > 0)
                & (df["low"] > 0)
                & (df["close"] > 0)
                & (df["high"] >= df["low"])
                & (df["high"] >= df[["open", "close"]].max(axis=1))
                & (df["low"] <= df[["open", "close"]].min(axis=1))
            )
            rejected_rows = int((~valid_ohlc).sum())
            if rejected_rows:
                logging.warning(
                    "Rejected %s malformed OHLC rows for %s %s.",
                    rejected_rows, symbol, interval
                )
            df = df.loc[valid_ohlc].reset_index(drop=True)

            cutoff = as_of or datetime.now(timezone.utc)
            df = filter_completed_candles(df, interval, cutoff)

            return df

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
                    safe_request_error(exc)
                )

                time.sleep(wait_seconds)

    raise RuntimeError(
        f"Could not fetch {symbol}: {safe_request_error(last_error)}"
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


def historical_backtest(df, horizon_bars=3):
    """
    Chronological out-of-sample holdout test of the fixed indicator rules.
    The first 70% is reserved as history; only the final 30% is scored.
    Qualifying outcome windows are non-overlapping. Signals are evaluated at
    candle close, entered at the next candle open, and measured to the
    horizon candle close. This measures directional movement, not net
    profit, costs, or future certainty.
    """
    if not isinstance(horizon_bars, int) or isinstance(horizon_bars, bool) or horizon_bars < 1:
        raise ValueError("horizon_bars must be a positive integer")

    observations = []
    required = ["ema9", "ema21", "ema50", "rsi", "macd", "macd_signal",
                "macd_hist", "adx", "plus_di", "minus_di"]
    test_start = max(50, int(len(df) * 0.70))
    next_eligible_index = test_start
    for i in range(test_start, len(df) - horizon_bars):
        # Keep scored outcome windows disjoint: after selecting a signal,
        # skip the next horizon_bars possible entry candles.
        if i < next_eligible_index:
            continue
        row = df.iloc[i]
        if any(pd.isna(row[key]) for key in required):
            continue
        bull = sum([row["ema9"] > row["ema21"] > row["ema50"],
                    row["close"] > row["ema21"], 50 < row["rsi"] < 68,
                    row["macd"] > row["macd_signal"], row["macd_hist"] > 0,
                    row["plus_di"] > row["minus_di"]])
        bear = sum([row["ema9"] < row["ema21"] < row["ema50"],
                    row["close"] < row["ema21"], 32 < row["rsi"] < 50,
                    row["macd"] < row["macd_signal"], row["macd_hist"] < 0,
                    row["minus_di"] > row["plus_di"]])
        direction = None
        if row["adx"] >= 18 and bull >= 4 and bull - bear >= 2:
            direction = "BULLISH"
        elif row["adx"] >= 18 and bear >= 4 and bear - bull >= 2:
            direction = "BEARISH"
        if direction is None:
            continue
        # The signal is known only after candle i closes. Model entry at the
        # next candle open, then measure through the horizon candle close.
        entry, future = (
            float(df.iloc[i + 1]["open"]),
            float(df.iloc[i + horizon_bars]["close"]),
        )
        if not np.isfinite(entry) or entry <= 0 or not np.isfinite(future):
            continue
        move = (future - entry) / entry * 100
        observations.append(move if direction == "BULLISH" else -move)
        next_eligible_index = i + horizon_bars

    if not observations:
        return {
            "samples": 0, "hit_rate": None, "avg_move_pct": None,
            "median_move_pct": None,
            "overlap_policy": "NON_OVERLAPPING_HORIZON",
        "entry_policy": "NEXT_CANDLE_OPEN_TO_HORIZON_CLOSE",
        }
    values = np.asarray(observations, dtype=float)
    return {
        "samples": len(values),
        "hit_rate": float((values > 0).mean() * 100),
        "avg_move_pct": float(values.mean()),
        "median_move_pct": float(np.median(values)),
        "overlap_policy": "NON_OVERLAPPING_HORIZON",
            "entry_policy": "NEXT_CANDLE_OPEN_TO_HORIZON_CLOSE",
    }


def analyze(symbol, timeframe, interval, as_of=None):
    df = fetch_candles(symbol, interval, as_of=as_of)

    if len(df) < MIN_CANDLES:
        raise RuntimeError(
            f"Only {len(df)} completed candles available."
        )

    df = add_indicators(df)
    quality = data_quality_context(
        df, timeframe_minutes=TIMEFRAMES[timeframe][1],
        as_of=as_of or datetime.now(timezone.utc),
    )
    volatility = volatility_context(df)
    regime = market_regime_context(df)
    quantitative = quantitative_research_context(df)
    risk_context = risk_management_context(df)
    algorithmic = algorithmic_system_context(df)
    backtest = historical_backtest(df, horizon_bars=3)
    validation = validation_context(backtest)
    walk_forward = walk_forward_research_context(df, folds=4, minimum_samples=10)
    anomaly = anomaly_research_context(df)
    row = df.iloc[-1]
    previous_row = df.iloc[-2]

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

    # Do not emit directional labels when the underlying data checks fail.
    integrity_ok = (
        algorithmic.get("status") == "PASS"
        and quality.get("status") != "FAIL"
    )

    if integrity_ok and (
        adx >= 20
        and bull_score >= 4
        and bull_score - bear_score >= 2
    ):
        signal = "BULLISH"
        direction = "BULLISH"

    elif integrity_ok and (
        adx >= 20
        and bear_score >= 4
        and bear_score - bull_score >= 2
    ):
        signal = "BEARISH"
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
        "rsi_momentum": rsi_momentum_status(rsi, float(previous_row["rsi"])),
        "macd": macd,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
        "macd_momentum": macd_momentum_status(macd_hist, float(previous_row["macd_hist"])),
        "adx": adx,
        "atr": atr,
        "volatility": volatility,
        "data_quality": quality,
        "market_regime": regime,
        "quantitative_research": quantitative,
        "risk_context": risk_context,
        "algorithmic_system": algorithmic,
        "validation": validation,
        "walk_forward": walk_forward,
        "anomaly_research": anomaly,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "support": float(row["support"]),
        "resistance": float(row["resistance"]),
        "candle_time": candle_time,
        "signal_time": row["datetime"].isoformat(),
        "scan_cutoff": (
            pd.Timestamp(as_of or datetime.now(timezone.utc))
            .tz_convert("UTC").isoformat()
            if pd.Timestamp(as_of or datetime.now(timezone.utc)).tzinfo
            else pd.Timestamp(as_of or datetime.now(timezone.utc))
            .tz_localize("UTC").isoformat()
        ),
        "backtest": backtest,
        # In-memory candle series for exact-horizon history evaluation.
        # save_new_record writes explicit fields only, so this is not persisted.
        "_candles": df[["datetime", "close"]].copy(),
    }


def atomic_save_history(history, path=HISTORY_FILE):
    """Persist history atomically so interrupted writes do not truncate it."""
    temporary_path = f"{path}.tmp"
    try:
        history.to_csv(temporary_path, index=False)
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            try:
                os.remove(temporary_path)
            except OSError:
                logging.warning("Could not remove temporary history file: %s", temporary_path)


def save_history_or_raise(history):
    """Persist history or fail the run so stale history cannot be uploaded."""
    try:
        atomic_save_history(history)
    except Exception as exc:
        logging.exception("History persistence failed; aborting before artifact upload.")
        raise RuntimeError(
            "Signal history could not be saved; refusing to continue with stale data."
        ) from exc


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return pd.DataFrame()

    try:
        return pd.read_csv(HISTORY_FILE)

    except (
        pd.errors.EmptyDataError,
        OSError,
        ValueError
    ) as exc:
        # Fail closed: never continue with an empty history and overwrite
        # the existing file after a read/parse failure.
        logging.exception("History file could not be read; refusing to overwrite it.")
        raise RuntimeError(
            "Signal history is unreadable. Preserve the file and repair it before scanning."
        ) from exc



def evaluate_past_signals(current, history, horizon_bars=3):
    """Evaluate observations at exactly the Nth subsequent completed candle."""
    if history.empty:
        return history, 0, 0

    required = ["symbol", "timeframe", "signal", "signal_time", "price"]
    if any(col not in history.columns for col in required):
        return history, 0, 0

    for col, default in [
        ("outcome_status", "PENDING"),
        ("outcome_pct", np.nan),
        ("evaluated_at", ""),
        ("outcome_method", ""),
    ]:
        if col not in history.columns:
            history[col] = default

    direction_values = history.get("direction", history["signal"])
    directions = direction_values.fillna("").astype(str).str.upper()
    fallback = history["signal"].fillna("").astype(str).str.upper()
    directions = directions.where(directions != "", fallback)
    directions = directions.replace({
        "BUY": "BULLISH",
        "BUY ANALYSIS": "BULLISH",
        "SELL": "BEARISH",
        "SELL ANALYSIS": "BEARISH",
    })

    mask = (
        (history["symbol"].astype(str) == current["symbol"])
        & (history["timeframe"].astype(str) == current["timeframe"])
        & directions.isin(["BULLISH", "BEARISH"])
        & (history["outcome_status"].fillna("PENDING").astype(str).str.upper() == "PENDING")
    )

    candles = current.get("_candles")
    if candles is None or candles.empty:
        return history, 0, 0

    candle_times = pd.to_datetime(candles["datetime"], utc=True, errors="coerce")
    candle_closes = pd.to_numeric(candles["close"], errors="coerce")
    positions = {
        timestamp: position
        for position, timestamp in enumerate(candle_times)
        if not pd.isna(timestamp)
    }

    updated = 0
    for idx in history.index[mask]:
        signal_time = pd.to_datetime(
            history.at[idx, "signal_time"], utc=True, errors="coerce"
        )
        if pd.isna(signal_time):
            continue

        signal_position = positions.get(signal_time)
        if signal_position is None:
            continue

        target_position = signal_position + horizon_bars
        if target_position >= len(candles):
            continue

        entry = float(history.at[idx, "price"])
        exit_price = float(candle_closes.iloc[target_position])
        if not np.isfinite(entry) or entry <= 0 or not np.isfinite(exit_price):
            continue

        direction = directions.at[idx]
        raw_change = (exit_price - entry) / entry * 100
        directional_change = raw_change if direction == "BULLISH" else -raw_change

        if directional_change > 0:
            status = "CORRECT"
        elif directional_change < 0:
            status = "INCORRECT"
        else:
            status = "FLAT"

        target_time = candle_times.iloc[target_position]
        history.at[idx, "outcome_status"] = status
        history.at[idx, "outcome_pct"] = round(directional_change, 6)
        history.at[idx, "evaluated_at"] = target_time.isoformat()
        history.at[idx, "outcome_method"] = "EXACT_3_CANDLE"
        updated += 1

    completed = history[
        (history["outcome_method"].astype(str) == "EXACT_3_CANDLE")
        & history["outcome_status"].astype(str).str.upper().isin(
            ["CORRECT", "INCORRECT", "FLAT"]
        )
    ]
    correct = int((completed["outcome_status"].astype(str).str.upper() == "CORRECT").sum())
    return history, updated, correct


def canonical_utc_timestamp(value):
    """Normalize equivalent timestamp strings to one UTC ISO representation."""
    timestamp = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(timestamp):
        return None
    return timestamp.isoformat()


def save_new_record(result, history):
    key = (
        result["symbol"],
        result["timeframe"],
        canonical_utc_timestamp(result["signal_time"]),
    )

    if not history.empty:
        for col in ["symbol", "timeframe", "signal_time"]:
            if col not in history.columns:
                history[col] = ""

        history_times = history["signal_time"].map(canonical_utc_timestamp)
        duplicate = (
            (history["symbol"].astype(str) == key[0])
            & (history["timeframe"].astype(str) == key[1])
            & (history_times == key[2])
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
        "mtf_cohort": "UNASSESSED" if result["direction"] in ("BULLISH", "BEARISH") else "NOT_DIRECTIONAL",
        "mtf_votes": 0,
        "mtf_scanned": 0,
        "mtf_h1_aligned": False,
        "mtf_m30_aligned": False,
        "mtf_reason": "Awaiting complete market scan" if result["direction"] in ("BULLISH", "BEARISH") else "No directional signal",
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

    atomic_save_history(history)

    return history, True



def mtf_decision(result, same_market):
    """Strict MTF research gate; it is not a profitability guarantee."""
    direction = result["direction"]
    expected_symbol = result["symbol"]
    mixed_symbols = sorted({
        str(item.get("symbol", ""))
        for item in same_market
        if item.get("symbol") != expected_symbol
    })
    # Never let another instrument's timeframe vote in this market's cohort.
    same_market = [
        item for item in same_market
        if item.get("symbol") == expected_symbol
    ]
    timeframe_names = [item["timeframe"] for item in same_market]
    by_timeframe = {item["timeframe"]: item for item in same_market}
    duplicate_timeframes = sorted(
        name for name in set(timeframe_names)
        if timeframe_names.count(name) > 1
    )
    scanned = len(by_timeframe)
    votes = sum(item["direction"] == direction for item in by_timeframe.values())
    h1 = by_timeframe.get("H1")
    m30 = by_timeframe.get("M30")
    h1_aligned = h1 is not None and h1["direction"] == direction
    m30_aligned = m30 is not None and m30["direction"] == direction
    def has_strong_adx(item):
        try:
            value = float(item.get("adx"))
        except (TypeError, ValueError, OverflowError):
            return False
        return bool(np.isfinite(value) and value >= 20)

    # Missing, malformed, or non-finite ADX data must fail closed rather
    # than crash the entire scan or accidentally qualify an MTF cohort.
    anchors_strong = (
        h1 is not None and m30 is not None
        and has_strong_adx(h1) and has_strong_adx(m30)
    )

    # Every production result carries its candle-open timestamp and the
    # common scan cutoff. A candle is fresh only while its close is no more
    # than one full timeframe behind that cutoff.
    freshness_errors = []
    for item in by_timeframe.values():
        timeframe = item.get("timeframe")
        minutes = TIMEFRAMES.get(timeframe, (None, None))[1]
        try:
            candle_open = pd.to_datetime(item.get("signal_time"), utc=True, errors="coerce")
            cutoff = pd.to_datetime(item.get("scan_cutoff"), utc=True, errors="coerce")
            if minutes is None or pd.isna(candle_open) or pd.isna(cutoff):
                raise ValueError("missing timing metadata")
            candle_close = candle_open + pd.Timedelta(minutes=minutes)
            age = cutoff - candle_close
            if age < pd.Timedelta(0) or age >= pd.Timedelta(minutes=minutes):
                freshness_errors.append(timeframe)
        except (TypeError, ValueError, OverflowError):
            freshness_errors.append(timeframe)
    stale_timeframes = sorted(set(freshness_errors))
    expected_timeframes = set(TIMEFRAMES)
    complete = (
        set(by_timeframe) == expected_timeframes
        and len(timeframe_names) == len(expected_timeframes)
        and not duplicate_timeframes
        and not mixed_symbols
        and not stale_timeframes
    )
    passed = complete and votes >= 3 and h1_aligned and m30_aligned and anchors_strong

    if mixed_symbols:
        reason, cohort = "MIXED_SYMBOLS", "INCOMPLETE"
    elif duplicate_timeframes:
        reason, cohort = "DUPLICATE_TIMEFRAMES", "INCOMPLETE"
    elif stale_timeframes:
        reason, cohort = "STALE_OR_MISSING_CANDLE_TIMING", "INCOMPLETE"
    elif not complete:
        reason, cohort = "INCOMPLETE_TIMEFRAMES", "INCOMPLETE"
    elif not h1_aligned:
        reason, cohort = "H1_NOT_ALIGNED", "BLOCKED"
    elif not m30_aligned:
        reason, cohort = "M30_NOT_ALIGNED", "BLOCKED"
    elif votes < 3:
        reason, cohort = "LESS_THAN_3_OF_4_AGREE", "BLOCKED"
    elif not anchors_strong:
        reason, cohort = "H1_OR_M30_ADX_BELOW_20", "BLOCKED"
    else:
        reason, cohort = "CONFIRMED_3_OF_4_WITH_STRONG_H1_M30", "PASSED"

    return {
        "passed": passed, "cohort": cohort, "votes": votes,
        "scanned": scanned, "h1_aligned": h1_aligned,
        "m30_aligned": m30_aligned, "reason": reason,
        "missing_timeframes": sorted(expected_timeframes - set(by_timeframe)),
        "duplicate_timeframes": duplicate_timeframes,
        "mixed_symbols": mixed_symbols,
        "stale_timeframes": stale_timeframes,
    }


def mtf_diagnostic_summary(scan_results):
    """Count MTF candidates and decisions without mixing legacy records."""
    candidates = [x for x in scan_results if x.get("direction") in ("BULLISH", "BEARISH")]
    counts = {"candidates": len(candidates), "passed": 0, "blocked": 0,
              "incomplete": 0, "reasons": {}}
    for result in candidates:
        same_market = [x for x in scan_results if x["symbol"] == result["symbol"]]
        decision = mtf_decision(result, same_market)
        counts[decision["cohort"].lower()] += 1
        reason = decision["reason"]
        counts["reasons"][reason] = counts["reasons"].get(reason, 0) + 1
    return counts


def label_mtf_cohorts(scan_results, history):
    """Freeze each observation's first MTF decision; never relabel old cohorts."""
    if history.empty:
        return history
    defaults = {
        "mtf_cohort": "LEGACY_UNKNOWN", "mtf_votes": 0,
        "mtf_scanned": 0, "mtf_h1_aligned": False,
        "mtf_m30_aligned": False,
        "mtf_reason": "Legacy record; MTF cohort not measured",
    }
    for column, default in defaults.items():
        if column not in history.columns:
            history[column] = default
        else:
            history[column] = history[column].fillna(default)

    for result in scan_results:
        if result["direction"] not in ("BULLISH", "BEARISH"):
            continue
        same_market = [x for x in scan_results if x["symbol"] == result["symbol"]]
        decision = mtf_decision(result, same_market)
        history_times = history["signal_time"].map(canonical_utc_timestamp)
        result_time = canonical_utc_timestamp(result["signal_time"])
        mask = (
            (history["symbol"].astype(str) == str(result["symbol"]))
            & (history["timeframe"].astype(str) == str(result["timeframe"]))
            & (history_times == result_time)
            & (history["mtf_cohort"].astype(str) == "UNASSESSED")
        )
        values = {
            "mtf_cohort": decision["cohort"],
            "mtf_votes": decision["votes"],
            "mtf_scanned": decision["scanned"],
            "mtf_h1_aligned": decision["h1_aligned"],
            "mtf_m30_aligned": decision["m30_aligned"],
            "mtf_reason": decision["reason"],
        }
        for column, value in values.items():
            history.loc[mask, column] = value
    return history


def exact_verified_history(history):
    """Return exact-horizon outcomes, excluding every row in duplicate signal keys."""
    if history.empty:
        return history.copy()
    required = {"symbol", "timeframe", "signal_time", "outcome_method", "outcome_status"}
    if not required.issubset(history.columns):
        return history.iloc[0:0].copy()
    statuses = history["outcome_status"].fillna("").astype(str).str.upper()
    valid = (
        history["outcome_method"].fillna("").astype(str).eq("EXACT_3_CANDLE")
        & statuses.isin(["CORRECT", "INCORRECT", "FLAT"])
    )
    exact = history[valid].copy()
    keys = ["symbol", "timeframe", "signal_time"]
    normalized_keys = exact[keys].copy()
    normalized_keys["signal_time"] = normalized_keys["signal_time"].map(
        canonical_utc_timestamp
    )
    missing_key = (
        normalized_keys.isna().any(axis=1)
        | normalized_keys["symbol"].astype(str).str.strip().eq("")
        | normalized_keys["timeframe"].astype(str).str.strip().eq("")
    )
    duplicate_key = normalized_keys.duplicated(keep=False)
    return exact[~(missing_key | duplicate_key)].copy()


def mtf_cohort_evidence_summary(history, minimum_directional_samples=30):
    """Report cohort hit rates with Wilson intervals and an evidence-size warning."""
    valid = exact_verified_history(history)
    lines = []
    stats = {}

    for cohort in ("PASSED", "BLOCKED"):
        group = valid[valid.get("mtf_cohort", pd.Series(index=valid.index, dtype=str))
                      .fillna("").astype(str) == cohort]
        statuses = group["outcome_status"].fillna("").astype(str).str.upper()
        correct = int((statuses == "CORRECT").sum())
        incorrect = int((statuses == "INCORRECT").sum())
        flat = int((statuses == "FLAT").sum())
        decisive = correct + incorrect
        rate = correct / decisive if decisive else None

        # Wilson score interval avoids misleading normal intervals at small n.
        if decisive:
            z = 1.959963984540054
            denominator = 1 + z * z / decisive
            center = (rate + z * z / (2 * decisive)) / denominator
            margin = (
                z * np.sqrt(
                    rate * (1 - rate) / decisive
                    + z * z / (4 * decisive * decisive)
                ) / denominator
            )
            low = max(0.0, center - margin) * 100
            high = min(1.0, center + margin) * 100
            interval = f"{low:.1f}%–{high:.1f}%"
            rate_text = f"{rate * 100:.1f}%"
        else:
            interval = "not available"
            rate_text = "not available"

        evidence = (
            "minimum sample reached"
            if decisive >= minimum_directional_samples
            else f"insufficient evidence (<{minimum_directional_samples} directional samples)"
        )
        lines.append(
            f"{cohort}: {len(group)} matured; {correct} correct / "
            f"{incorrect} incorrect / {flat} flat; directional hit rate "
            f"{rate_text}; 95% Wilson CI {interval}; {evidence}"
        )
        stats[cohort] = {
            "matured": len(group), "correct": correct,
            "incorrect": incorrect, "flat": flat,
            "directional_samples": decisive, "hit_rate": rate,
            "ci95_low": low if decisive else None,
            "ci95_high": high if decisive else None,
        }

    enough = all(
        stats[cohort]["directional_samples"] >= minimum_directional_samples
        for cohort in ("PASSED", "BLOCKED")
    )
    if enough:
        comparison = (
            "PASSED vs BLOCKED: both groups meet the minimum sample size; "
            "compare rates and confidence intervals cautiously. This is "
            "observational evidence, not proof that the filter causes better results."
        )
    else:
        comparison = (
            "PASSED vs BLOCKED comparison: not ready; each group needs at least "
            f"{minimum_directional_samples} matured directional observations."
        )
    lines.append(comparison)
    return lines, stats


def mtf_accuracy_summary(history):
    """Report matured exact-three-candle results for passed/blocked cohorts."""
    empty = {
        "PASSED": "PASSED: no matured observations yet",
        "BLOCKED": "BLOCKED: no matured observations yet",
    }
    if history.empty or "mtf_cohort" not in history.columns:
        return empty
    valid = exact_verified_history(history)
    lines = {}
    for cohort in ("PASSED", "BLOCKED"):
        group = valid[valid["mtf_cohort"].astype(str) == cohort]
        statuses = group["outcome_status"].fillna("").astype(str).str.upper()
        correct = int((statuses == "CORRECT").sum())
        incorrect = int((statuses == "INCORRECT").sum())
        flat = int((statuses == "FLAT").sum())
        decisive = correct + incorrect
        rate = f"{correct / decisive * 100:.1f}%" if decisive else "not available"
        lines[cohort] = (
            f"{cohort}: {len(group)} matured; {correct} correct / "
            f"{incorrect} incorrect / {flat} flat; hit rate {rate}"
        )
    return lines


def accuracy_summary(history):
    """Summarize unique, verified exact-horizon observations; flats are not wins."""
    if history.empty or "outcome_status" not in history.columns:
        return {"completed": 0, "correct": 0, "incorrect": 0,
                "flat": 0, "win_rate": None}
    history = exact_verified_history(history)
    statuses = history["outcome_status"].fillna("").astype(str).str.upper()
    correct = int((statuses == "CORRECT").sum())
    incorrect = int((statuses == "INCORRECT").sum())
    flat = int((statuses == "FLAT").sum())
    decisive = correct + incorrect
    return {
        "completed": decisive + flat,
        "correct": correct,
        "incorrect": incorrect,
        "flat": flat,
        "win_rate": (correct / decisive * 100) if decisive else None,
    }

def accuracy_breakdown(history, group_col):
    """Return accuracy lines grouped by market or timeframe."""
    if (
        history.empty
        or group_col not in history.columns
        or "outcome_status" not in history.columns
    ):
        return []

    if "outcome_method" not in history.columns:
        return []

    completed = exact_verified_history(history)
    if completed.empty:
        return []

    lines = []
    for name, group in completed.groupby(group_col):
        statuses = group["outcome_status"].fillna("").astype(str).str.upper()
        correct = int((statuses == "CORRECT").sum())
        incorrect = int((statuses == "INCORRECT").sum())
        flat = int((statuses == "FLAT").sum())
        decisive = correct + incorrect
        if decisive:
            rate = correct / decisive * 100
            lines.append(
                f"{name}: {rate:.1f}% ({correct} correct / "
                f"{incorrect} incorrect; {flat} flat)"
            )
        else:
            lines.append(f"{name}: no decisive results yet ({flat} flat)")
    return lines



def accuracy_integrity_summary(history):
    """Audit exact-horizon counts, duplicate keys, and grouped status totals."""
    result = {
        "status": "OK", "warnings": [], "completed": 0,
        "correct": 0, "incorrect": 0, "flat": 0,
        "market_rows": 0, "timeframe_rows": 0,
        "duplicate_keys": 0, "duplicate_rows_quarantined": 0,
        "missing_keys": 0, "invalid_exact_status": 0,
    }
    if history.empty:
        return result
    required = {"symbol", "timeframe", "signal_time", "outcome_method", "outcome_status"}
    if not required.issubset(history.columns):
        result["status"] = "WARNING"
        result["warnings"].append("Required history columns are missing")
        return result

    exact_mask = history["outcome_method"].fillna("").astype(str).eq("EXACT_3_CANDLE")
    statuses = history["outcome_status"].fillna("").astype(str).str.upper()
    valid_status = statuses.isin(["CORRECT", "INCORRECT", "FLAT"])
    exact_all = history[exact_mask & valid_status].copy()
    result["invalid_exact_status"] = int((exact_mask & ~valid_status).sum())

    keys = ["symbol", "timeframe", "signal_time"]
    normalized_keys = exact_all[keys].copy()
    normalized_keys["signal_time"] = normalized_keys["signal_time"].map(
        canonical_utc_timestamp
    )
    missing_key_mask = (
        normalized_keys.isna().any(axis=1)
        | normalized_keys["symbol"].astype(str).str.strip().eq("")
        | normalized_keys["timeframe"].astype(str).str.strip().eq("")
    )
    duplicate_mask = normalized_keys.duplicated(keep=False)
    result["missing_keys"] = int(missing_key_mask.sum())
    result["duplicate_rows_quarantined"] = int(duplicate_mask.sum())
    result["duplicate_keys"] = int(normalized_keys.loc[duplicate_mask].drop_duplicates().shape[0])

    exact = exact_verified_history(history)
    exact_statuses = exact["outcome_status"].fillna("").astype(str).str.upper()
    result["correct"] = int((exact_statuses == "CORRECT").sum())
    result["incorrect"] = int((exact_statuses == "INCORRECT").sum())
    result["flat"] = int((exact_statuses == "FLAT").sum())
    result["completed"] = len(exact)
    result["market_rows"] = int(exact.groupby("symbol", dropna=False).size().sum())
    result["timeframe_rows"] = int(exact.groupby("timeframe", dropna=False).size().sum())

    expected = {"CORRECT": result["correct"], "INCORRECT": result["incorrect"], "FLAT": result["flat"]}
    for group_col, label in (("symbol", "market"), ("timeframe", "timeframe")):
        grouped = exact.assign(
            _status=exact["outcome_status"].fillna("").astype(str).str.upper()
        ).groupby([group_col, "_status"], dropna=False).size()
        actual = {status: int(grouped.xs(status, level="_status").sum())
                  if status in grouped.index.get_level_values("_status") else 0
                  for status in expected}
        if actual != expected:
            result["warnings"].append(f"{label.title()} correct/incorrect/flat totals do not reconcile")

    if result["invalid_exact_status"]:
        result["warnings"].append(f"{result['invalid_exact_status']} exact-horizon rows have invalid or pending outcome statuses")
    if result["missing_keys"]:
        result["warnings"].append(f"{result['missing_keys']} exact-horizon rows have missing signal keys")
    if result["duplicate_keys"]:
        result["warnings"].append(
            f"{result['duplicate_keys']} duplicate signal keys found; "
            f"{result['duplicate_rows_quarantined']} rows excluded from accuracy"
        )
    if result["warnings"]:
        result["status"] = "WARNING"
    return result


def rsi_momentum_status(current, previous):
    """Describe RSI movement using the latest two completed candles."""
    current, previous = float(current), float(previous)
    if not np.isfinite(current) or not np.isfinite(previous):
        raise ValueError("RSI values must be finite")
    if current >= 70:
        if current < previous:
            return "OVERBOUGHT — RSI easing"
        if current > previous:
            return "OVERBOUGHT — RSI still rising"
        return "OVERBOUGHT — RSI unchanged"
    if previous >= 70:
        return "Cooling below overbought"
    if current <= 30:
        if current > previous:
            return "OVERSOLD — RSI recovering"
        if current < previous:
            return "OVERSOLD — RSI still falling"
        return "OVERSOLD — RSI unchanged"
    if previous <= 30:
        return "Recovering above oversold"
    if current > previous:
        return "RSI rising"
    if current < previous:
        return "RSI falling"
    return "RSI unchanged"


def macd_momentum_status(current, previous):
    """Describe MACD histogram momentum change across completed candles."""
    current, previous = float(current), float(previous)
    if not np.isfinite(current) or not np.isfinite(previous):
        raise ValueError("MACD histogram values must be finite")
    if current > 0:
        if current > previous:
            return "Bullish momentum strengthening"
        if current < previous:
            return "Bullish momentum weakening"
        return "Bullish momentum steady"
    if current < 0:
        if current < previous:
            return "Bearish momentum strengthening"
        if current > previous:
            return "Bearish momentum weakening"
        return "Bearish momentum steady"
    if current > previous:
        return "Bullish momentum emerging"
    if current < previous:
        return "Bearish momentum emerging"
    return "MACD momentum neutral"


def rsi_warning(rsi):
    """Describe extreme RSI conditions without changing the directional signal."""
    value = float(rsi)
    if not np.isfinite(value):
        raise ValueError("RSI must be finite")
    if value <= 30:
        return "OVERSOLD — downside momentum is stretched; a rebound or continued weakness is possible"
    if value >= 70:
        return "OVERBOUGHT — upside momentum is stretched; a pullback or continued strength is possible"
    return "No extreme RSI warning"


def format_report(r, mtf_text="Not enough matching timeframe data", confidence_label="MTF CONFIRMED DEMO"):
    if r["signal"] == "BULLISH":
        signal_display = "BUY — DEMO 🟢"
        signal_icon = "🟢"
    elif r["signal"] == "BEARISH":
        signal_display = "SELL — DEMO 🔴"
        signal_icon = "🔴"
    else:
        return None

    return (
        "━━━━━━━━━━━━━━━━━━\n"
        "🐅 <b>PUNJAB AI ROBOT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🧪 <b>VIRTUAL DEMO OBSERVATION ONLY</b>\n"
        f"📊 <b>{r['symbol']}</b>\n"
        f"⏱ <b>{r['timeframe']}</b> timeframe\n"
        f"{signal_icon} <b>{signal_display}</b>\n"
        f"🧭 <b>Status: {confidence_label}</b>\n\n"
        "📈 <b>ANALYSIS DETAILS</b>\n"
        f"🟢 Bull score: <b>{r['bull_score']}/6</b>\n"
        f"🔴 Bear score: <b>{r['bear_score']}/6</b>\n"
        f"💰 Last completed price: <code>{r['price']:.6f}</code>\n"
        f"📉 RSI (14): <b>{r['rsi']:.2f}</b>\n"
        f"⚠️ RSI status: <b>{rsi_warning(r['rsi'])}</b>\n"
        f"↕️ RSI momentum: <b>{r['rsi_momentum']}</b>\n"
        f"📊 ADX (14): <b>{r['adx']:.2f}</b>\n"
        f"🧭 Market regime: <b>{r['market_regime']['label']}</b> — {r['market_regime']['detail']}\n"
        f"📐 Quant research: {r['quantitative_research']['sample_count']} returns; volatility {r['quantitative_research']['return_volatility_pct']:.3f}% (descriptive)\n"
        f"🛡️ Risk research: historical max drawdown {r['risk_context']['max_drawdown_pct']:.2f}%; 95th percentile absolute move {r['risk_context']['return_p95_abs_pct']:.3f}%\n"
        f"⚙️ Algorithmic system: {r['algorithmic_system']['status']} — {r['algorithmic_system']['detail']}\n"
        + (f"   Failed checks: {', '.join(r['algorithmic_system'].get('failed_checks', []))}\n" if r['algorithmic_system'].get('failed_checks') else "")
        + f"🧪 Validation: {r['validation']['status']} — {r['validation']['detail']}\n"
        f"🧭 Walk-forward research: {r['walk_forward']['status']} — {r['walk_forward']['detail']}\n"
        f"🌡️ Volatility: <b>{r['volatility']['regime']}</b> — ATR {r['volatility']['atr_pct']:.3f}% of price; {r['volatility']['percentile']:.0f}th percentile (100 candles)\n"
        f"〽️ MACD histogram: <code>{r['macd_hist']:.6f}</code>\n"
        f"📈 MACD momentum: <b>{r['macd_momentum']}</b>\n"
        f"🧭 Timeframe agreement: <b>{mtf_text}</b>\n\n"
        f"🕒 Candle: {r['candle_time']}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        '<a href="https://github.com/lovedeepsingh82033-ops/Punjab-Trading-Bot">📂 View Punjab Scanner on GitHub</a>\n\n'
        "<i>Educational market observation only. "
        "Not a trading instruction or prediction. "
        "Indicators can be wrong. No orders are placed.</i>"
    )

def format_watch_research_report(r, reason):
    """Format a non-actionable directional research watch, never a trade signal."""
    if r["bull_score"] > r["bear_score"]:
        bias = "BULLISH WATCH — RESEARCH ONLY 🟢"
    elif r["bear_score"] > r["bull_score"]:
        bias = "BEARISH WATCH — RESEARCH ONLY 🔴"
    else:
        bias = "MIXED MOMENTUM — RESEARCH ONLY 🟡"

    return (
        "━━━━━━━━━━━━━━━━━━\n"
        "🐅 <b>PUNJAB AI ROBOT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🧪 <b>EDUCATIONAL RESEARCH WATCH — NOT A BUY/SELL SIGNAL</b>\n"
        f"📊 <b>{r['symbol']}</b> | ⏱ <b>{r['timeframe']}</b>\n"
        f"🔎 <b>{bias}</b>\n"
        f"🧭 Reason: {html.escape(str(reason))}\n\n"
        f"Bull score: <b>{r['bull_score']}/6</b> | Bear score: <b>{r['bear_score']}/6</b>\n"
        f"ADX (14): <b>{r['adx']:.2f}</b> | RSI (14): <b>{r['rsi']:.2f}</b>\n"
        f"Last completed price: <code>{r['price']:.6f}</code>\n"
        f"Market regime: <b>{html.escape(str(r['market_regime']['label']))}</b>\n"
        f"Candle: {r['candle_time']}\n\n"
        "<i>Research watch only. Not a recommendation, prediction, or trading instruction. "
        "No orders are placed.</i>"
    )


def format_discord_report(r):
    if r["signal"] == "BULLISH":
        signal_display = "UP 🟢"
    elif r["signal"] == "BEARISH":
        signal_display = "DOWN 🔴"
    else:
        return None

    return (
        "**Punjab Market Scanner — Educational Update**\n\n"
        f"**Market:** {r['symbol']}\n"
        f"**Timeframe:** {r['timeframe']}\n"
        f"**Signal:** **{signal_display}** (observation only)\n"
        f"**Last completed candle:** {r['price']:.6f}\n\n"
        f"EMA 9: {r['ema9']:.6f}\n"
        f"EMA 21: {r['ema21']:.6f}\n"
        f"EMA 50: {r['ema50']:.6f}\n"
        f"RSI 14: {r['rsi']:.2f}\n"
        f"RSI status: {rsi_warning(r['rsi'])}\n"
        f"RSI momentum: {r['rsi_momentum']}\n"
        f"MACD: {r['macd']:.6f}\n"
        f"MACD Signal: {r['macd_signal']:.6f}\n"
        f"MACD Histogram: {r['macd_hist']:.6f}\n"
        f"MACD momentum: {r['macd_momentum']}\n"
        f"ADX 14: {r['adx']:.2f}\n"
        f"Market regime: {r['market_regime']['label']} — {r['market_regime']['detail']}\n"
        f"Quant research: {r['quantitative_research']['sample_count']} returns; volatility {r['quantitative_research']['return_volatility_pct']:.3f}% (descriptive)\n"
        f"Risk research: historical max drawdown {r['risk_context']['max_drawdown_pct']:.2f}%; 95th percentile absolute move {r['risk_context']['return_p95_abs_pct']:.3f}%\n"
        f"Data quality: {r['data_quality']['status']} — {r['data_quality']['checks_passed']}/{r['data_quality']['checks_total']} checks; {r['data_quality']['invalid_rows']} invalid rows; {r['data_quality']['duplicate_timestamps']} duplicates\n"
        f"Algorithmic system: {r['algorithmic_system']['status']} — {r['algorithmic_system']['detail']}\n"
        + (f"Failed checks: {', '.join(r['algorithmic_system'].get('failed_checks', []))}\n" if r['algorithmic_system'].get('failed_checks') else "")
        + f"Testing/validation: {r['validation']['status']} — {r['validation']['detail']}\n"
        f"Walk-forward research: {r['walk_forward']['status']} — {r['walk_forward']['detail']}\n"
        f"ATR 14: {r['atr']:.6f}\n"
        f"Volatility context: {r['volatility']['regime']} — ATR {r['volatility']['atr_pct']:.3f}% of price; {r['volatility']['percentile']:.0f}th percentile (100 candles)\n"
        f"Support reference: {r['support']:.6f}\n"
        f"Resistance reference: {r['resistance']:.6f}\n\n"
        f"Candle time: {r['candle_time']}\n\n"
        "*Educational market data only. Not a trading instruction "
        "or prediction. No orders are placed.*"
    )



def format_single_telegram_brief(
    scan_results, confirmed_observations, watch_observations,
    scanner_health, calendar_context, accuracy, backtest_results,
    mtf_diagnostics, errors, new_records
):
    """One compact, non-actionable Telegram summary for the entire scan."""
    symbols = []
    for symbol in SYMBOLS:
        rows = [x for x in scan_results if x.get("symbol") == symbol]
        if not rows:
            label = "NO DATA"
        else:
            bull = sum(x.get("direction") == "BULLISH" for x in rows)
            bear = sum(x.get("direction") == "BEARISH" for x in rows)
            label = "BULLISH" if bull > bear else ("BEARISH" if bear > bull else "MIXED")
        symbols.append(f"{symbol}: {label}")

    bull_confirmed = sum(x.get("signal") == "BULLISH" for x in confirmed_observations)
    bear_confirmed = sum(x.get("signal") == "BEARISH" for x in confirmed_observations)
    if bull_confirmed > bear_confirmed:
        overall = "DEMO BUY OBSERVATION 🟢"
    elif bear_confirmed > bull_confirmed:
        overall = "DEMO SELL OBSERVATION 🔴"
    else:
        overall = "NO CONFIRMED SETUP — RESEARCH ONLY 🟡"

    quality = {}
    regimes = {}
    volatility = {}
    for item in scan_results:
        q = item.get("data_quality", {}).get("status", "UNKNOWN")
        r = item.get("market_regime", {}).get("label", "UNKNOWN")
        v = item.get("volatility", {}).get("regime", "UNKNOWN")
        quality[q] = quality.get(q, 0) + 1
        regimes[r] = regimes.get(r, 0) + 1
        volatility[v] = volatility.get(v, 0) + 1

    def compact_counts(values):
        return ", ".join(f"{k} {v}" for k, v in sorted(values.items())) or "No data"

    confirmed_lines = []
    for item in confirmed_observations[:5]:
        confirmed_lines.append(
            f"• {item.get('symbol')} {item.get('timeframe')}: "
            f"{item.get('signal')} DEMO | RSI {item.get('rsi', 0):.1f} | "
            f"ADX {item.get('adx', 0):.1f}"
        )
    watch_lines = []
    for item in watch_observations[:3]:
        direction = "BULLISH WATCH" if item.get("bull_score", 0) > item.get("bear_score", 0) else (
            "BEARISH WATCH" if item.get("bear_score", 0) > item.get("bull_score", 0) else "MIXED WATCH"
        )
        watch_lines.append(f"• {item.get('symbol')} {item.get('timeframe')}: {direction} (research only)")

    tested = [x for x in backtest_results if x.get("samples", 0) > 0]
    tested.sort(key=lambda x: x.get("samples", 0), reverse=True)
    backtest_line = "; ".join(
        f"{x['symbol']} {x['timeframe']}: {x['hit_rate']:.1f}% positive, n={x['samples']}"
        for x in tested[:3]
    ) or "Insufficient historical samples"

    events = (calendar_context or {}).get("events", [])[:2]
    event_lines = [
        f"• {e.get('event_time_utc', '')} {e.get('currency', '')} "
        f"[{e.get('impact', '')}] {e.get('event', '')}"
        for e in events
    ] or ["No source-attributed calendar events loaded"]

    return (
        "🐅 PUNJAB AI ROBOT — SINGLE SCAN BRIEF\\n"
        "🧪 RESEARCH / PAPER DEMO ONLY — NO ORDERS\\n\\n"
        f"OVERALL: {overall}\\n"
        f"MTF confirmed: {len(confirmed_observations)} | research watches: {len(watch_observations)}\\n"
        f"Markets scanned: {len({x.get('symbol') for x in scan_results})}/{len(SYMBOLS)} | "
        f"Timeframes: {len(TIMEFRAMES)} | analyses: {len(scan_results)}\\n\\n"
        "MARKET HEATMAP\\n" + "\\n".join(symbols) + "\\n\\n"
        "CONFIRMED DEMO OBSERVATIONS\\n"
        + ("\\n".join(confirmed_lines) if confirmed_lines else "No MTF-confirmed observations")
        + "\\n\\nRESEARCH WATCHES\\n"
        + ("\\n".join(watch_lines) if watch_lines else "No developing watch observations")
        + "\\n\\nDATA / MARKET CONTEXT\\n"
        + f"Quality: {compact_counts(quality)}\\n"
        + f"Regimes: {compact_counts(regimes)}\\n"
        + f"Volatility: {compact_counts(volatility)}\\n"
        + f"Economic calendar: {(calendar_context or {}).get('status', 'UNKNOWN')} "
        + f"({(calendar_context or {}).get('count', 0)} events)\\n"
        + ("\\n".join(event_lines))
        + "\\n\\nHISTORICAL VALIDATION\\n"
        + f"Evaluated: {accuracy.get('completed', 0)} | correct: {accuracy.get('correct', 0)} | "
        + f"incorrect: {accuracy.get('incorrect', 0)} | flat: {accuracy.get('flat', 0)}\\n"
        + f"Directional hit rate: {accuracy.get('win_rate'):.1f}%\\n" if accuracy.get("win_rate") is not None
        else "Directional hit rate: Not available\\n"
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

    # The workflow cron already limits scheduled scans to every 2 hours.
    # Do not re-check the current UTC hour here: GitHub may delay scheduled
    # workflow starts, which could incorrectly skip a valid scheduled run.

    history = load_history()
    # Freeze the data boundary before the first API request. Every market and
    # timeframe is evaluated only with candles closed by this same UTC instant.
    scan_cutoff = datetime.now(timezone.utc)

    checked = 0
    new_records = 0
    telegram_sent = 0
    discord_sent = 0
    errors = 0
    pending_notifications = []
    pending_watch_notifications = []
    telegram_confirmed_observations = []
    telegram_watch_observations = []
    scan_results = []
    backtest_results = []
    outcomes_evaluated = 0
    correct_observations = 0

    # Telegram is intentionally quiet during the scan; one combined brief is sent at the end.\n
    for symbol in SYMBOLS:
        if API_RATE_LIMITED:
            break

        for timeframe, (interval, _) in TIMEFRAMES.items():

            if API_RATE_LIMITED:
                break

            try:
                result = analyze(
                    symbol, timeframe, interval, as_of=scan_cutoff
                )

                checked += 1
                scan_results.append(result)
                backtest_results.append({"symbol": symbol, "timeframe": timeframe, **result["backtest"]})

                history, evaluated_now, correct_now = evaluate_past_signals(
                    result, history, horizon_bars=3
                )
                outcomes_evaluated += evaluated_now
                correct_observations = correct_now

                history, is_new = save_new_record(
                    result, history
                )

                if is_new:
                    new_records += 1

                    # Queue only newly recorded directional observations. The
                    # MTF gate below decides whether an educational update is
                    # eligible for delivery; repeated scans cannot resend the
                    # same candle because save_new_record() rejects duplicates.
                    if result.get("direction") in ("BULLISH", "BEARISH"):
                        pending_notifications.append(result)
                    else:
                        # A separate, non-actionable watch category broadens
                        # research coverage without weakening directional rules.
                        quality_status = result.get("data_quality", {}).get("status")
                        algorithm_status = result.get("algorithmic_system", {}).get("status")
                        bull = int(result.get("bull_score", 0))
                        bear = int(result.get("bear_score", 0))
                        adx_value = float(result.get("adx", 0))
                        near_directional = (
                            algorithm_status == "PASS"
                            and quality_status != "FAIL"
                            and adx_value >= 15
                            and (
                                (bull >= 3 and bull - bear >= 1)
                                or (bear >= 3 and bear - bull >= 1)
                            )
                        )
                        if near_directional:
                            pending_watch_notifications.append(result)

                    logging.info(
                        "Recorded research observation for %s %s (direction=%s).",
                        symbol, timeframe, result.get("direction", "UNKNOWN")
                    )

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

    # Freeze each signal's MTF cohort once; labels are not backfilled onto legacy data.
    history = label_mtf_cohorts(scan_results, history)

    # Report cohort counts for every directional candidate in this scan,
    # not merely the newly recorded observations queued for notification.
    mtf_diagnostics = mtf_diagnostic_summary(scan_results)
    mtf_blocked = mtf_diagnostics["blocked"]
    mtf_incomplete = mtf_diagnostics["incomplete"]

    for result in pending_notifications:
        same_market = [
            item for item in scan_results
            if item["symbol"] == result["symbol"]
        ]
        decision = mtf_decision(result, same_market)

        if decision["passed"]:
            mtf_text = (
                f"CONFIRMED: {decision['votes']}/{decision['scanned']} timeframes; "
                "H1 + M30 aligned; anchor ADX >= 20"
            )
            confidence_label = "MTF-CONFIRMED DEMO OBSERVATION"
            send_to_discord = True
        elif decision["cohort"] == "BLOCKED":
            # Complete, fresh cohorts that do not pass the strict MTF gate are
            # still shown as low-confidence educational observations on Telegram.
            # Incomplete/stale cohorts remain suppressed.
            mtf_text = (
                f"EARLY / MIXED: {decision['votes']}/{decision['scanned']} "
                f"timeframes agree; H1 aligned={decision['h1_aligned']}; "
                f"M30 aligned={decision['m30_aligned']}; reason={decision['reason']}"
            )
            # Keep non-confirmed cohorts visibly separate from BUY/SELL
            # demo labels: they are research watches, not trade signals.
            watch_report = format_watch_research_report(
                result,
                f"MTF not confirmed: {decision['votes']}/{decision['scanned']} timeframes agree; {decision['reason']}"
            )
            telegram_watch_observations.append(result)
            continue
        else:
            logging.info(
                "MTF %s %s %s: %s (agreement=%s/%s, H1=%s, M30=%s)",
                decision["cohort"], result["symbol"], result["timeframe"],
                decision["reason"], decision["votes"], decision["scanned"],
                decision["h1_aligned"], decision["m30_aligned"]
            )
            continue

        telegram_confirmed_observations.append(result)

        if send_to_discord:
            discord_report = format_discord_report(result)
            if discord_report is not None and discord(discord_report):
                discord_sent += 1

    for result in pending_watch_notifications:
        watch_report = format_watch_research_report(
            result,
            "Directional indicators are developing, but the strict directional threshold was not met."
        )
        telegram_watch_observations.append(result)

    logging.info(
        "MTF filter blocked %s candidates; %s incomplete.",
        mtf_blocked, mtf_incomplete
    )

    # Persistence failure must fail the job; otherwise an older CSV could
    # be uploaded as if it were the result of this scan.
    save_history_or_raise(history)

    accuracy = accuracy_summary(history)
    win_rate_text = (
        f"{accuracy['win_rate']:.1f}%"
        if accuracy["win_rate"] is not None
        else "Not available yet"
    )
    market_accuracy = accuracy_breakdown(history, "symbol")
    timeframe_accuracy = accuracy_breakdown(history, "timeframe")
    market_lines = "\n".join(market_accuracy) if market_accuracy else "Not available yet"
    timeframe_lines = "\n".join(timeframe_accuracy) if timeframe_accuracy else "Not available yet"
    mtf_accuracy = mtf_accuracy_summary(history)
    mtf_evidence_lines, mtf_evidence_stats = mtf_cohort_evidence_summary(history)
    integrity = accuracy_integrity_summary(history)
    integrity_warning_text = "; ".join(integrity["warnings"]) if integrity["warnings"] else "All totals reconcile; no duplicate keys detected"
    mtf_accuracy_text = "\n".join(mtf_accuracy.values())
    mtf_evidence_text = "\n".join(mtf_evidence_lines)
    # Diagnostics were computed from the full scan above (including
    # neutral frames), independently of the new-observation notification queue.
    mtf_reason_text = (
        "\n".join(f"{reason}: {count}" for reason, count in sorted(mtf_diagnostics["reasons"].items()))
        if mtf_diagnostics["reasons"] else "No directional candidates"
    )

    tested = [x for x in backtest_results if x["samples"] > 0]
    tested.sort(key=lambda x: x["avg_move_pct"], reverse=True)
    backtest_lines = [
        f'{x["symbol"]} {x["timeframe"]}: {x["samples"]} samples; '
        f'positive {x["hit_rate"]:.1f}%; average {x["avg_move_pct"]:+.4f}%; '
        f'median {x["median_move_pct"]:+.4f}%'
        for x in tested
    ]
    backtest_text = "\n".join(backtest_lines) if backtest_lines else "Not enough historical samples yet"

    scanner_health = scanner_health_context(
        expected_analyses=len(SYMBOLS) * len(TIMEFRAMES),
        completed_analyses=checked,
        processing_errors=errors,
        api_rate_limited=API_RATE_LIMITED,
        telegram_deliveries=telegram_sent,
        discord_deliveries=discord_sent,
    )

    calendar_context = economic_calendar_context(
        path="economic_calendar.csv",
        as_of=scan_cutoff,
        symbols=SYMBOLS,
        lookahead_hours=24,
    )

    summary = (
        "<b>Punjab Scan Complete</b>\n\n"
        f"Markets: {len(SYMBOLS)}\n"
        f"Timeframes per market: {len(TIMEFRAMES)}\n"
        f"Analyses completed: {checked}\n"
        f"New history records: {new_records}\n"
        f"Telegram updates sent: {telegram_sent}\n"
        f"Discord updates sent: {discord_sent}\n"
        f"Data/processing issues: {errors}\n"
        f"Scanner health: {scanner_health['status']} — {scanner_health['completion_pct']:.1f}% complete; "
        f"{scanner_health['completed_analyses']}/{scanner_health['expected_analyses']} analyses; "
        f"errors={scanner_health['processing_errors']}; API rate limited={scanner_health['api_rate_limited']}\n"
        f"Successful notification deliveries: Telegram={scanner_health['telegram_deliveries']}, Discord={scanner_health['discord_deliveries']}\n"
        f"Past observations evaluated this scan: {outcomes_evaluated}\n"
        f"MTF blocked: {mtf_blocked} | incomplete: {mtf_incomplete}\n"
        f"MTF candidates: {mtf_diagnostics['candidates']} | passed: {mtf_diagnostics['passed']} | blocked: {mtf_diagnostics['blocked']} | incomplete: {mtf_diagnostics['incomplete']}\n"
        f"MTF block reasons: {mtf_reason_text}\n\n"
        "<b>MTF Cohort Evidence (exact 3-candle; legacy rows excluded)</b>\n"
        f"{mtf_evidence_text}\n\n"
        "<b>Verified Exact 3-Candle Directional Accuracy</b>\n"
        f"Completed observations: {accuracy['completed']}\n"
        f"Correct: {accuracy['correct']}\n"
        f"Incorrect: {accuracy['incorrect']}\n"
        f"Flat: {accuracy['flat']}\n"
        f"Directional hit rate: {win_rate_text}\n\n"
        f"Data integrity: {integrity['status']}\n"
        f"Market rows reconciled: {integrity['market_rows']} | timeframe rows reconciled: {integrity['timeframe_rows']}\n"
        f"Duplicate keys: {integrity['duplicate_keys']} | invalid exact outcomes: {integrity['invalid_exact_status']}\n"
        f"Integrity details: {integrity_warning_text}\n\n"
        "<b>Accuracy by Market</b>\n"
        f"{market_lines}\n\n"
        "<b>Accuracy by Timeframe</b>\n"
        f"{timeframe_lines}\n\n"
        "<b>Base-rule Non-overlapping Holdout Sample (not MTF-filtered; final 30%, exact 3-candle horizon)</b>\n"
        f"{backtest_text}\n\n"
        "<i>Backtest samples use non-overlapping exact 3-candle outcome windows. "
        "Persisted accuracy includes only observations evaluated at exactly "
        "the third subsequent completed candle. Older variable-horizon "
        "results are excluded. Flat outcomes are excluded from hit rate. "
        "This is historical direction testing, not verified profitability; "
        "spread, slippage, and fees are not included. No orders were placed.</i>"
    )

    # Included in the combined Telegram brief below.\n

    # Send exactly one concise Telegram message for this completed scan.
    brief = format_single_telegram_brief(
        scan_results=scan_results,
        confirmed_observations=telegram_confirmed_observations,
        watch_observations=telegram_watch_observations,
        scanner_health=scanner_health,
        calendar_context=calendar_context,
        accuracy=accuracy,
        backtest_results=backtest_results,
        mtf_diagnostics=mtf_diagnostics,
        errors=errors,
        new_records=new_records,
    )
    # Keep one message below Telegram's 4096-character sendMessage limit.
    brief = brief[:3900]
    if telegram(brief):
        telegram_sent = 1
    else:
        telegram_sent = 0

    # Cross-market research is descriptive only and uses aligned completed-candle returns.
    anomaly_count = sum(
        item.get("anomaly_research", {}).get("status") == "UNUSUAL OBSERVATION"
        for item in scan_results
    )
    correlations_by_timeframe = {}
    for timeframe in TIMEFRAMES:
        timeframe_series = {
            item["symbol"]: item["_candles"]
            for item in scan_results
            if item["timeframe"] == timeframe
        }
        correlations_by_timeframe[timeframe] = cross_market_correlation_context(
            timeframe_series, minimum_samples=30
        )

    dashboard_data = advanced_research_dashboard(
        scan_results,
        correlations_by_timeframe,
        calendar_context=calendar_context,
        scanner_health=scanner_health,
    )
    # Included in the combined Telegram brief below.\n
    intelligence_report = build_intelligence_hub(
        dashboard_data,
        scan_results,
        scanner_health,
        calendar_context=calendar_context,
    )
    # Included in the combined Telegram brief below.\n
    # Aggregate existing diagnostics; leave scanner signals and decisions unchanged.
    quant_report = build_quant_intelligence(scan_results)
    # Included in the combined Telegram brief below.\n
    # Snapshot generation is best-effort and must never interrupt legacy reports.
    try:
        write_bot_snapshot(
            scan_cutoff=scan_cutoff,
            scanner_health=scanner_health,
            dashboard=dashboard_data,
            intelligence=intelligence_report,
            calendar_context=calendar_context,
            scan_results=scan_results,
        )
        if upload_snapshot():
            logging.info("Super Bot snapshot uploaded to the private state bridge.")
    except (OSError, TypeError, ValueError, requests.RequestException) as exc:
        logging.warning(
            "Super Bot snapshot or bridge unavailable (%s).",
            type(exc).__name__,
        )

    research_lines = [
        "<b>Cross-Market Research (historical correlation)</b>",
        "Correlation is descriptive, not causation or a forecast.",
    ]
    for timeframe in TIMEFRAMES:
        timeframe_series = {
            item["symbol"]: item["_candles"]
            for item in scan_results
            if item["timeframe"] == timeframe
        }
        correlation = correlations_by_timeframe[timeframe]
        top_pairs = correlation["pairs"][:3]
        if top_pairs:
            pair_text = "; ".join(
                f"{pair['symbol_a']} / {pair['symbol_b']}: "
                f"{pair['correlation']:+.2f} (n={pair['samples']})"
                for pair in top_pairs
            )
        else:
            pair_text = "Insufficient aligned history"
        research_lines.append(f"{timeframe}: {pair_text}")

    research_lines.extend([
        "",
        "<b>Statistical Anomaly Diagnostics</b>",
        f"Unusual historical observations: {anomaly_count}/{len(scan_results)}",
        "Outlier flags describe unusually large historical returns; they do not predict direction.",
        "",
        "<i>Research context only. No buy/sell instructions or orders.</i>",
    ])
    # Cross-market diagnostics are represented in the dashboard and snapshot.\n
    discord(
        "**Punjab Scan Complete**\n\n"
        f"Markets: {len(SYMBOLS)}\n"
        f"Timeframes per market: {len(TIMEFRAMES)}\n"
        f"Analyses completed: {checked}\n"
        f"New history records: {new_records}\n"
        f"Telegram updates sent: {telegram_sent}\n"
        f"Discord updates sent: {discord_sent}\n"
        f"Data/processing issues: {errors}\n"
        f"Past observations evaluated this scan: {outcomes_evaluated}\n"
        f"MTF blocked: {mtf_blocked} | incomplete: {mtf_incomplete}\n"
        f"MTF candidates: {mtf_diagnostics['candidates']} | passed: {mtf_diagnostics['passed']} | blocked: {mtf_diagnostics['blocked']} | incomplete: {mtf_diagnostics['incomplete']}\n"
        f"MTF block reasons: {mtf_reason_text}\n\n"
        "**MTF Cohort Accuracy (exact 3-candle; legacy rows excluded)**\n"
        f"{mtf_accuracy_text}\n\n"
        "**Overall Historical Directional Accuracy**\n"
        f"Completed observations: {accuracy['completed']}\n"
        f"Correct: {accuracy['correct']}\n"
        f"Incorrect: {accuracy['incorrect']}\n"
        f"Flat: {accuracy['flat']}\n"
        f"Directional hit rate: {win_rate_text}\n\n"
        "**Accuracy by Market**\n"
        f"{market_lines}\n\n"
        "**Accuracy by Timeframe**\n"
        f"{timeframe_lines}\n\n"
        "**Base-rule Rolling Holdout Sample (not MTF-filtered; final 30%, exact 3-candle horizon)**\n"
        f"{backtest_text}\n\n"
        "*Backtest samples use next-candle-open entry and non-overlapping exact 3-candle outcome windows. "
        "Persisted accuracy includes only exact third-candle evaluations. "
        "Older variable-horizon results are excluded. Hit rate excludes flats. "
        "Spread, slippage, and fees are not included; this is not verified "
        "profitability. No orders were placed.*"
    )


if __name__ == "__main__":
    main()
