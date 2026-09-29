# Architecture

This document explains how the pieces of Algo fit together: processes and threads, modules, data flow, files on disk, and the external services it talks to.

---

## 1. Big picture

```
                         ┌──────────────────────────── your computer ─────────────────────────────┐
                         │                                                                          │
  start.command ───────► │  python main.py  (one process)                                           │
                         │  ├─ main thread: `schedule` loop (checks every 10 s)                     │
                         │  │    ├─ 09:31 ET  job_morning_summary ──► trader.print_portfolio_summary│
                         │  │    ├─ every 5 min job_monitor_positions ──► trader.monitor_and_exit   │
                         │  │    └─ every 1 min job_scan_check ─► (due?) job_scan_and_buy ─► scanner│
                         │  │                                       └──► trader.buy_stocks          │
                         │  └─ daemon thread: dashboard HTTP server on 127.0.0.1:8765               │
                         │         GET /            → dashboard.html (Algo Desk)                    │
                         │         GET /api/state   → JSON (Alpaca data + bot status + log)         │
                         │                                                                          │
                         │  files: trader.log · entries.json · last_scan.json                       │
                         └───────────────┬───────────────────────────────┬──────────────────────────┘
                                         │ HTTPS                         │ HTTPS
                          ┌──────────────▼─────────────┐   ┌─────────────▼──────────────┐
                          │ Alpaca paper trading API   │   │ Yahoo Finance (yfinance)   │
                          │ assets, orders, positions, │   │ daily OHLCV price history  │
                          │ account, clock, quotes     │   │ for the scan               │
                          └────────────────────────────┘   └────────────────────────────┘
```

