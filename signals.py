# =============================================================================
# signals.py — Technical Indicators, Momentum & Sentiment Scoring
# =============================================================================

from __future__ import annotations
import logging
import pandas as pd
import numpy as np
from config import (
    WEIGHT_RSI, WEIGHT_MACD, WEIGHT_MA,
    WEIGHT_VOLUME, WEIGHT_MOMENTUM
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Individual Indicators
# ---------------------------------------------------------------------------

def compute_rsi(prices: pd.Series, period: int = 14) -> float:
    """
    Relative Strength Index (0-100).
    Best buy zone: 40–60 (not overbought, has upward room).
    Returns a 0–1 score.
    """
    delta = prices.diff().dropna()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)

    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]

    if avg_loss == 0:
        rsi = 100.0
    else:
        rs  = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    # Score: peak around RSI=50-60, penalise extremes
    if rsi < 30:
        return 0.2   # Oversold — risky but possible reversal
    elif rsi > 75:
        return 0.1   # Overbought — likely pullback
    elif 45 <= rsi <= 65:
        return 1.0   # Sweet spot
    else:
        return 0.6


def compute_macd_signal(prices: pd.Series) -> float:
    """
    MACD = EMA(12) - EMA(26), Signal = EMA(9) of MACD.
    Score 1.0 if MACD just crossed above signal (bullish crossover).
    Score 0.5 if MACD is above signal (uptrend continuing).
    Score 0.0 if MACD is below signal (downtrend).
    """
    ema12  = prices.ewm(span=12, adjust=False).mean()
    ema26  = prices.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()

    macd_now   = macd.iloc[-1]
    macd_prev  = macd.iloc[-2]
    signal_now = signal.iloc[-1]
    signal_prev = signal.iloc[-2]

    # Bullish crossover: MACD crossed above signal in the last bar
    if macd_prev < signal_prev and macd_now > signal_now:
        return 1.0
    # MACD above signal: ongoing uptrend
    elif macd_now > signal_now:
        return 0.6
    # MACD below signal: downtrend
    else:
        return 0.0


def compute_ma_score(prices: pd.Series) -> float:
    """
    Price relative to 20-day and 50-day moving averages.
    Score 1.0 if price > MA20 > MA50 (strong uptrend).
    Score 0.5 if price > MA20 only.
    Score 0.0 if price < both MAs.
    """
    if len(prices) < 50:
        return 0.5  # Not enough data, neutral

    ma20 = prices.rolling(20).mean().iloc[-1]
    ma50 = prices.rolling(50).mean().iloc[-1]
    current = prices.iloc[-1]

    if current > ma20 > ma50:
        return 1.0
    elif current > ma20:
        return 0.6
    elif current > ma50:
        return 0.3
    else:
        return 0.0


def compute_volume_score(volumes: pd.Series) -> float:
    """
    Volume spike: today's volume vs. 20-day average.
    Score 1.0 if volume is 2x+ the average (unusual interest).
    Score 0.5 if volume is roughly average.
    Score 0.0 if volume is low.
    """
    if len(volumes) < 20:
        return 0.5

    avg_vol     = volumes.iloc[-21:-1].mean()   # 20-day average (excluding today)
    today_vol   = volumes.iloc[-1]

    if avg_vol == 0:
        return 0.5

    ratio = today_vol / avg_vol

    if ratio >= 2.0:
        return 1.0
    elif ratio >= 1.5:
        return 0.8
    elif ratio >= 1.0:
        return 0.5
    elif ratio >= 0.7:
        return 0.3
    else:
        return 0.1


def compute_momentum_score(prices: pd.Series, days: int = 5) -> float:
    """
    Price momentum over the last N days.
    A stock that's been trending up in recent days is more likely to continue.
    Returns a 0–1 score based on % change.
    """
    if len(prices) < days + 1:
        return 0.5

    pct_change = (prices.iloc[-1] - prices.iloc[-(days + 1)]) / prices.iloc[-(days + 1)]

    if pct_change >= 0.05:
        return 1.0    # Up 5%+ in last 5 days — strong momentum
    elif pct_change >= 0.02:
        return 0.8
    elif pct_change >= 0.0:
        return 0.6    # Slight positive momentum
    elif pct_change >= -0.02:
        return 0.3
    else:
        return 0.0    # Downtrend


# ---------------------------------------------------------------------------
# Composite Score
# ---------------------------------------------------------------------------

def score_stock(symbol: str, df: pd.DataFrame) -> dict:
    """
    Given a DataFrame with columns [open, high, low, close, volume],
    compute a composite score from 0–1 and return all individual scores.

    Args:
        symbol: Ticker symbol (for logging)
        df: OHLCV DataFrame indexed by date, sorted oldest → newest

    Returns:
        dict with 'score' (0–1) and individual indicator scores
    """
    try:
        closes  = df["close"].astype(float)
        volumes = df["volume"].astype(float)

        rsi_score      = compute_rsi(closes)
        macd_score     = compute_macd_signal(closes)
        ma_score       = compute_ma_score(closes)
        volume_score   = compute_volume_score(volumes)
        momentum_score = compute_momentum_score(closes)

        composite = (
            WEIGHT_RSI      * rsi_score +
            WEIGHT_MACD     * macd_score +
            WEIGHT_MA       * ma_score +
            WEIGHT_VOLUME   * volume_score +
            WEIGHT_MOMENTUM * momentum_score
        )

        return {
            "symbol":         symbol,
            "score":          round(composite, 4),
            "rsi_score":      round(rsi_score, 4),
            "macd_score":     round(macd_score, 4),
            "ma_score":       round(ma_score, 4),
            "volume_score":   round(volume_score, 4),
            "momentum_score": round(momentum_score, 4),
            "close":          round(float(closes.iloc[-1]), 2),
        }

    except Exception as e:
        logger.warning(f"[{symbol}] Scoring failed: {e}")
        return None
