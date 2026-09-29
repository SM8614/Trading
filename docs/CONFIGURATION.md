# Configuration reference

All behaviour is controlled from [`config.py`](../config.py). Secrets are **not** kept there; see [API keys](#api-keys). After changing any value, **restart the bot** (close the Terminal window and double-click `start.command` again).

---

## API keys

Loaded in this order:

1. **`local_settings.py`** (git-ignored). Create it from the template:
   ```bash
   cp local_settings.example.py local_settings.py
   ```
   ```python
   ALPACA_API_KEY    = "PK..."
   ALPACA_SECRET_KEY = "..."
   ```
2. **Environment variables** `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`, used when `local_settings.py` doesn't exist.

Use **paper** keys (they start with `PK`). The code always connects with `paper=True`; live keys will be rejected by the paper endpoint.

`ALPACA_BASE_URL` is informational; the trading client selects the paper endpoint itself.

---

## Money and position sizing

| Setting | Default | Type / range | Effect |
|---------|---------|--------------|--------|
| `STARTING_CAPITAL` | `10000` | dollars > 0 | Virtual budget the bot may use. Grows and shrinks with its P&L. |
| `ACCOUNT_BASE` | `100000` | dollars | The Alpaca paper account's real starting balance. Used to convert Alpaca equity into the bot's P&L: `virtual = STARTING_CAPITAL + (equity − ACCOUNT_BASE)`. Must match your paper account. |
| `POSITION_SIZE_USD` | `1000` | dollars | Target cost per purchase. Shares = ⌊size ÷ price⌋, so actual cost is slightly lower. |
| `DAILY_BUYS` | `3` | integer ≥ 0 | Maximum new stocks bought per trading day. `0` pauses buying while still managing exits. |
| `MAX_POSITIONS` | `10` | integer ≥ 1 | Hard cap on open positions. Also sets candidate count (`× 3`). |

Keep `MAX_POSITIONS × POSITION_SIZE_USD ≈ STARTING_CAPITAL` so the cap and the budget agree.

## Exits

| Setting | Default | Effect |
|---------|---------|--------|
| `TARGET_GAIN_PCT` | `0.15` | Take-profit at +15%. Written into each bracket order at purchase time, so changing it affects **new** buys only (and the bot's own backup check for all positions). |
| `STOP_LOSS_PCT` | `0.05` | Stop-loss at −5%. Same note as above. |
| `MAX_HOLD_DAYS` | `10` | Trading days (Mon–Fri, holidays not excluded) before the bot sells regardless of P&L. |

## Stock filters

| Setting | Default | Effect |
|---------|---------|--------|
| `MIN_STOCK_PRICE` | `5` | Ignore stocks below this price. |
| `MAX_STOCK_PRICE` | `500` | Ignore stocks above this price. Keep it below `POSITION_SIZE_USD` so at least one share fits. |
| `MIN_AVG_VOLUME` | `500_000` | Minimum 20-day average daily volume. |

## Scheduling

| Setting | Default | Effect |
|---------|---------|--------|
| `SCAN_TIME` | `"15:20"` | Daily scan start, `HH:MM` **US Eastern** regardless of your computer's time zone. The scan must finish before 16:00 for market orders to fill the same day, so don't set it much later than 15:30. |
| `MONITOR_INTERVAL_SEC` | `300` | Seconds between position checks during market hours. |

The morning summary (09:31 ET) is fixed in `main.py`.

## Scoring weights

| Setting | Default | Signal |
|---------|---------|--------|
| `WEIGHT_RSI` | `0.20` | RSI sweet spot |
| `WEIGHT_MACD` | `0.25` | MACD crossover / trend |
| `WEIGHT_MA` | `0.20` | price vs MA20 / MA50 |
| `WEIGHT_VOLUME` | `0.15` | volume vs 20-day average |
| `WEIGHT_MOMENTUM` | `0.20` | 5-day % change |

They should sum to **1.0** so scores stay in 0–1 (the code doesn't enforce it). See [STRATEGY.md](STRATEGY.md#3-the-five-signals) for what each one measures.

## Logging

| Setting | Default | Effect |
|---------|---------|--------|
| `LOG_FILE` | `"trader.log"` | Log file name, relative to the project folder. Also read by the dashboard's log view. |

## Dashboard

The port (`8765`) and bind address (`127.0.0.1`) are constants at the top of `dashboard.py`. If you change the port, also change it in `start.command`.

---

## Example setups

**More aggressive** — five buys a day, bigger positions, looser stop:
```python
STARTING_CAPITAL  = 10000
DAILY_BUYS        = 5
POSITION_SIZE_USD = 2000
MAX_POSITIONS     = 5
STOP_LOSS_PCT     = 0.08
```

**Conservative** — fewer, smaller positions, quicker profits, shorter holds:
```python
DAILY_BUYS        = 1
POSITION_SIZE_USD = 500
MAX_POSITIONS     = 20
TARGET_GAIN_PCT   = 0.08
STOP_LOSS_PCT     = 0.03
MAX_HOLD_DAYS     = 5
```

**Use the whole $100k paper account**:
```python
STARTING_CAPITAL  = 100000
ACCOUNT_BASE      = 100000
POSITION_SIZE_USD = 5000
MAX_POSITIONS     = 20
```

**Pause new buying** but keep managing exits:
```python
DAILY_BUYS = 0
```
