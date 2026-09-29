"""
Stock Screener — identifies candidates likely to rise based on technical signals.
Signals used:
  1. RSI Oversold Recovery  (RSI crossed above 35 from below)
  2. Volume Surge           (today's volume > 2x 20-day average)
  3. Bullish MACD Crossover (MACD line crossed above signal line)
  4. Price near 52-week low bounce (within 15% of 52w low, recovering)
  5. Momentum               (price up 2–8% today — not overextended)
"""

from __future__ import annotations
import yfinance as yf
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.trend import MACD
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.WARNING)

# ── Universe of stocks to scan ───────────────────────────────────────────────
# S&P 500 subset + high-liquidity mid caps for demo; extend as you like
STOCK_UNIVERSE = [
    # Mega cap
    "AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA","BRK-B","JPM","V",
    "UNH","XOM","LLY","JNJ","WMT","MA","PG","HD","CVX","MRK",
    # Large cap growth
    "AVGO","COST","ABBV","PEP","KO","ADBE","CRM","TMO","ACN","MCD",
    "BAC","LIN","AMD","QCOM","NEE","TXN","HON","UPS","SBUX","GS",
    "AMGN","CAT","MS","INTU","AXP","SPGI","DE","BLK","ISRG","GILD",
    # Mid cap momentum
    "ENPH","DXCM","CRWD","SNOW","PLTR","NET","DDOG","ZS","BILL","AFRM",
    "ROKU","SHOP","SQ","COIN","RBLX","U","PATH","GTLB","MDB","DASH",
    # Healthcare
    "CVS","CI","HUM","ELV","DGX","ZBH","BSX","EW","IDXX","ALGN",
    # Energy
    "SLB","MPC","PSX","VLO","OXY","DVN","HAL","BKR","FANG","PR",
    # Financials
    "WFC","C","USB","PNC","TFC","COF","AIG","CB","MMC","AON",
    # Consumer
    "NKE","TGT","LULU","BURL","FIVE","ROST","YUM","CMG","DPZ","EL",
]

def fetch_data(ticker: str, period: str = "6mo") -> pd.DataFrame | None:
    """Download OHLCV data for a ticker. Returns None on failure."""
    try:
        df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
        if df is None or len(df) < 50:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return df
    except Exception:
        return None


def compute_signals(df: pd.DataFrame) -> dict:
    """Compute all technical indicators and return a signal dict."""
    close = df["Close"].squeeze()
    volume = df["Volume"].squeeze()
    high = df["High"].squeeze()
    low = df["Low"].squeeze()

    # RSI
    rsi_series = RSIIndicator(close=close, window=14).rsi()
    rsi_now = float(rsi_series.iloc[-1])
    rsi_prev = float(rsi_series.iloc[-2])

    # MACD
    macd_obj = MACD(close=close)
    macd_line = macd_obj.macd()
    signal_line = macd_obj.macd_signal()
    macd_now = float(macd_line.iloc[-1])
    macd_prev = float(macd_line.iloc[-2])
    sig_now = float(signal_line.iloc[-1])
    sig_prev = float(signal_line.iloc[-2])

    # Volume
    vol_now = float(volume.iloc[-1])
    vol_avg20 = float(volume.iloc[-21:-1].mean())
    vol_ratio = vol_now / vol_avg20 if vol_avg20 > 0 else 1.0

    # Price momentum
    price_now = float(close.iloc[-1])
    price_prev = float(close.iloc[-2])
    price_pct = (price_now - price_prev) / price_prev * 100

    # 52-week range
    high_52 = float(high.iloc[-252:].max()) if len(high) >= 252 else float(high.max())
    low_52 = float(low.iloc[-252:].min()) if len(low) >= 252 else float(low.min())
    pct_from_52low = (price_now - low_52) / low_52 * 100

    # 20-day moving average for trend context
    ma20 = float(close.iloc[-20:].mean())

    return {
        "price": price_now,
        "price_pct": price_pct,
        "rsi": rsi_now,
        "rsi_prev": rsi_prev,
        "macd_now": macd_now,
        "macd_prev": macd_prev,
        "sig_now": sig_now,
        "sig_prev": sig_prev,
        "vol_ratio": vol_ratio,
        "pct_from_52low": pct_from_52low,
        "high_52": high_52,
        "low_52": low_52,
        "ma20": ma20,
    }


