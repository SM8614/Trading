# =============================================================================
# dashboard.py — Local live activity dashboard (http://localhost:8765)
# =============================================================================
# Started automatically by main.py in a background thread. Read-only: it never
# places or cancels orders. Everything is shown on the $STARTING_CAPITAL basis.

from __future__ import annotations
import json
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

from config import (
    ALPACA_API_KEY, ALPACA_SECRET_KEY, STARTING_CAPITAL, ACCOUNT_BASE,
    LOG_FILE, SCAN_TIME, DAILY_BUYS, MAX_POSITIONS, POSITION_SIZE_USD,
    TARGET_GAIN_PCT, STOP_LOSS_PCT, MAX_HOLD_DAYS,
)

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
BASE = "https://paper-api.alpaca.markets/v2/"
HDRS = {"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY}

# Shared with main.py
BOT = {"started": datetime.now().isoformat(), "next_scan": None, "next_monitor": None,
       "last_monitor": None, "scanning": False}

_cache = {"t": 0, "data": None}
_lock = threading.Lock()


def _get(path):
    r = requests.get(BASE + path, headers=HDRS, timeout=15)
    r.raise_for_status()
    return r.json()


def _alpaca_state():
    with _lock:
        if _cache["data"] and time.time() - _cache["t"] < 10:
            return _cache["data"]
        shift = STARTING_CAPITAL - ACCOUNT_BASE
        a = _get("account")
        pos = _get("positions")
        orders = _get("orders?status=open&nested=true&limit=100")
        fills = _get("account/activities/FILL?page_size=100")
        clock = _get("clock")
        hist_d = _get("account/portfolio/history?period=1A&timeframe=1D")
        hist_i = _get("account/portfolio/history?period=1D&timeframe=5Min")

        def series(h):
            pts = [{"t": t, "v": v + shift} for t, v in zip(h.get("timestamp") or [], h.get("equity") or []) if v]
            i = 0
            while i + 1 < len(pts) and abs(pts[i + 1]["v"] - STARTING_CAPITAL) < 1e-6:
                i += 1
            return pts[i:]

        eq = float(a["equity"]) + shift
        invested = sum(float(p["market_value"]) for p in pos)
        entries = {}
        try:
            with open(os.path.join(HERE, "entries.json")) as f:
                entries = json.load(f)
        except Exception:
            pass

        # Legs of bracket orders: find the take-profit and stop for each symbol
        legs = {}
        for o in orders:
            for leg in [o] + (o.get("legs") or []):
                if leg.get("side") == "sell" and leg.get("status") in ("new", "held", "accepted", "pending_new"):
                    d = legs.setdefault(leg["symbol"], {})
                    if leg.get("type") == "limit":
                        d["target"] = float(leg["limit_price"])
                    elif leg.get("type") in ("stop", "stop_limit"):
                        d["stop"] = float(leg["stop_price"])

        data = {
            "summary": {
                "equity": eq, "start": STARTING_CAPITAL, "total_pl": eq - STARTING_CAPITAL,
                "day_pl": float(a["equity"]) - float(a["last_equity"]),
                "invested": invested, "cash": eq - invested, "positions": len(pos),
            },
            "clock": {"is_open": clock["is_open"], "next_open": clock["next_open"], "next_close": clock["next_close"]},
            "positions": [{
                "symbol": p["symbol"], "qty": float(p["qty"]), "entry": float(p["avg_entry_price"]),
                "price": float(p["current_price"]), "value": float(p["market_value"]),
                "pl": float(p["unrealized_pl"]), "plpc": float(p["unrealized_plpc"]),
                "day_plpc": float(p.get("change_today") or 0),
                "since": entries.get(p["symbol"]), **legs.get(p["symbol"], {}),
            } for p in pos],
            "orders": [{
                "symbol": o["symbol"], "side": o["side"], "type": o["type"], "qty": o.get("qty"),
                "status": o["status"], "submitted": o.get("submitted_at"),
                "limit": o.get("limit_price"), "stop": o.get("stop_price"),
            } for o in orders],
            "fills": [{
                "time": f["transaction_time"], "symbol": f["symbol"], "side": f["side"],
                "qty": float(f["qty"]), "price": float(f["price"]),
            } for f in fills],
            "daily": series(hist_d),
            "intraday": series(hist_i),
        }
        _cache.update(t=time.time(), data=data)
        return data


def _log_tail(n=150):
    try:
        with open(os.path.join(HERE, LOG_FILE), "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 60000))
            lines = f.read().decode("utf-8", "replace").splitlines()[-n:]
        return lines[::-1]
    except Exception:
        return []


def _last_scan():
    try:
        with open(os.path.join(HERE, "last_scan.json")) as f:
            return json.load(f)
    except Exception:
        return None


def state():
    out = {"bot": dict(BOT), "log": _log_tail(), "scan": _last_scan(),
           "settings": {"scan_time": SCAN_TIME, "daily_buys": DAILY_BUYS, "max_positions": MAX_POSITIONS,
                        "position_size": POSITION_SIZE_USD, "target": TARGET_GAIN_PCT,
                        "stop": STOP_LOSS_PCT, "max_hold": MAX_HOLD_DAYS},
           "now": datetime.now().isoformat()}
    try:
        out["alpaca"] = _alpaca_state()
    except Exception as e:
        out["alpaca_error"] = str(e)
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/state"):
            self._send(200, json.dumps(state(), default=str).encode(), "application/json")
        elif self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "dashboard.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")


def start_dashboard():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://localhost:{PORT}"


if __name__ == "__main__":
    print("Dashboard (standalone, no bot status):", start_dashboard())
    while True:
        time.sleep(3600)
