# =============================================================================
# trader.py — Alpaca Paper Trading Engine
# =============================================================================
# Handles buying top candidates and monitoring positions for exit conditions:
#   - Sell at +15% gain (take profit)
#   - Sell at -5% loss (stop loss)

from __future__ import annotations
import logging
import math
import time
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    GetOrdersRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

from config import (
    ALPACA_API_KEY, ALPACA_SECRET_KEY,
    TARGET_GAIN_PCT, STOP_LOSS_PCT,
    MAX_POSITIONS, POSITION_SIZE_USD,
    DAILY_BUYS, MAX_HOLD_DAYS,
    STARTING_CAPITAL, ACCOUNT_BASE,
)
import json, os
from datetime import date
import numpy as np
from alpaca.trading.requests import TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderClass

ENTRY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "entries.json")


def _load_entries() -> dict:
    try:
        with open(ENTRY_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_entries(d: dict):
    with open(ENTRY_FILE, "w") as f:
        json.dump(d, f, indent=2)


def _cancel_open_orders(trading_client, symbol: str):
    """Cancel any open orders (e.g. bracket take-profit/stop legs) for a symbol."""
    try:
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol], nested=True)
        for o in trading_client.get_orders(req):
            try:
                trading_client.cancel_order_by_id(o.id)
            except Exception:
                pass
        time.sleep(2)   # let cancellations settle so shares are free to sell
    except Exception as e:
        logger.warning(f"[{symbol}] Could not cancel open orders: {e}")

logger = logging.getLogger(__name__)


def get_clients():
    trading = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
    data    = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
    return trading, data


def get_current_positions(trading_client: TradingClient) -> dict:
    """
    Returns a dict of {symbol: position_object} for all open positions.
    """
    positions = trading_client.get_all_positions()
    return {p.symbol: p for p in positions}


def get_latest_price(data_client: StockHistoricalDataClient, symbol: str) -> float | None:
    """
    Fetch the latest ask price for a symbol using Alpaca's data API.
    """
    try:
        req    = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        quotes = data_client.get_stock_latest_quote(req)
        q = quotes[symbol]
        ask, bid = float(q.ask_price or 0), float(q.bid_price or 0)
        if ask > 0 and bid > 0:
            return (ask + bid) / 2
        if ask > 0 or bid > 0:
            return ask or bid
        from alpaca.data.requests import StockLatestTradeRequest
        trades = data_client.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbol))
        return float(trades[symbol].price)
    except Exception as e:
        logger.warning(f"[{symbol}] Could not fetch latest price: {e}")
        return None


def buy_stocks(candidates: list[dict]) -> list[str]:
    """
    Place market buy orders for the top candidates, respecting MAX_POSITIONS.

    Args:
        candidates: Sorted list of score dicts from scanner.run_scan()

    Returns:
        List of symbols that were successfully ordered
    """
    trading_client, data_client = get_clients()

    # Check how many positions we already have
    current_positions = get_current_positions(trading_client)
    available_slots   = min(DAILY_BUYS, MAX_POSITIONS - len(current_positions))

    if available_slots <= 0:
        logger.info("All position slots are full. No new buys.")
        return []

    logger.info(
        f"Have {len(current_positions)} open positions. "
        f"Room for {available_slots} more."
    )

    # Virtual $STARTING_CAPITAL budget: starting capital + the bot's P&L, minus what's already invested
    account  = trading_client.get_account()
    budget   = STARTING_CAPITAL + (float(account.equity) - ACCOUNT_BASE)
    invested = sum(float(p.market_value) for p in current_positions.values())
    available_cash = budget - invested
    logger.info(f"Budget ${budget:,.2f}  invested ${invested:,.2f}  available ${available_cash:,.2f}")

    bought = []
    for candidate in candidates:
        if len(bought) >= available_slots:
            break

        symbol = candidate["symbol"]

        # Skip if we already hold this stock
        if symbol in current_positions:
            logger.info(f"[{symbol}] Already holding — skipping.")
            continue

        # Get current price to calculate quantity
        price = get_latest_price(data_client, symbol)
        if price is None or price <= 0:
            logger.warning(f"[{symbol}] Could not get price — skipping.")
            continue

        qty = math.floor(POSITION_SIZE_USD / price)
        if qty < 1:
            logger.info(f"[{symbol}] Price ${price:.2f} too high for ${POSITION_SIZE_USD} budget — skipping.")
            continue

        if qty * price > available_cash:
            logger.info(f"[{symbol}] Not enough budget left (${available_cash:,.2f}) — stopping buys for today.")
            break

        try:
            # Bracket order: Alpaca itself holds the +15% take-profit and -5% stop-loss,
            # so exits happen even if this computer is off.
            order_req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.GTC,
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=round(price * (1 + TARGET_GAIN_PCT), 2)),
                stop_loss=StopLossRequest(stop_price=round(price * (1 - STOP_LOSS_PCT), 2)),
            )
            order = trading_client.submit_order(order_req)
            entries = _load_entries()
            entries[symbol] = date.today().isoformat()
            _save_entries(entries)
            logger.info(
                f"[{symbol}] BUY order placed — {qty} shares @ ~${price:.2f} "
                f"(${qty * price:.2f} total)  score={candidate['score']:.3f}"
            )
            bought.append(symbol)
            available_cash -= qty * price
        except Exception as e:
            logger.error(f"[{symbol}] Failed to place buy order: {e}")

    return bought


