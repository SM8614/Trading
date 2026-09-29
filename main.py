#!/usr/bin/env python3
# =============================================================================
# main.py — Orchestrator & Scheduler
# =============================================================================
# This is the entry point. Run it once and it will:
#   - Every trading day at SCAN_TIME (default 2:30 PM ET):
#       1. Scan all US stocks and rank them
#       2. Buy the top candidates
#   - Every MONITOR_INTERVAL_SEC seconds during market hours:
#       3. Check open positions and sell at +15% / -5%
#   - Print a portfolio summary every morning at open
#   - Catch-up: if the computer was off or asleep at SCAN_TIME, the missed scan
#     runs as soon as the bot is running again while the market is open.

from __future__ import annotations
import logging
import time
import schedule
import pytz
from datetime import datetime, date, timedelta, time as dtime

from config import SCAN_TIME, MONITOR_INTERVAL_SEC, LOG_FILE
from scanner import run_scan
from trader import buy_stocks, monitor_and_exit, print_portfolio_summary
from dashboard import start_dashboard, BOT
import json, os

# ---------------------------------------------------------------------------
# Logging setup — writes to file + console
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")

# ---------------------------------------------------------------------------
# Market Hours Helper
# ---------------------------------------------------------------------------
MARKET_OPEN  = dtime(9, 30)
MARKET_CLOSE = dtime(16, 0)


def is_market_open() -> bool:
    """Returns True if US markets are open. Uses Alpaca's clock (handles holidays),
    falling back to Mon–Fri 9:30–16:00 ET."""
    try:
        from alpaca.trading.client import TradingClient
        from config import ALPACA_API_KEY, ALPACA_SECRET_KEY
        return bool(TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True).get_clock().is_open)
    except Exception:
        pass
    now_et = datetime.now(ET)
    if now_et.weekday() >= 5:   # Saturday=5, Sunday=6
        return False
    t = now_et.time()
    return MARKET_OPEN <= t <= MARKET_CLOSE


# ---------------------------------------------------------------------------
# Catch-up scheduling
# ---------------------------------------------------------------------------
# Instead of a fixed "run at 14:30" timer (which is simply missed when the
# computer is off), the bot keeps track of the last trading day it scanned for
# in scan_state.json. Every minute it asks: "which trading day's scan should
# have happened by now?" If that is newer than the last one done and the market
# is open, it scans now. Several missed days collapse into one catch-up scan.

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "scan_state.json")
CATCHUP_CUTOFF_MIN = 15          # don't start a scan in the last 15 minutes before the close
_cal_cache = {"day": None, "days": []}
_retry = {"after": None}         # back-off after a failed scan


def _trading_days():
    """Alpaca trading calendar for the last 14 and next 14 days: [(date, open_dt, close_dt)] in ET (naive)."""
    today = datetime.now(ET).date()
    if _cal_cache["day"] != today:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetCalendarRequest
        from config import ALPACA_API_KEY, ALPACA_SECRET_KEY
        cal = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True).get_calendar(
            GetCalendarRequest(start=today - timedelta(days=14), end=today + timedelta(days=14)))
        _cal_cache.update(day=today, days=[(c.date, c.open, c.close) for c in cal])
    return _cal_cache["days"]


def _scan_moment(d, close_dt):
    """When the scan for trading day d is due: SCAN_TIME, or 40 min before an early close."""
    hh, mm = map(int, SCAN_TIME.split(":"))
    due = datetime.combine(d, dtime(hh, mm))
    return min(due, close_dt - timedelta(minutes=40))


def due_scan_day():
    """Most recent trading day whose scan time has already passed."""
    now = datetime.now(ET).replace(tzinfo=None)
    for d, _o, c in reversed(_trading_days()):
        if _scan_moment(d, c) <= now:
            return d
    return None


def next_scan_time():
    """Next scheduled scan moment (ET, naive) after now."""
    now = datetime.now(ET).replace(tzinfo=None)
    for d, _o, c in _trading_days():
        if _scan_moment(d, c) > now:
            return _scan_moment(d, c)
    return None


def load_last_scan_for():
    try:
        with open(STATE_FILE) as f:
            return date.fromisoformat(json.load(f)["last_scan_for"])
    except Exception:
        return None


def save_last_scan_for(d):
    with open(STATE_FILE, "w") as f:
        json.dump({"last_scan_for": d.isoformat(), "saved_at": datetime.now(ET).isoformat()}, f)


