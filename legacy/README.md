# Legacy prototype

These files come from an earlier version of the project and are **not used** by the bot (`main.py`). They are kept for reference.

| File | What it is |
|------|------------|
| `algotrader.html` | A browser-only screener and paper-trading page. You type your Alpaca keys into the page (stored in that browser's `localStorage`) and it calls Alpaca and Yahoo Finance directly from the browser. |
| `alpaca_trader.py` | A thin `requests`-based wrapper around the Alpaca REST API v2 (account, positions, orders, quotes). |
| `screener.py` | An older screener over a fixed list of large caps, using RSI-recovery, volume surge, MACD cross, 52-week-low bounce and daily momentum signals. Requires the `ta` package, which is not in `requirements.txt`. |

The current strategy is documented in [../docs/STRATEGY.md](../docs/STRATEGY.md).