def score_stock(signals: dict) -> tuple[int, list[str]]:
    """
    Score a stock 0–5 based on how many bullish signals it triggers.
    Returns (score, reasons).
    """
    score = 0
    reasons = []
    s = signals

    # Signal 1: RSI oversold recovery (RSI was below 35, now crossing up)
    if s["rsi_prev"] < 35 and s["rsi"] >= 35:
        score += 1
        reasons.append(f"RSI oversold recovery ({s['rsi']:.1f})")
    elif 35 <= s["rsi"] <= 50:
        score += 0.5
        reasons.append(f"RSI in recovery zone ({s['rsi']:.1f})")

    # Signal 2: Volume surge (>2x average)
    if s["vol_ratio"] >= 2.0:
        score += 1
        reasons.append(f"Volume surge ({s['vol_ratio']:.1f}x avg)")
    elif s["vol_ratio"] >= 1.5:
        score += 0.5
        reasons.append(f"Above-avg volume ({s['vol_ratio']:.1f}x)")

    # Signal 3: Bullish MACD crossover
    if s["macd_prev"] < s["sig_prev"] and s["macd_now"] > s["sig_now"]:
        score += 1
        reasons.append("Bullish MACD crossover")
    elif s["macd_now"] > s["sig_now"] and s["macd_now"] > 0:
        score += 0.5
        reasons.append("MACD bullish & above zero")

    # Signal 4: Bounce off 52-week low (within 20%, recovering)
    if 0 < s["pct_from_52low"] < 20 and s["price_pct"] > 0:
        score += 1
        reasons.append(f"Bouncing off 52w low (+{s['pct_from_52low']:.1f}% above low)")

    # Signal 5: Healthy momentum (up 1–8% today, not overextended)
    if 1.0 <= s["price_pct"] <= 8.0:
        score += 1
        reasons.append(f"Healthy momentum (+{s['price_pct']:.1f}% today)")
    elif 0 < s["price_pct"] < 1.0:
        score += 0.25
        reasons.append(f"Slight upward move (+{s['price_pct']:.2f}%)")

    # Penalty: RSI overbought (>75) — likely overextended
    if s["rsi"] > 75:
        score -= 1
        reasons.append(f"⚠️ RSI overbought ({s['rsi']:.1f}) — penalized")

    # Penalty: price above 20-day MA by more than 10% — chasing
    if s["price"] > s["ma20"] * 1.10:
        score -= 0.5
        reasons.append("⚠️ Extended above MA20 — penalized")

    return max(0, score), reasons


def run_screener(universe: list[str] = None, min_score: float = 2.0,
                 max_price: float = 10000, min_price: float = 5.0) -> pd.DataFrame:
    """
    Run screener across the universe. Returns DataFrame of candidates sorted by score.
    """
    if universe is None:
        universe = STOCK_UNIVERSE

    results = []
    print(f"Scanning {len(universe)} stocks...")

    for i, ticker in enumerate(universe):
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(universe)} scanned...")

        df = fetch_data(ticker)
        if df is None:
            continue

        try:
            signals = compute_signals(df)
        except Exception:
            continue

        # Basic price filter
        if not (min_price <= signals["price"] <= max_price):
            continue

        score, reasons = score_stock(signals)
        if score >= min_score:
            results.append({
                "Ticker": ticker,
                "Price": round(signals["price"], 2),
                "Score": round(score, 1),
                "RSI": round(signals["rsi"], 1),
                "Vol Ratio": round(signals["vol_ratio"], 2),
                "Day %": round(signals["price_pct"], 2),
                "MACD": round(signals["macd_now"], 4),
                "Reasons": " | ".join(reasons),
            })

    df_out = pd.DataFrame(results)
    if not df_out.empty:
        df_out = df_out.sort_values("Score", ascending=False).reset_index(drop=True)

    print(f"\nScreener complete. {len(df_out)} candidates found (min score={min_score}).")
    return df_out


if __name__ == "__main__":
    df = run_screener(min_score=2.0)
    pd.set_option("display.max_colwidth", 80)
    pd.set_option("display.width", 200)
    print(df.to_string(index=False))
