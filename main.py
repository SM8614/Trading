#!/usr/bin/env python3
# =============================================================================
# main.py — Orchestrator & Scheduler
# =============================================================================
# This is the entry point. Run it once and it will:
#   - Every trading day at SCAN_TIME (default 3:20 PM ET):
#       1. Scan all US stocks and rank them
#       2. Buy the top candidates
#   - Every MONITOR_INTERVAL_SEC seconds during market hours:
#       3. Check open positions and sell at +15% / -5%
#   - Print a portfolio summary every morning at open

from __future__ import annotations
import logging
import time
import schedule
import pytz
from datetime import datetime, time as dtime

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
# Scheduled Jobs
# ---------------------------------------------------------------------------

def job_scan_and_buy():
    """Run the daily stock scan and place buy orders for top candidates."""
    if not is_market_open():
        logger.info("Market is closed — skipping scan.")
        return

    logger.info("=" * 60)
    logger.info("DAILY SCAN STARTING")
    logger.info("=" * 60)

    BOT["scanning"] = True
    try:
        candidates = run_scan()
        if not candidates:
            logger.warning("No candidates found today.")
            return

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

    except Exception as e:
        logger.error(f"Scan/buy job failed: {e}", exc_info=True)
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

    # Schedule the daily scan near market close
    scan_job = schedule.every().day.at(SCAN_TIME, "America/New_York").do(job_scan_and_buy)

    # Schedule morning portfolio summary at 9:31 ET
    schedule.every().day.at("09:31", "America/New_York").do(job_morning_summary)

    # Schedule the position monitor every N seconds
    mon_job = schedule.every(MONITOR_INTERVAL_SEC).seconds.do(job_monitor_positions)

    url = start_dashboard()
    logger.info(f"Live dashboard: {url}")

    logger.info("Scheduler running. Press Ctrl+C to stop.")

    # Run monitor once on startup to catch any overnight changes
    job_monitor_positions()
    print_portfolio_summary()

    while True:
        BOT["next_scan"] = scan_job.next_run.isoformat() if scan_job.next_run else None
        BOT["next_monitor"] = mon_job.next_run.isoformat() if mon_job.next_run else None
        schedule.run_pending()
        time.sleep(10)


if __name__ == "__main__":
    main()
