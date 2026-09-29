# Dashboards

Algo has two ways to watch it:

| | **Algo Desk** (local) | **Online P&L page** (optional) |
|---|---|---|
| Where | `http://localhost:8765` on the computer running the bot | a private claude.ai page, any device |
| Updates | live, every 15 s | once per trading day after the close |
| Shows | everything: status, P&L, holdings, scan, trades, orders, log | P&L, account value, holdings, fills |
| Needs the bot running | yes | no |

---

## Algo Desk

Served by [`dashboard.py`](../dashboard.py) from inside the bot process and opened automatically by `start.command` once the server responds. Read-only: it cannot place, change or cancel orders.

### Layout

1. **Status strip**
   - **Theme switch** — *Auto* (follows the operating system), *Light*, *Dark*. Saved in the browser's `localStorage` under `algo-theme`.
   - **Bot** — green *Bot running*; amber, pulsing *Scanning stocks…* during the daily scan; red *Bot not running* if the page can't reach the server.
   - **Market** — open, or closed with the next opening time.
   - **Next scan in …** — countdown to `SCAN_TIME`.
   - **Updated** — time of the last successful refresh.
   - A red banner appears if Alpaca can't be reached (network or key problem).
2. **Profit since start** — total P&L in dollars and percent against `STARTING_CAPITAL`, today's P&L, account value, starting amount, invested, free cash, and a one-line summary of the active rules.
3. **Account value chart** — *Today* (5-minute points) or *All days* (daily closes). The dashed line marks the starting amount; the line is green above it and red below.
4. **Holdings** — per position: shares, buy price, current price, today's change, P&L in $ and %, a **stop → target bar** (the left 25% is the loss zone down to −5%, the rest the gain zone up to +15%; the black tick is the current price; hover to see exact stop and target prices), and trading days held out of `MAX_HOLD_DAYS`.
5. **Latest scan** — the top 15 candidates from `last_scan.json` with score, a score bar, closing price and a *Bought* tag.
6. **Activity** — three tabs:
   - *Trades*: the last 100 fills from Alpaca (buy/sell, symbol, shares, price, total).
   - *Open orders*: including the take-profit and stop legs waiting on Alpaca.
   - *Bot log*: the newest 150 lines of `trader.log`, with buys, sells, warnings and errors coloured.

### Opening it later
Visit <http://localhost:8765> in any browser on the same computer while the bot is running. To view it without the bot (no bot status, but live Alpaca data), run:
```bash
.venv/bin/python dashboard.py
```

### JSON API

`GET /api/state` returns:

```jsonc
{
  "now": "2026-09-29T10:15:00",
  "bot": {
    "started": "…", "scanning": false,
    "next_scan": "2026-09-29T15:20:00",      // local time of the computer
    "next_monitor": "…", "last_monitor": "…"
  },
  "settings": { "scan_time": "15:20", "daily_buys": 3, "max_positions": 10,
                "position_size": 1000, "target": 0.15, "stop": 0.05, "max_hold": 10 },
  "alpaca": {
    "summary":  { "equity": 10180.5, "start": 10000, "total_pl": 180.5, "day_pl": -22.1,
                  "invested": 3100.0, "cash": 7080.5, "positions": 3 },
    "clock":    { "is_open": true, "next_open": "…", "next_close": "…" },
    "positions":[ { "symbol": "INTC", "qty": 8, "entry": 123.0, "price": 131.2, "value": 1049.6,
                    "pl": 65.6, "plpc": 0.0667, "day_plpc": 0.012, "since": "2026-09-22",
                    "target": 141.45, "stop": 116.85 } ],
    "orders":   [ { "symbol": "INTC", "side": "sell", "type": "limit", "qty": "8",
                    "status": "held", "submitted": "…", "limit": "141.45", "stop": null } ],
    "fills":    [ { "time": "…", "symbol": "PLTR", "side": "buy", "qty": 5, "price": 189.67 } ],
    "daily":    [ { "t": 1790000000, "v": 10012.3 } ],   // unix seconds, virtual value
    "intraday": [ { "t": 1790000000, "v": 10012.3 } ]
  },
  "alpaca_error": "…",            // present only when Alpaca calls failed
  "scan": { "time": "…", "candidates": [ { "symbol": "…", "score": 0.78, "close": 12.3, "…": "…" } ],
            "bought": ["…"] },
  "log": ["2026-09-29 10:15:00  INFO  …", "…"]   // newest first
}
```

All money values are on the virtual `STARTING_CAPITAL` basis. Alpaca data is cached for 10 s.

### Customising
- Colours and fonts are CSS custom properties at the top of `dashboard.html` (`:root` for light, the `[data-theme="dark"]` / `prefers-color-scheme` blocks for dark).
- Refresh interval: `setInterval(tick, 15000)` at the bottom of the file.
- Changes to `dashboard.html` apply on page reload; changes to `dashboard.py` need a bot restart.

---

## Online P&L page

An optional private web page ("Algo Paper P&L") that you can open from a phone. A cloud scheduled task runs every weekday at 4:17 PM ET:

1. runs the same code as [`tools/pnl_snapshot.py`](../tools/pnl_snapshot.py) (embedded in the task) with the Alpaca keys (read-only calls: account, portfolio history, positions, fills);
2. writes the result into the page's data store (`summary`, `equity`, `positions`, `trades`);
3. sends a one-line push notification with the day's P&L.

It uses the same `$10,000` basis as the bot (constants `ACCOUNT_BASE` and `START` at the top of the script). If you change `STARTING_CAPITAL` or your API keys, the scheduled task's instructions must be updated too.

Run the snapshot yourself:
```bash
ALPACA_API_KEY=PK... ALPACA_SECRET_KEY=... python3 tools/pnl_snapshot.py | python3 -m json.tool
```
