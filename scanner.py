# =============================================================================
# scanner.py — Daily Stock Scanner
# =============================================================================
# Fetches all tradable US stocks from Alpaca, downloads price history,
# scores each one using technical signals, and returns the top candidates.

from __future__ import annotations
import logging
import time
import pandas as pd
import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta
import pytz

from config import (
    ALPACA_API_KEY, ALPACA_SECRET_KEY,
    MIN_STOCK_PRICE, MAX_STOCK_PRICE,
    MIN_AVG_VOLUME, MAX_POSITIONS
)
from signals import score_stock

logger = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")


def get_tradable_symbols(trading_client: TradingClient) -> list[str]:
    """
    Fetch all US equity assets from Alpaca that are:
    - Active and tradable
    - Listed on major US exchanges (NYSE, NASDAQ, ARCA)
    - Not ETFs (we want individual stocks)
    """
    logger.info("Fetching tradable asset list from Alpaca...")
    assets = trading_client.get_all_assets()

    symbols = []
    for asset in assets:
        if (
            asset.tradable
            and asset.status == "active"
            and asset.asset_class == "us_equity"
            and asset.exchange in ("NYSE", "NASDAQ", "ARCA")
            and "." not in asset.symbol   # Skip foreign listings (BRK.B etc.)
            and "/" not in asset.symbol
        ):
            symbols.append(asset.symbol)

    logger.info(f"Found {len(symbols)} tradable US equity symbols")
    return symbols


def fetch_ohlcv_batch(symbols: list[str], lookback_days: int = 100) -> dict:
    """
    Download daily OHLCV for many symbols in one yfinance call.
    Returns {symbol: DataFrame[open, high, low, close, volume]}.
    100 calendar days gives ~68 trading days, enough for the 50-day MA.
    """
    out = {}
    try:
        end   = datetime.now(ET) + timedelta(days=1)   # end is exclusive — include today
        start = end - timedelta(days=lookback_days)
        data = yf.download(
            symbols,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1d",
            progress=False,
            auto_adjust=True,
            group_by="ticker",
            threads=True,
        )
    except Exception as e:
        logger.debug(f"Batch download failed: {e}")
        return out
    if data is None or data.empty:
        return out
    for sym in symbols:
        try:
            df = data[sym] if isinstance(data.columns, pd.MultiIndex) else data
            df = df.copy()
            df.columns = [str(c).lower() for c in df.columns]
            df = df[["open", "high", "low", "close", "volume"]].dropna()
            if len(df) >= 30:
                out[sym] = df
        except Exception:
            continue
    return out


def passes_basic_filters(df: pd.DataFrame) -> bool:
    """
    Quick sanity checks before we bother scoring a stock.
    """
    if df is None or len(df) < 30:
        return False

    last_close = float(df["close"].iloc[-1])
    avg_volume = float(df["volume"].iloc[-20:].mean())

    if not (MIN_STOCK_PRICE <= last_close <= MAX_STOCK_PRICE):
        return False
    if avg_volume < MIN_AVG_VOLUME:
        return False

    return True


def run_scan(top_n: int = MAX_POSITIONS * 3) -> list[dict]:
    """
    Full scan pipeline:
    1. Get all tradable symbols from Alpaca
    2. In parallel, download price data and score each stock
    3. Return the top N candidates sorted by composite score

    Args:
        top_n: How many candidates to return (we return more than MAX_POSITIONS
               so the trader can skip any that are already held)

    Returns:
        List of score dicts sorted highest score first
    """
    trading_client = TradingClient(
        ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True
    )

    symbols = get_tradable_symbols(trading_client)
    logger.info(f"Scanning {len(symbols)} symbols...")

    results = []
    errors  = 0
    CHUNK   = 200

    chunks = [symbols[i:i + CHUNK] for i in range(0, len(symbols), CHUNK)]
    for n, chunk in enumerate(chunks, 1):
        frames = fetch_ohlcv_batch(chunk)
        for sym, df in frames.items():
            try:
                if passes_basic_filters(df):
                    r = score_stock(sym, df)
                    if r is not None:
                        results.append(r)
            except Exception as e:
                errors += 1
                logger.debug(f"Error scoring {sym}: {e}")
        logger.info(f"  Progress: {min(n * CHUNK, len(symbols))}/{len(symbols)} scanned, {len(results)} passed filters")
        time.sleep(1)   # be gentle with Yahoo's rate limits

    logger.info(
        f"Scan complete. {len(results)} stocks scored, {errors} errors. "
        f"Top {top_n} candidates selected."
    )

    # Sort by composite score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[:top_n]

    # Log the top candidates
    logger.info("Top candidates:")
    for r in top:
        logger.info(
            f"  {r['symbol']:6s}  score={r['score']:.3f}  "
            f"close=${r['close']:.2f}  "
            f"RSI={r['rsi_score']:.2f}  MACD={r['macd_score']:.2f}  "
            f"MA={r['ma_score']:.2f}  Vol={r['volume_score']:.2f}  "
            f"Mom={r['momentum_score']:.2f}"
        )

    return top