Optionally, a cloud scheduled task runs [`tools/pnl_snapshot.py`](../tools/pnl_snapshot.py) after each close and publishes the numbers to an online P&L page (see [DASHBOARD.md](DASHBOARD.md#online-pl-page)). It is independent of the bot process and read-only.

---

## 2. Modules

### `main.py` — orchestrator
- Configures logging to both `trader.log` and the terminal.
- `is_market_open()` asks Alpaca's `/v2/clock` (so holidays and early closes are respected) and falls back to Mon–Fri 9:30–16:00 ET if Alpaca can't be reached.
- Registers three jobs with the [`schedule`](https://schedule.readthedocs.io) library. Times are pinned to `America/New_York`, so the bot behaves the same whatever the computer's time zone.

  | Job | Schedule | Does |
  |-----|----------|------|
  | `job_scan_check` | every minute | decides whether a scan is due (today's, or a missed one) and runs `job_scan_and_buy` → `run_scan()` → `buy_stocks()` → writes `last_scan.json` and `scan_state.json` |
  | `job_monitor_positions` | every `MONITOR_INTERVAL_SEC` | skips if market closed → `monitor_and_exit()` |
  | `job_morning_summary` | daily 09:31 ET | logs cash, value and positions |

- Starts the dashboard server, then runs one monitor pass, a portfolio summary and a scan check immediately at start-up.

#### Catch-up scheduling
A fixed "run at 15:20" timer is silently skipped when the computer is off or asleep, so the scan is driven by state instead:

1. `_trading_days()` loads Alpaca's trading calendar (±14 days, cached per day), which includes holidays and early closes.
2. The scan moment for a trading day is `SCAN_TIME`, or 40 minutes before an early close, whichever is earlier.
3. `due_scan_day()` = the most recent trading day whose scan moment has passed.
4. `scan_state.json` stores `last_scan_for`, the trading day the last *completed* scan covered.
5. Every minute, if `due_scan_day() > last_scan_for` and the market is open with at least 15 minutes left before the close, the scan runs and `last_scan_for` is updated. If the market is closed, the scan stays pending until the next open.

Consequences: a missed day is caught up once (several missed days collapse into one scan); today's regular scan still runs later the same day; a failed scan is retried after 10 minutes; on the very first run the state starts at the latest due day, so installing the bot never triggers a surprise catch-up.
- Main loop: publishes `next_scan` / `next_monitor` to the dashboard's shared `BOT` dict, calls `schedule.run_pending()`, sleeps 10 s.

### `scanner.py` — market scan
1. `get_tradable_symbols()` — all Alpaca assets that are `active`, `tradable`, `us_equity`, listed on NYSE, NASDAQ or ARCA, and whose symbol has no `.` or `/` (skips share classes like `BRK.B` and odd listings). Roughly 10,000 symbols.
2. `fetch_ohlcv_batch()` — one `yfinance.download()` call per chunk of **200** symbols, `group_by="ticker"`, ~100 calendar days (≈68 trading days) ending *tomorrow* so today's partial bar is included. Normalises columns to `open/high/low/close/volume` and keeps symbols with ≥30 rows.
3. `passes_basic_filters()` — last close within `[MIN_STOCK_PRICE, MAX_STOCK_PRICE]` and 20-day average volume ≥ `MIN_AVG_VOLUME`.
4. `signals.score_stock()` on every survivor.
5. Sorts by composite score and returns the top `MAX_POSITIONS × 3` candidates (extra so already-held names can be skipped).

A 1-second pause between chunks keeps Yahoo's rate limiter happy.

### `signals.py` — scoring
Five independent indicator functions, each returning 0–1, combined with the weights from `config.py`. Full scoring tables are in [STRATEGY.md](STRATEGY.md#3-the-five-signals).

### `trader.py` — orders and exits
- `get_latest_price()` — mid-point of bid/ask from Alpaca's latest quote; falls back to whichever side is non-zero, then to the latest trade price.
- `buy_stocks()` — computes available slots (`min(DAILY_BUYS, MAX_POSITIONS − open)`), computes the **virtual budget** (see STRATEGY.md), and submits **bracket** market orders (`time_in_force=GTC`) with a take-profit limit at `price × (1 + TARGET_GAIN_PCT)` and a stop at `price × (1 − STOP_LOSS_PCT)`. Records the buy date in `entries.json`.
- `monitor_and_exit()` — for each open position computes P&L, trading days held (`numpy.busday_count`), and sells at market if the target, stop, or `MAX_HOLD_DAYS` is reached. Before selling it cancels the position's open bracket legs (otherwise Alpaca would reject the sell because the shares are reserved) and waits 2 s for the cancellations to settle.
- `print_portfolio_summary()` — logs cash, value and each position.

### `dashboard.py` — local UI server
- `ThreadingHTTPServer` bound to `127.0.0.1:8765`, started as a daemon thread by `main.py` (or standalone with `python dashboard.py`).
- `/api/state` merges: live Alpaca data (account, positions, open orders with nested bracket legs, last 100 fills, market clock, daily and 5-minute equity history), bot status from the shared `BOT` dict, the last 150 lines of `trader.log`, `last_scan.json`, and the active settings. Alpaca responses are cached for 10 s so several open tabs don't multiply API calls.
- All money figures are shifted onto the `STARTING_CAPITAL` basis.
- Uses plain `requests` against the REST API and never calls an order-placing endpoint.

### `dashboard.html` — Algo Desk
Single self-contained page (vanilla JS, inline SVG chart, Google Fonts). Polls `/api/state` every 15 s. See [DASHBOARD.md](DASHBOARD.md).

### `config.py`
Every tunable parameter. Loads API keys from `local_settings.py` or environment variables. See [CONFIGURATION.md](CONFIGURATION.md).

---

## 3. Files written at runtime

| File | Written by | Purpose |
|------|-----------|---------|
| `trader.log` | `logging` in `main.py` | Complete history of scans, orders, exits and errors. Append-only. |
| `entries.json` | `trader.py` | `{symbol: "YYYY-MM-DD"}` buy date per open position, used for the max-hold rule. Entries are removed when the bot sells. Positions found without an entry are stamped with today's date. |
| `last_scan.json` | `main.py` | `{time, candidates:[…score dicts…], bought:[symbols]}` from the latest scan, shown on the dashboard. |
| `scan_state.json` | `main.py` | `{last_scan_for: "YYYY-MM-DD"}` — trading day of the last completed scan; drives catch-up. Delete it to reset tracking. |
| `.venv/` | `start.command` | Python virtual environment. |

All are git-ignored.

---

## 4. External services

| Service | Used for | Auth | Notes |
|---------|----------|------|-------|
| Alpaca Trading API (paper) `paper-api.alpaca.markets` | assets, account, clock, positions, orders, activities, portfolio history | API key + secret headers | Paper endpoint is hard-coded (`paper=True`). |
| Alpaca Market Data `data.alpaca.markets` | latest quote / trade for sizing and exits | same keys | Free plan uses the IEX feed. |
| Yahoo Finance via `yfinance` | daily OHLCV for the scan | none | Unofficial API; can rate-limit or change format. |
| Google Fonts | dashboard typography | none | Page falls back to system fonts offline. |

---

## 5. Concurrency and failure behaviour

- Jobs run sequentially on the main thread; a long scan delays the next monitor pass rather than overlapping it.
- Sleep and wake: the process is frozen while the Mac sleeps; on wake the next minute's scan check notices a missed scan and catches up.
- Every job is wrapped in `try/except` and logs the error with a traceback, so one failure never stops the scheduler.
- Exits placed as bracket legs live on Alpaca's servers, so +15% / −5% protection continues when the bot or the computer is off. Only the scan/buy step and the 10-day rule need the bot running.
- If the process dies, `start.command` keeps the Terminal window open and prints "The bot has stopped" under the traceback.
