# Algo — Stock Scanner & Paper Trader

An automated, **paper-money** stock-trading bot for US equities. Every trading day it scans the whole US stock market, scores each stock with five technical signals, buys the top picks through [Alpaca](https://alpaca.markets)'s paper-trading API, and sells them automatically at a profit target, a stop-loss, or after a maximum holding period. A live local dashboard (**Algo Desk**) shows everything the bot is doing.

> **No real money is involved.** All orders go to Alpaca's *paper* (simulated) endpoint. Nothing in this repository is financial advice, and the strategy has not been back-tested. Treat it as an experiment.

---

## Table of contents

- [What it does, in one minute](#what-it-does-in-one-minute)
- [Quick start (macOS)](#quick-start-macos)
- [Quick start (any OS, manual)](#quick-start-any-os-manual)
- [Daily timeline](#daily-timeline)
- [Project layout](#project-layout)
- [Configuration at a glance](#configuration-at-a-glance)
- [The live dashboard](#the-live-dashboard)
- [Security: where your API keys live](#security-where-your-api-keys-live)
- [Further documentation](#further-documentation)
- [Disclaimer](#disclaimer)

---

## What it does, in one minute

| Step | When (US Eastern) | What happens |
|------|-------------------|--------------|
| **Scan** | 3:20 PM every trading day | Downloads ~100 days of daily prices for every tradable US stock on NYSE / NASDAQ / ARCA (≈10,000 symbols) in batches of 200, drops anything under $5, over $500, or trading under 500k shares/day, and scores the rest from 0 to 1. |
| **Buy** | Right after the scan | Buys the top **3** scorers (skipping ones already held) at **$1,000** each, as long as there is budget left and fewer than **10** positions are open. Each buy is a **bracket order**: Alpaca itself holds a +15% take-profit and a −5% stop-loss for it. |
| **Exit** | Continuously (Alpaca) + every 5 min (bot) | Alpaca sells at +15% or −5% on its own, even if your computer is off. The bot additionally checks every 5 minutes during market hours and sells any position held **10 trading days**. |
| **Catch up** | Whenever the bot comes back | If the computer was off or asleep at 3:20 PM, the missed scan runs as soon as the bot is running again and the market is open (several missed days → one catch-up scan). |
| **Track** | Always | The **Algo Desk** dashboard at `http://localhost:8765` shows profit, holdings, the latest scan, trades, open orders and the bot log, refreshing every 15 seconds. |

The bot trades a **virtual $10,000 budget** inside the Alpaca paper account (which starts at $100,000). Profit is measured against that $10,000. See [docs/STRATEGY.md](docs/STRATEGY.md#the-virtual-10000-budget).

---

## Quick start (macOS)

1. **Create a free Alpaca account** at <https://alpaca.markets>, switch to **Paper Trading**, open **API Keys** and click **Generate**. Copy the *Key* and *Secret*.
2. **Clone this repo**
   ```bash
   git clone https://github.com/SM8614/Trading.git
   cd Trading
   ```
3. **Add your keys** (this file is git-ignored):
   ```bash
   cp local_settings.example.py local_settings.py
   open -e local_settings.py        # paste your Key and Secret, save
   ```
4. **Double-click `start.command`** in Finder (first time: right-click → Open to get past Gatekeeper).
   - First run creates a `.venv` and installs dependencies (~1 minute).
   - The bot starts, keeps the Mac awake with `caffeinate`, and opens **Algo Desk** in your browser.
5. **Leave the Terminal window open.** Closing it (or pressing Ctrl+C) stops the bot. Exits that are already placed with Alpaca keep working regardless.
6. **Optional — start automatically:** double-click `install_autostart.command` once. The bot then launches every time you log in, and can optionally wake the Mac at 3:05 PM on weekdays. Undo with `uninstall_autostart.command`. See [docs/OPERATIONS.md](docs/OPERATIONS.md#3-starting-automatically-and-catching-up).

## Quick start (any OS, manual)

```bash
git clone https://github.com/SM8614/Trading.git && cd Trading
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp local_settings.example.py local_settings.py   # then edit it
python main.py                       # dashboard: http://localhost:8765
```

Requires **Python 3.9 or newer**. Alternatively, skip `local_settings.py` and export `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` as environment variables.

---

## Daily timeline

```
 9:30 ET  market opens ─┬─ portfolio summary logged (9:31)
                        └─ every 5 min: check positions → sell if +15% / −5% / 10 days held
15:20 ET  daily scan  ──── score ~10,000 stocks (≈5–20 min) → buy top 3 as bracket orders
          (missed because the computer was off? → runs at the next moment the bot is up and the market is open)
16:00 ET  market close
16:17 ET  (optional cloud task) refresh the online P&L page
```

Weekends and market holidays are skipped automatically (the bot asks Alpaca's market clock).

---

## Project layout

```
.
├── main.py                    # Entry point: scheduler, jobs, starts the dashboard
├── scanner.py                 # Market-wide scan: symbol list, batch price download, filters, ranking
├── signals.py                 # The five technical indicators and the composite score
├── trader.py                  # Orders: bracket buys, budget logic, exits, portfolio summary
├── dashboard.py               # Local HTTP server + JSON API for Algo Desk (read-only)
├── dashboard.html             # Algo Desk single-page UI (light / dark / auto theme)
├── config.py                  # All tunable settings (no secrets)
├── local_settings.example.py  # Template for your private API keys
├── start.command              # macOS double-click launcher
├── install_autostart.command  # start the bot at every login (+ optional weekday wake)
├── uninstall_autostart.command
├── requirements.txt
├── tools/
│   └── pnl_snapshot.py        # Read-only P&L snapshot used by the online P&L page
├── docs/                      # Detailed documentation (see below)
└── legacy/                    # Earlier prototype, not used by the bot
```

Files the bot creates at runtime (all git-ignored): `trader.log`, `entries.json` (buy date per position), `last_scan.json` (latest scan results), `scan_state.json` (last trading day scanned, for catch-up), `.venv/`.

---

## Configuration at a glance

All settings live in [`config.py`](config.py). The most important:

| Setting | Default | Meaning |
|---------|---------|---------|
| `STARTING_CAPITAL` | `10000` | Virtual budget the bot trades with |
| `DAILY_BUYS` | `3` | New stocks bought per trading day |
| `POSITION_SIZE_USD` | `1000` | Dollars per purchase |
| `MAX_POSITIONS` | `10` | Maximum open positions |
| `TARGET_GAIN_PCT` | `0.15` | Take-profit at +15% |
| `STOP_LOSS_PCT` | `0.05` | Stop-loss at −5% |
| `MAX_HOLD_DAYS` | `10` | Sell after this many trading days |
| `SCAN_TIME` | `"15:20"` | Daily scan time, US Eastern |

Every setting is explained in [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

---

## The live dashboard

**Algo Desk** runs inside the bot process and opens automatically at <http://localhost:8765>:

- status chips — bot running / scanning, market open or closed, countdown to the next scan
- profit since start, today's change, account value, invested vs. free cash
- account value chart (today in 5-minute steps, or all days)
- holdings with a stop → target bar and days held
- latest scan results with which picks were bought
- activity feed: trades, open orders, bot log
- Auto / Light / Dark theme switch (remembered per browser)

Details and the JSON API: [docs/DASHBOARD.md](docs/DASHBOARD.md).

---

## Security: where your API keys live

- Keys are read from **`local_settings.py`** (git-ignored) or from the **environment**. `config.py` contains no secrets.
- `.gitignore` also excludes logs, runtime state, the virtualenv and local backups.
- The dashboard binds to `127.0.0.1` only, so it is not reachable from other machines, and it cannot place or cancel orders.
- If a key is ever exposed, regenerate it in the Alpaca dashboard and update `local_settings.py`.

---

## Further documentation

| Document | Contents |
|----------|----------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, data flow, threads, files, external services |
| [docs/STRATEGY.md](docs/STRATEGY.md) | Universe, filters, every signal and its scoring table, buy and exit rules, budget math, known limitations |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Every setting, valid ranges, and worked examples |
| [docs/DASHBOARD.md](docs/DASHBOARD.md) | Algo Desk UI, JSON API reference, online P&L page |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Running, stopping, logs, resetting, troubleshooting, FAQ |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | What changed from the original prototype and why |

---

## Disclaimer

This software is for education and experimentation with **simulated money only**. It is not investment advice. Past or simulated performance does not predict future results. If you adapt it for live trading you do so entirely at your own risk.
