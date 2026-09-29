"""
Alpaca Paper Trading Integration
─────────────────────────────────
Uses Alpaca's free paper trading API to:
  • Check account balance & positions
  • Place market buy orders
  • Place limit/trailing-stop sell orders (to capture the 15% target)
  • Cancel open orders
  • Track trade history

Set your keys in config.py or pass them directly.
Sign up free at https://alpaca.markets (Paper Trading — no real money).
"""

from __future__ import annotations
import requests
import json
from datetime import datetime
from typing import Optional


class AlpacaTrader:
    """
    Thin wrapper around Alpaca REST API v2.
    Works with Paper Trading keys (base URL: paper-api.alpaca.markets).
    """

    PAPER_BASE = "https://paper-api.alpaca.markets/v2"
    DATA_BASE  = "https://data.alpaca.markets/v2"

    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        self.api_key    = api_key
        self.secret_key = secret_key
        self.base_url   = self.PAPER_BASE if paper else "https://api.alpaca.markets/v2"
        self.headers    = {
            "APCA-API-KEY-ID":     api_key,
            "APCA-API-SECRET-KEY": secret_key,
            "Content-Type":        "application/json",
        }

    # ── Helpers ────────────────────────────────────────────────────────────

    def _get(self, endpoint: str, params: dict = None) -> dict:
        url = f"{self.base_url}/{endpoint}"
        r = requests.get(url, headers=self.headers, params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def _post(self, endpoint: str, body: dict) -> dict:
        url = f"{self.base_url}/{endpoint}"
        r = requests.post(url, headers=self.headers, data=json.dumps(body), timeout=10)
        r.raise_for_status()
        return r.json()

    def _delete(self, endpoint: str) -> int:
        url = f"{self.base_url}/{endpoint}"
        r = requests.delete(url, headers=self.headers, timeout=10)
        return r.status_code

    # ── Account ────────────────────────────────────────────────────────────

    def get_account(self) -> dict:
        """Return account info: cash, portfolio value, buying power, etc."""
        return self._get("account")

    def get_buying_power(self) -> float:
        acct = self.get_account()
        return float(acct.get("buying_power", 0))

    def get_portfolio_value(self) -> float:
        acct = self.get_account()
        return float(acct.get("portfolio_value", 0))

    def account_summary(self) -> dict:
        acct = self.get_account()
        return {
            "status":          acct.get("status"),
            "cash":            float(acct.get("cash", 0)),
            "buying_power":    float(acct.get("buying_power", 0)),
            "portfolio_value": float(acct.get("portfolio_value", 0)),
            "equity":          float(acct.get("equity", 0)),
            "day_trade_count": int(acct.get("daytrade_count", 0)),
            "currency":        acct.get("currency", "USD"),
        }

    # ── Positions ──────────────────────────────────────────────────────────

    def get_positions(self) -> list[dict]:
        """Return all open positions."""
        raw = self._get("positions")
        positions = []
        for p in raw:
            entry = float(p.get("avg_entry_price", 0))
            current = float(p.get("current_price", 0))
            gain_pct = ((current - entry) / entry * 100) if entry else 0
            positions.append({
                "ticker":       p["symbol"],
                "qty":          float(p["qty"]),
                "entry_price":  entry,
                "current_price": current,
                "market_value": float(p.get("market_value", 0)),
                "unrealized_pl": float(p.get("unrealized_pl", 0)),
                "gain_pct":     round(gain_pct, 2),
                "side":         p.get("side", "long"),
            })
        return positions

    def get_position(self, ticker: str) -> Optional[dict]:
        """Return a single position, or None if not held."""
        try:
            p = self._get(f"positions/{ticker}")
            entry = float(p.get("avg_entry_price", 0))
            current = float(p.get("current_price", 0))
            gain_pct = ((current - entry) / entry * 100) if entry else 0
            return {
                "ticker":       p["symbol"],
                "qty":          float(p["qty"]),
                "entry_price":  entry,
                "current_price": current,
                "market_value": float(p.get("market_value", 0)),
                "unrealized_pl": float(p.get("unrealized_pl", 0)),
                "gain_pct":     round(gain_pct, 2),
            }
        except Exception:
            return None

    # ── Orders ─────────────────────────────────────────────────────────────

    def get_orders(self, status: str = "open") -> list[dict]:
        """Return orders filtered by status: open | closed | all."""
        raw = self._get("orders", {"status": status, "limit": 50})
        return [
            {
                "id":        o["id"],
                "ticker":    o["symbol"],
                "side":      o["side"],
                "qty":       o.get("qty"),
                "type":      o["type"],
                "status":    o["status"],
                "filled_at": o.get("filled_at"),
                "filled_avg_price": o.get("filled_avg_price"),
                "limit_price": o.get("limit_price"),
                "submitted_at": o.get("submitted_at"),
            }
            for o in raw
        ]

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a specific order. Returns True on success."""
        status = self._delete(f"orders/{order_id}")
        return status in (200, 204)

    def cancel_all_orders(self) -> int:
        """Cancel all open orders. Returns HTTP status code."""
        return self._delete("orders")

    # ── Trading ────────────────────────────────────────────────────────────

    def buy_market(self, ticker: str, qty: float = None,
                   notional: float = None) -> dict:
        """
        Place a market buy order.
        Specify either qty (shares) or notional (dollar amount).
        """
        if qty is None and notional is None:
            raise ValueError("Specify either qty or notional.")

        body = {
            "symbol":        ticker,
            "side":          "buy",
            "type":          "market",
            "time_in_force": "day",
        }
        if qty is not None:
            body["qty"] = str(qty)
        else:
            body["notional"] = str(round(notional, 2))

        result = self._post("orders", body)
        return {
            "order_id": result.get("id"),
            "ticker":   result.get("symbol"),
            "side":     result.get("side"),
            "qty":      result.get("qty"),
            "notional": result.get("notional"),
            "status":   result.get("status"),
            "type":     result.get("type"),
        }

    def sell_limit(self, ticker: str, qty: float, limit_price: float) -> dict:
        """Place a limit sell order (GTC — Good Till Cancelled)."""
        body = {
            "symbol":        ticker,
            "side":          "sell",
            "type":          "limit",
            "time_in_force": "gtc",
            "qty":           str(qty),
            "limit_price":   str(round(limit_price, 2)),
        }
        result = self._post("orders", body)
        return {
            "order_id":    result.get("id"),
            "ticker":      result.get("symbol"),
            "limit_price": result.get("limit_price"),
            "qty":         result.get("qty"),
            "status":      result.get("status"),
        }

    def sell_trailing_stop(self, ticker: str, qty: float,
                           trail_percent: float = 5.0) -> dict:
        """
        Place a trailing stop sell order.
        trail_percent: how far below peak price to trigger the stop.
        """
        body = {
            "symbol":        ticker,
            "side":          "sell",
            "type":          "trailing_stop",
            "time_in_force": "gtc",
            "qty":           str(qty),
            "trail_percent": str(trail_percent),
        }
        result = self._post("orders", body)
        return {
            "order_id":      result.get("id"),
            "ticker":        result.get("symbol"),
            "trail_percent": result.get("trail_percent"),
            "qty":           result.get("qty"),
            "status":        result.get("status"),
        }

    def sell_market(self, ticker: str, qty: float) -> dict:
        """Place an immediate market sell order."""
        body = {
            "symbol":        ticker,
            "side":          "sell",
            "type":          "market",
            "time_in_force": "day",
            "qty":           str(qty),
        }
        result = self._post("orders", body)
        return {
            "order_id": result.get("id"),
            "ticker":   result.get("symbol"),
            "status":   result.get("status"),
        }

    # ── Strategy: Buy + auto-set 15% profit target ──────────────────────────

    def buy_with_profit_target(self, ticker: str, notional: float,
                                target_pct: float = 15.0,
                                trail_stop_pct: float = 5.0) -> dict:
        """
        Full strategy execution:
        1. Buy `notional` dollars worth of `ticker` at market.
        2. Place a limit sell order at entry + target_pct%.
        3. Optionally place a trailing stop as a loss-protection hedge.

        Returns a summary dict with both order IDs.
        """
        # Step 1: Buy
        buy_order = self.buy_market(ticker, notional=notional)

        # We don't know the exact fill price yet (market order fills async),
        # so we get the last known price to estimate target
        try:
            pos = self.get_position(ticker)
            entry = pos["entry_price"] if pos else None
        except Exception:
            entry = None

        # Fall back: get latest quote from Alpaca data API
        if not entry:
            try:
                r = requests.get(
                    f"{self.DATA_BASE}/stocks/{ticker}/trades/latest",
                    headers=self.headers, timeout=5
                )
                entry = float(r.json()["trade"]["p"])
            except Exception:
                entry = None

        sell_order = None
        if entry and entry > 0:
            target_price = round(entry * (1 + target_pct / 100), 2)
            estimated_qty = round(notional / entry, 4)
            try:
                sell_order = self.sell_limit(ticker, estimated_qty, target_price)
            except Exception as e:
                sell_order = {"error": str(e)}

        return {
            "strategy":       f"Buy → Sell at +{target_pct}%",
            "ticker":         ticker,
            "invested":       notional,
            "buy_order":      buy_order,
            "estimated_entry": entry,
            "target_price":   round(entry * (1 + target_pct / 100), 2) if entry else None,
            "sell_order":     sell_order,
            "timestamp":      datetime.now().isoformat(),
        }

    # ── Latest price ───────────────────────────────────────────────────────

    def get_latest_price(self, ticker: str) -> Optional[float]:
        """Fetch the latest trade price from Alpaca data API."""
        try:
            r = requests.get(
                f"{self.DATA_BASE}/stocks/{ticker}/trades/latest",
                headers=self.headers, timeout=5
            )
            return float(r.json()["trade"]["p"])
        except Exception:
            return None