def monitor_and_exit() -> list[dict]:
    """
    Check all open positions and sell if:
    - Current price >= entry price * (1 + TARGET_GAIN_PCT)  → Take profit
    - Current price <= entry price * (1 - STOP_LOSS_PCT)    → Stop loss

    Returns:
        List of exit records (symbol, reason, entry, exit_price, pnl_pct)
    """
    trading_client, data_client = get_clients()
    positions = get_current_positions(trading_client)

    if not positions:
        logger.info("No open positions to monitor.")
        return []

    exits = []

    for symbol, position in positions.items():
        entry_price   = float(position.avg_entry_price)
        current_price = get_latest_price(data_client, symbol)

        if current_price is None:
            continue

        pnl_pct = (current_price - entry_price) / entry_price

        take_profit_price = entry_price * (1 + TARGET_GAIN_PCT)
        stop_loss_price   = entry_price * (1 - STOP_LOSS_PCT)

        entries = _load_entries()
        if symbol not in entries:
            entries[symbol] = date.today().isoformat()
            _save_entries(entries)
        held_days = int(np.busday_count(entries[symbol], date.today().isoformat()))

        reason = None
        if current_price >= take_profit_price:
            reason = "TAKE_PROFIT"
        elif current_price <= stop_loss_price:
            reason = "STOP_LOSS"
        elif held_days >= MAX_HOLD_DAYS:
            reason = "MAX_HOLD"

        if reason:
            qty = int(float(position.qty))
            _cancel_open_orders(trading_client, symbol)
            try:
                order_req = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                )
                trading_client.submit_order(order_req)
                logger.info(
                    f"[{symbol}] SELL ({reason}) — {qty} shares  "
                    f"entry=${entry_price:.2f}  current=${current_price:.2f}  "
                    f"P&L={pnl_pct:+.1%}"
                )
                exits.append({
                    "symbol":        symbol,
                    "reason":        reason,
                    "entry_price":   entry_price,
                    "exit_price":    current_price,
                    "pnl_pct":       round(pnl_pct, 4),
                    "qty":           qty,
                })
                entries.pop(symbol, None)
                _save_entries(entries)
            except Exception as e:
                logger.error(f"[{symbol}] Failed to place sell order: {e}")
        else:
            logger.info(
                f"[{symbol}] Holding — entry=${entry_price:.2f}  "
                f"current=${current_price:.2f}  P&L={pnl_pct:+.1%}  "
                f"target=${take_profit_price:.2f}  stop=${stop_loss_price:.2f}"
            )

    return exits


def print_portfolio_summary():
    """Print a summary of the current portfolio state."""
    trading_client, data_client = get_clients()

    try:
        account   = trading_client.get_account()
        positions = get_current_positions(trading_client)

        logger.info("=" * 60)
        logger.info("PORTFOLIO SUMMARY")
        logger.info(f"  Cash:            ${float(account.cash):>12,.2f}")
        logger.info(f"  Portfolio value: ${float(account.portfolio_value):>12,.2f}")
        logger.info(f"  Open positions:  {len(positions)}")

        if positions:
            logger.info("  Positions:")
            for symbol, pos in positions.items():
                entry   = float(pos.avg_entry_price)
                mkt_val = float(pos.market_value)
                unr_pnl = float(pos.unrealized_pl)
                pnl_pct = float(pos.unrealized_plpc) * 100
                logger.info(
                    f"    {symbol:6s}  entry=${entry:.2f}  "
                    f"mkt=${mkt_val:,.2f}  "
                    f"P&L=${unr_pnl:+,.2f} ({pnl_pct:+.1f}%)"
                )
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"Could not fetch portfolio summary: {e}")
