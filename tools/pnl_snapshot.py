#!/usr/bin/env python3
"""
tools/pnl_snapshot.py — one-shot, read-only P&L snapshot of the Alpaca paper account.

Prints a JSON document with four sections (summary, equity, positions, trades),
expressed on the bot's virtual STARTING_CAPITAL basis rather than the raw
Alpaca balance. This is the script the daily "Algo P&L dashboard refresh"
scheduled task runs to feed the online P&L page.

Usage:
    python3 tools/pnl_snapshot.py KEY SECRET > snap.json
    # or, with ALPACA_API_KEY / ALPACA_SECRET_KEY set in the environment:
    python3 tools/pnl_snapshot.py > snap.json

Standard library only, so it runs anywhere Python 3.8+ is available.
It never places, changes or cancels orders.
"""
import datetime
import json
import os
import sys
import urllib.request

BASE_URL = "https://paper-api.alpaca.markets/v2/"
ACCOUNT_BASE = 100000.0     # Alpaca paper account's real starting balance
START = 10000.0             # The bot's virtual budget (config.STARTING_CAPITAL)

if len(sys.argv) >= 3:
    KEY, SECRET = sys.argv[1], sys.argv[2]
else:
    KEY, SECRET = os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"]


def get(path):
    req = urllib.request.Request(BASE_URL + path, headers={"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SECRET})
    return json.load(urllib.request.urlopen(req, timeout=20))


account = get("account")
history = get("account/portfolio/history?period=1A&timeframe=1D")
positions = get("positions")
fills = get("account/activities/FILL?page_size=100")

points = [{"t": datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"), "v": v}
          for t, v in zip(history.get("timestamp") or [], history.get("equity") or []) if v]
i = 0
while i + 1 < len(points) and points[i + 1]["v"] == ACCOUNT_BASE:   # drop the flat pre-bot stretch
    i += 1
points = [{"t": p["t"], "v": p["v"] - ACCOUNT_BASE + START} for p in points[i:]]

equity = float(account["equity"]) - ACCOUNT_BASE + START
last_equity = float(account["last_equity"]) - ACCOUNT_BASE + START
invested = sum(float(p["market_value"]) for p in positions)

print(json.dumps({
    "summary": {"equity": equity, "cash": equity - invested, "start": START,
                "total_pl": equity - START, "day_pl": equity - last_equity,
                "positions": len(positions),
                "updatedAt": datetime.datetime.utcnow().isoformat() + "Z"},
    "equity": {"points": points},
    "positions": {"items": [{"symbol": p["symbol"], "qty": float(p["qty"]),
                             "entry": float(p["avg_entry_price"]), "price": float(p["current_price"]),
                             "value": float(p["market_value"]), "pl": float(p["unrealized_pl"]),
                             "plpc": float(p["unrealized_plpc"])} for p in positions]},
    "trades": {"items": [{"time": f["transaction_time"], "symbol": f["symbol"], "side": f["side"],
                          "qty": float(f["qty"]), "price": float(f["price"])} for f in fills]},
}))
