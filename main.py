
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
# PUNJAB ADVANCED SCANNER + HISTORICAL PAPER BACKTEST
# Educational analysis only. No broker. No live orders.
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
    "M1": "1min",
    "M2": "2min",
    "M5": "5min",
    "M10": "10min",
}

OUTPUT_SIZE = 500
MIN_CANDLES = 45
FORWARD_CANDLES = 3
REQUEST_DELAY = 1.5

SIGNAL_FILE = Path("signal_history.csv")
BACKTEST_FILE = Path("backtest_history.csv")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

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
        logging.warning("Telegram settings missing")
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
        logging.error("Twelve Data API key missing")
        return None

    try:
        response = session.get(
            "https://api.twelvedata.com/time_series",
            params={
                "symbol": symbol,
                "interval": "1min",
                "outputsize": OUTPUT_SIZE,
                "apikey": API_KEY,
                "format": "JSON",
                "timezone": "UTC",
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        if "values" not in data:
            logging.warning("%s: %s", symbol, data.get("message", data))
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

        return (
            df.sort_values("datetime")
            .drop_duplicates("datetime")
            .set_index("datetime")
        )

    except (requests.RequestException, ValueError, KeyError) as error:
        logging.error("%s data error: %s", symbol, error)
        return None


# ---------------- TIMEFRAMES ----------------

def prepare_timeframe(raw, timeframe):
    interval = TIMEFRAMES[timeframe]
    minutes = int(interval.replace("min", ""))

    if timeframe == "M1":
        df = raw.copy()
    else:
        df = raw.resample(interval).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
        }).dropna()

    now = pd.Timestamp.now(tz="UTC")
    df = df[
        df.index + pd.Timedelta(minutes=minutes) <= now
    ]

    if len(df) < MIN_CANDLES:
        return None

    return df


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

    avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean()

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

    df["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()

    up = high.diff()
    down = -low.diff()

    plus_dm = up.where((up > down) & (up > 0), 0)
    minus_dm = down.where((down > up) & (down > 0), 0)

    atr_safe = df["atr"].replace(0, np.nan)

    plus_di = (
        100 * plus_dm.ewm(alpha=1 / 14, adjust=False).mean()
        / atr_safe
    )
    minus_di = (
        100 * minus_dm.ewm(alpha=1 / 14, adjust=False).mean()
        / atr_safe
    )

    denominator = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / denominator

    df["adx"] = dx.ewm(alpha=1 / 14, adjust=False).mean()
    df["adx"] = df["adx"].fillna(0)

    df["support"] = low.rolling(20).min()
    df["resistance"] = high.rolling(20).max()

    return df


# ---------------- SIGNAL CALCULATION ----------------

def calculate_signal(row):
    fields = [
        "close", "ema9", "ema21", "ema50",
        "rsi", "macd", "macd_signal",
        "atr", "adx", "support", "resistance",
    ]

    if not np.isfinite(
        row[fields].to_numpy(dtype=float)
    ).all():
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
        "reasons": "; ".join(reasons),
    }


# ---------------- LIVE PAPER ANALYSIS ----------------

def analyze_latest(df):
    prepared = add_indicators(df)
    row = prepared.iloc[-1]
    result = calculate_signal(row)

    if result is None:
        return None

    result["time"] = prepared.index[-1].isoformat()
    return result


def make_report(symbol, timeframe, result):
    return (
        "📊 <b>PUNJAB ADVANCED SCANNER</b>\n\n"
        f"<b>Symbol:</b> {html.escape(symbol)}\n"
        f"<b>Timeframe:</b> {timeframe}\n"
        f"<b>Analysis:</b> {result['direction']}\n\n"
        f"<b>Observed price:</b> {result['price']:.5f}\n"
        f"<b>Indicator alignment:</b> {result['score']}/5\n"
        f"<b>BUY score:</b> {result['buy_score']}\n"
        f"<b>SELL score:</b> {result['sell_score']}\n\n"
        f"<b>RSI:</b> {result['rsi']:.2f}\n"
        f"<b>ADX:</b> {result['adx']:.2f}\n"
        f"<b>ATR:</b> {result['atr']:.5f}\n"
        f"<b>Support:</b> {result['support']:.5f}\n"
        f"<b>Resistance:</b> {result['resistance']:.5f}\n\n"
        f"<b>Reasons:</b> {html.escape(result['reasons'])}\n"
        f"<b>Candle time:</b> {result['time']}\n\n"
        "<i>Paper analysis only. No real orders.</i>"
    )


# ---------------- HISTORICAL BACKTEST ----------------

def run_backtest(df, symbol, timeframe):
    """
    Historical signal is evaluated against the close
    exactly three completed candles later.

    BUY wins if future close > signal close.
    SELL wins if future close < signal close.
    Equal prices are neutral and excluded.
    """

    prepared = add_indicators(df)
    records = []

    if len(prepared) <= MIN_CANDLES + FORWARD_CANDLES:
        return records

    for i in range(MIN_CANDLES, len(prepared) - FORWARD_CANDLES):
        row = prepared.iloc[i]
        signal = calculate_signal(row)

        if signal is None:
            continue

        direction = signal["direction"]

        if direction == "WAIT":
            continue

        entry = float(row["close"])
        future = float(
            prepared.iloc[i + FORWARD_CANDLES]["close"]
        )

        if direction == "BUY ANALYSIS":
            outcome = (
                "WIN" if future > entry
                else "LOSS" if future < entry
                else "NEUTRAL"
            )
        else:
            outcome = (
                "WIN" if future < entry
                else "LOSS" if future > entry
                else "NEUTRAL"
            )

        change_pct = (
            ((future - entry) / entry) * 100
            if entry != 0 else 0
        )

        records.append({
            "tested_at": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "timeframe": timeframe,
            "signal_time": prepared.index[i].isoformat(),
            "direction": direction,
            "entry_close": entry,
            "future_close": future,
            "future_candles": FORWARD_CANDLES,
            "outcome": outcome,
            "market_change_pct": change_pct,
        })

    return records