def job_scan_check():
    """Every minute: run today's scan, or a missed one, if it is due and the market is open."""
    try:
        due = due_scan_day()
        last = load_last_scan_for()
        if last is None and due is not None:
            # First run ever: start tracking from now instead of catching up history.
            save_last_scan_for(due)
            logger.info(f"Scan tracking started (next scan: {next_scan_time()} ET).")
            return
        pending = due is not None and due > last
        BOT["catchup_pending"] = bool(pending and due != datetime.now(ET).date())
        if not pending:
            return
        if _retry["after"] and datetime.now(ET) < _retry["after"]:
            return

        from alpaca.trading.client import TradingClient
        from config import ALPACA_API_KEY, ALPACA_SECRET_KEY
        clock = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True).get_clock()
        if not clock.is_open:
            return                                  # wait for the next open; stays pending
        mins_left = (clock.next_close - clock.timestamp).total_seconds() / 60
        if mins_left < CATCHUP_CUTOFF_MIN:
            return                                  # too close to the close; do it at the next open

        if due != datetime.now(ET).date():
            logger.info(f"CATCH-UP: the scan for {due} was missed (computer off or asleep). Running it now.")
        if job_scan_and_buy():
            save_last_scan_for(due)
            BOT["catchup_pending"] = False
        else:
            _retry["after"] = datetime.now(ET) + timedelta(minutes=10)
            logger.warning("Scan did not complete; retrying in 10 minutes.")
    except Exception as e:
        logger.error(f"Scan check failed: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Scheduled Jobs
# ---------------------------------------------------------------------------

def job_scan_and_buy() -> bool:
    """Run the daily stock scan and place buy orders for top candidates.
    Returns True when the scan completed (even if nothing was bought)."""
    if not is_market_open():
        logger.info("Market is closed — skipping scan.")
        return False

    logger.info("=" * 60)
    logger.info("DAILY SCAN STARTING")
    logger.info("=" * 60)

    BOT["scanning"] = True
    try:
        candidates = run_scan()
        if not candidates:
            logger.warning("No candidates found today.")
            return True

        bought = buy_stocks(candidates)
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_scan.json"), "w") as f:
                json.dump({"time": datetime.now(ET).isoformat(), "candidates": candidates, "bought": bought}, f, default=str)
        except Exception as e:
            logger.warning(f"Could not save scan results: {e}")

        if bought:
            logger.info(f"Bought {len(bought)} stock(s): {', '.join(bought)}")
        else:
            logger.info("No new stocks purchased today.")
        return True

    except Exception as e:
        logger.error(f"Scan/buy job failed: {e}", exc_info=True)
        return False
    finally:
        BOT["scanning"] = False


def job_monitor_positions():
    """Check open positions and exit at target gain or stop loss."""
    if not is_market_open():
        return

    BOT["last_monitor"] = datetime.now(ET).isoformat()
    try:
        exits = monitor_and_exit()
        if exits:
            for exit_record in exits:
                logger.info(
                    f"EXIT: {exit_record['symbol']}  "
                    f"reason={exit_record['reason']}  "
                    f"P&L={exit_record['pnl_pct']:+.1%}"
                )
    except Exception as e:
        logger.error(f"Monitor job failed: {e}", exc_info=True)


def job_morning_summary():
    """Print portfolio summary at market open each day."""
    if not is_market_open():
        return
    try:
        print_portfolio_summary()
    except Exception as e:
        logger.error(f"Morning summary failed: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def main():
    logger.info("=" * 60)
    logger.info("Stock Scanner & Paper Trader — STARTING UP")
    logger.info(f"  Scan time:        {SCAN_TIME} ET (daily)")
    logger.info(f"  Monitor interval: every {MONITOR_INTERVAL_SEC}s during market hours")
    logger.info("=" * 60)

    # Daily scan (and catch-up of a missed one) — checked every minute
    schedule.every(1).minutes.do(job_scan_check)

    # Schedule morning portfolio summary at 9:31 ET
    schedule.every().day.at("09:31", "America/New_York").do(job_morning_summary)

    # Schedule the position monitor every N seconds
    mon_job = schedule.every(MONITOR_INTERVAL_SEC).seconds.do(job_monitor_positions)

    url = start_dashboard()
    logger.info(f"Live dashboard: {url}")

    logger.info("Scheduler running. Press Ctrl+C to stop.")

    # Run monitor once on startup to catch any overnight changes, then check for a missed scan
    job_monitor_positions()
    print_portfolio_summary()
    job_scan_check()

    while True:
        try:
            nxt = next_scan_time()
            BOT["next_scan"] = ET.localize(nxt).isoformat() if nxt else None
        except Exception:
            pass
        BOT["next_monitor"] = mon_job.next_run.isoformat() if mon_job.next_run else None
        schedule.run_pending()
        time.sleep(10)


if __name__ == "__main__":
    main()
