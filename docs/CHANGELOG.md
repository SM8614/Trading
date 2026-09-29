# Changelog

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