def save_backtest(records):
    if not records:
        return

    new = pd.DataFrame(records)

    if BACKTEST_FILE.exists():
        try:
            old = pd.read_csv(BACKTEST_FILE)
            new = pd.concat([old, new], ignore_index=True)
        except (OSError, ValueError) as error:
            logging.warning("Backtest history read issue: %s", error)

    new = new.drop_duplicates(
        subset=["symbol", "timeframe", "signal_time"],
        keep="last",
    )

    new.to_csv(BACKTEST_FILE, index=False)


def backtest_summary(all_records):
    if not all_records:
        return (
            "📊 <b>PUNJAB BACKTEST</b>\n\n"
            "Not enough historical data or no qualifying signals.\n"
            "No performance result available."
        )

    df = pd.DataFrame(all_records)
    wins = int((df["outcome"] == "WIN").sum())
    losses = int((df["outcome"] == "LOSS").sum())
    neutral = int((df["outcome"] == "NEUTRAL").sum())
    decided = wins + losses

    rate = wins / decided * 100 if decided else 0

    lines = [
        "📊 <b>PUNJAB HISTORICAL PAPER BACKTEST</b>",
        "",
        f"Signals tested: {len(df)}",
        f"Wins: {wins}",
        f"Losses: {losses}",
        f"Neutral: {neutral}",
        f"Win rate on decided signals: {rate:.2f}%",
        "",
        f"Evaluation: next {FORWARD_CANDLES} candles",
        "",
        "<b>By market and timeframe:</b>",
    ]

    grouped = df.groupby(["symbol", "timeframe"])

    for (symbol, timeframe), group in grouped:
        w = int((group["outcome"] == "WIN").sum())
        l = int((group["outcome"] == "LOSS").sum())
        n = int((group["outcome"] == "NEUTRAL").sum())
        total = w + l
        pct = w / total * 100 if total else 0

        lines.append(
            f"{html.escape(symbol)} {timeframe}: "
            f"{w}W / {l}L / {n}N ({pct:.1f}%)"
        )

    lines.extend([
        "",
        "<i>Historical paper results only. "
        "Not a forecast or guarantee. "
        "No spread, fees or slippage included. "
        "No real orders placed.</i>",
    ])

    return "\n".join(lines)


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
            logging.warning("Signal history issue: %s", error)

    new = new.drop_duplicates(
        subset=["symbol", "timeframe", "time"],
        keep="last",
    )

    new.to_csv(SIGNAL_FILE, index=False)


# ---------------- MAIN ----------------

def main():
    logging.info("Punjab Scanner and Backtest started")

    sent = 0
    saved = 0
    scanned = 0
    issues = 0
    all_backtest_records = []

    for symbol in SYMBOLS:
        logging.info("Scanning %s", symbol)

        market = fetch_market_data(symbol)

        if market is None or market.empty:
            issues += 1
            time.sleep(REQUEST_DELAY)
            continue

        for timeframe in TIMEFRAMES:
            try:
                prepared = prepare_timeframe(market, timeframe)

                if prepared is None:
                    logging.info(
                        "%s %s: insufficient candles",
                        symbol, timeframe,
                    )
                    continue

                # Latest paper analysis
                result = analyze_latest(prepared)

                if result is not None:
                    scanned += 1
                    save_signal(symbol, timeframe, result)
                    saved += 1

                    if result["direction"] != "WAIT":
                        if send_telegram(
                            make_report(symbol, timeframe, result)
                        ):
                            sent += 1

                # Historical backtesting
                records = run_backtest(
                    prepared, symbol, timeframe
                )
                all_backtest_records.extend(records)

            except Exception:
                logging.exception(
                    "Analysis error: %s %s",
                    symbol, timeframe,
                )
                issues += 1

        time.sleep(REQUEST_DELAY)

    save_backtest(all_backtest_records)

    # Send historical backtest report
    backtest_message = backtest_summary(
        all_backtest_records
    )
    backtest_sent = send_telegram(backtest_message)

    summary = (
        "✅ <b>PUNJAB SCAN COMPLETE</b>\n\n"
        f"Markets checked: {len(SYMBOLS)}\n"
        f"Latest analyses: {scanned}\n"
        f"Signal records saved: {saved}\n"
        f"Analysis alerts sent: {sent}\n"
        f"Historical signals tested: {len(all_backtest_records)}\n"
        f"Backtest report sent: {'Yes' if backtest_sent else 'No'}\n"
        f"Data or analysis issues: {issues}\n\n"
        "<i>Educational paper analysis only. "
        "No real orders placed.</i>"
    )

    send_telegram(summary)

    logging.info(
        "Completed | Analyses=%s Saved=%s Alerts=%s "
        "Backtests=%s Issues=%s",
        scanned, saved, sent,
        len(all_backtest_records), issues,
    )


if __name__ == "__main__":
    main()
