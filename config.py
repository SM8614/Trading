# =============================================================================
# config.py — Alpaca Paper Trading Configuration
# =============================================================================
# API keys are NOT stored here. They are read (in order) from:
#   1. local_settings.py   (git-ignored; copy local_settings.example.py to create it)
#   2. environment variables ALPACA_API_KEY / ALPACA_SECRET_KEY
import os
try:
    from local_settings import ALPACA_API_KEY, ALPACA_SECRET_KEY
except ImportError:
    ALPACA_API_KEY    = os.environ.get("ALPACA_API_KEY", "YOUR_PAPER_API_KEY")
    ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "YOUR_PAPER_SECRET_KEY")
ALPACA_BASE_URL   = "https://paper-api.alpaca.markets"   # Paper trading endpoint

# --- Trading Parameters ---
TARGET_GAIN_PCT      = 0.15    # Sell when position is up 15%
STOP_LOSS_PCT        = 0.05    # Sell if position drops 5% (risk management)
STARTING_CAPITAL     = 10000   # Budget the bot may use (its own "account"), grows/shrinks with its profit
ACCOUNT_BASE         = 100000  # Alpaca paper account's actual starting balance (used to compute the bot's P&L)
MAX_POSITIONS        = 10      # Max simultaneous open positions
DAILY_BUYS           = 3       # New stocks to buy every trading day
MAX_HOLD_DAYS        = 10      # Sell anything held this many trading days (frees cash for new buys)
POSITION_SIZE_USD    = 1000    # Dollar amount to invest per stock
MAX_STOCK_PRICE      = 500     # Ignore stocks above this price (liquidity)
MIN_STOCK_PRICE      = 5       # Ignore penny stocks below this price
MIN_AVG_VOLUME       = 500_000 # Minimum average daily volume (liquidity filter)

# --- Scheduling ---
# The scanner runs before market close (2:30 PM ET) and places buy orders
# The monitor runs every 5 minutes during market hours to check for exits
SCAN_TIME            = "14:30"  # HH:MM Eastern Time — scan takes ~2-5 min (Alpaca data; up to ~40 min on the Yahoo fallback), leaving room before the 4:00 close
MONITOR_INTERVAL_SEC = 300      # Check positions every 5 minutes

# --- Scoring Weights (must sum to 1.0) ---
# Adjust these to tune how much each signal contributes to the final score
WEIGHT_RSI       = 0.20   # RSI momentum
WEIGHT_MACD      = 0.25   # MACD crossover signal
WEIGHT_MA        = 0.20   # Price vs moving averages
WEIGHT_VOLUME    = 0.15   # Volume spike
WEIGHT_MOMENTUM  = 0.20   # Recent price momentum (last 5 days)

# --- Logging ---
LOG_FILE = "trader.log"
