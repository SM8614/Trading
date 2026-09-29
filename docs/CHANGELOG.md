# Changelog

## 2.2.0 — 2026-09-29

### Changed
- **Scan is ~20× faster.** Daily bars now come from Alpaca's consolidated (SIP) feed, 1,000 symbols per request: a full scan of ~10,750 symbols takes about 2 minutes instead of ~38. Yahoo Finance remains as an automatic fallback per chunk.
- **Scan time moved to 2:30 PM ET** (was 3:20 PM) so even a slow fallback scan finishes before the close. The optional weekday wake moved to 2:15 PM.

### Fixed
- **Rejected bracket orders.** Sizing and bracket levels used the bid/ask mid from the IEX quote, which could be stale; Alpaca validates against the last trade and rejected orders such as `stop_loss.stop_price must be <= base_price - 0.01`. The latest trade price is now used.

## 2.1.0 — 2026-09-29

### Added
- **Catch-up scans.** The daily scan is no longer a fixed timer. The bot records the last trading day it scanned (`scan_state.json`) and, every minute, runs any scan that is due, so a scan missed while the computer was off or asleep runs as soon as the bot is back and the market is open. Uses Alpaca's trading calendar (holidays, early closes). Failed scans retry after 10 minutes.
- **Start at login.** `install_autostart.command` adds the bot to macOS Login Items and can set a weekday 3:05 PM wake; `uninstall_autostart.command` removes both.
- `start.command` no longer starts a second copy if the bot is already running.
- Dashboard shows when a missed scan is pending.

## 2.0.0 — 2026-09-28

First version pushed to GitHub. Starts from the original prototype ("Stock Scanner & Paper Trader") and fixes the problems that kept it from trading.

### Fixed
- **Scan returned nothing.** Newer `yfinance` returns multi-level columns even for one ticker, so every stock failed silently and no candidates were ever found. Downloads are now batched (200 symbols per call) and columns normalised.
- **Scan ran past the close.** Scanning ~10,000 symbols one at a time starting 3:55 PM could not finish before 4:00 PM. Batch downloads plus a 3:20 PM start fix this.
- **50-day moving average never used.** 60 calendar days held only ~41 trading days, so the MA signal was always neutral. History is now ~100 calendar days.
- **Today's bar excluded.** `yfinance`'s `end` date is exclusive; it now ends tomorrow.
- **Holidays treated as trading days.** Market status now comes from Alpaca's clock.
- **Schedule followed the computer's time zone.** Jobs are pinned to `America/New_York`.
- **Price lookup could return 0** when the ask was missing; now uses bid/ask mid, then either side, then last trade.
- **Crash on Python 3.9** (macOS default) because of `X | None` type hints; every module now uses `from __future__ import annotations`.

### Added
- **Daily buying**: up to `DAILY_BUYS` (3) new stocks per day instead of stopping after the first five.
- **Bracket orders**: +15% / −5% exits are held by Alpaca, so they work when the computer is off.
- **Maximum holding period**: positions are sold after `MAX_HOLD_DAYS` (10) trading days.
- **Virtual budget**: the bot trades `STARTING_CAPITAL` ($10,000) inside the $100,000 paper account and reports P&L against it.
- **Algo Desk**: live local dashboard with light/dark/auto theme and a JSON API.
- **`start.command`**: one-click macOS launcher (virtualenv, dependencies, keep-awake, auto-open dashboard, error pause).
- **`tools/pnl_snapshot.py`** and an optional online P&L page refreshed after each close.
- Detailed documentation in `docs/`.

### Security
- API keys moved out of `config.py` into git-ignored `local_settings.py` (or environment variables).

### Moved
- The unused earlier prototype (`algotrader.html`, `alpaca_trader.py`, `screener.py`) is kept in `legacy/`.

## 1.0.0 — original prototype
- Daily scan at 3:55 PM ET, five signals, up to 5 positions of $1,000, bot-monitored +15% / −5% exits.
