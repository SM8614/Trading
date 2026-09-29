# Trading strategy

A precise description of what the bot buys, why, and when it sells. All numbers are the defaults in `config.py`.

> The strategy is a simple momentum / trend-following screen. It has **not** been back-tested. Its purpose is experimentation with paper money.

---

## 1. Universe

Every Alpaca asset that is:

- `asset_class == us_equity`, `status == active`, `tradable == True`
- listed on **NYSE**, **NASDAQ** or **ARCA**
- a plain symbol (no `.` or `/`, which excludes share classes such as `BRK.B` and some foreign listings)

That is roughly 10,000 symbols. ETFs listed on these exchanges are *not* explicitly excluded; they usually rank lower but can appear.

## 2. Filters

Price history: ~100 calendar days of daily bars from Yahoo Finance, including today's partial bar (the scan runs at 3:20 PM ET). A symbol is scored only if:

| Filter | Rule | Why |
|--------|------|-----|
| History | ≥ 30 daily bars | indicators need data |
| Price floor | last close ≥ **$5** | avoid penny stocks |
| Price ceiling | last close ≤ **$500** | $1,000 must buy at least a couple of shares |
| Liquidity | 20-day average volume ≥ **500,000** shares | tight spreads, reliable fills |

## 3. The five signals

Each signal maps to a score between 0 and 1.

### 3.1 RSI (weight 20%)
14-period Relative Strength Index using simple rolling averages of gains and losses.

| RSI | Score | Reading |
|-----|-------|---------|
| 45 – 65 | **1.0** | healthy momentum with room to run |
| 30 – 45 or 65 – 75 | 0.6 | acceptable |
| < 30 | 0.2 | oversold, falling knife risk |
| > 75 | 0.1 | overbought, pullback risk |

### 3.2 MACD (weight 25%)
MACD = EMA(12) − EMA(26); signal = EMA(9) of MACD.

| Condition | Score |
|-----------|-------|
| MACD crossed above signal on the latest bar | **1.0** |
| MACD above signal | 0.6 |
| MACD below signal | 0.0 |

### 3.3 Moving-average trend (weight 20%)

| Condition | Score |
|-----------|-------|
| price > MA20 > MA50 | **1.0** |
| price > MA20 | 0.6 |
| price > MA50 only | 0.3 |
| below both | 0.0 |
| fewer than 50 bars | 0.5 (neutral) |

### 3.4 Volume spike (weight 15%)
Today's volume ÷ average of the previous 20 days.

| Ratio | Score |
|-------|-------|
| ≥ 2.0× | **1.0** |
| ≥ 1.5× | 0.8 |
| ≥ 1.0× | 0.5 |
| ≥ 0.7× | 0.3 |
| < 0.7× | 0.1 |

Because the scan runs before the close, today's volume is partial (roughly 85–90% of a full day), which biases this score slightly downward for every stock equally.

### 3.5 Five-day momentum (weight 20%)
Percent change in close over the last 5 bars.

| Change | Score |
|--------|-------|
| ≥ +5% | **1.0** |
| ≥ +2% | 0.8 |
| ≥ 0% | 0.6 |
| ≥ −2% | 0.3 |
| < −2% | 0.0 |

### 3.6 Composite score

```
score = 0.20·RSI + 0.25·MACD + 0.20·MA + 0.15·Volume + 0.20·Momentum      (0 … 1)
```

**Worked example.** RSI 58 → 1.0; MACD above signal, no fresh cross → 0.6; price > MA20 > MA50 → 1.0; volume 1.2× → 0.5; +3.1% over 5 days → 0.8.
Score = 0.20·1.0 + 0.25·0.6 + 0.20·1.0 + 0.15·0.5 + 0.20·0.8 = **0.785**.

The maximum possible is 1.0. In practice the top of the list usually sits between 0.75 and 0.95.

## 4. Buy rules

Run once per trading day at **3:20 PM ET**:

1. Rank all scored stocks; keep the top 30 as candidates.
2. Open slots = `min(DAILY_BUYS, MAX_POSITIONS − positions currently open)` → at most **3** per day, never more than **10** open.
3. Budget available = virtual account value − value of open positions (see §6).
4. Walk down the candidate list:
   - skip symbols already held;
   - price = mid of latest bid/ask (fallbacks: one side, then last trade);
   - shares = ⌊ $1,000 ÷ price ⌋ (skip if 0);
   - stop buying for the day if the cost exceeds the remaining budget;
   - submit a **bracket order**: market buy, `GTC`, with
     - take-profit **limit** at `price × 1.15`
     - **stop** at `price × 0.95`
   - record today as the buy date.

Buying shortly before the close means the purchase is priced on the day the signals were measured, and the stock has the next session to move.

## 5. Exit rules

A position is closed by whichever happens first:

| Exit | Trigger | Who executes | Needs the bot running? |
|------|---------|--------------|------------------------|
| **Take profit** | price reaches +15% | Alpaca (bracket limit leg) | No |
| **Stop loss** | price falls to −5% | Alpaca (bracket stop leg) | No |
| **Take profit / stop (backup)** | bot sees ≥ +15% or ≤ −5% on its 5-minute check | bot, market order | Yes |
| **Max hold** | 10 trading days since purchase | bot: cancels bracket legs, then market sell | Yes |

Only one leg of a bracket can fill; when one fills Alpaca cancels the other. Stop orders become market orders when triggered, so a stock that gaps down overnight can be sold below −5%.

## 6. The virtual $10,000 budget

The Alpaca paper account holds $100,000 (`ACCOUNT_BASE`). The bot behaves as if it only had `STARTING_CAPITAL` = $10,000:

```
virtual value  = STARTING_CAPITAL + (Alpaca equity − ACCOUNT_BASE)
available cash = virtual value − market value of open positions
```

So profits are reinvested and losses shrink the budget. This relies on the bot being the **only** thing trading in that paper account; manual trades would be counted as the bot's P&L.

To make the Alpaca account itself hold $10,000, reset the paper account in Alpaca's dashboard with a $10,000 balance, set `ACCOUNT_BASE = 10000`, and update your keys (a reset issues new ones).

## 7. Capital usage at the defaults

| Day | Max new buys | Max open | Max invested |
|-----|--------------|----------|--------------|
| 1 | 3 | 3 | ≈ $3,000 |
| 2 | 3 | 6 | ≈ $6,000 |
| 3 | 3 | 9 | ≈ $9,000 |
| 4+ | 1 until a slot frees | 10 | ≈ $10,000 |

With a 10-day maximum hold, capital recycles at least every two weeks.

## 8. Known limitations

- **No back-test.** Weights and thresholds are hand-picked.
- **Correlated picks.** On strong market days the top scorers are often in the same sector.
- **Data source.** Yahoo Finance via `yfinance` is unofficial and can throttle or change format.
- **Quotes.** The free Alpaca data plan uses the IEX feed; bid/ask can be wide or missing for thin names (the liquidity filter reduces this).
- **Gaps.** Stops can fill well below −5% after overnight news.
- **Partial-day bar.** Volume and the last close are intraday values at 3:20 PM.
- **Bot-dependent rules.** The 10-day exit and daily buying only happen while the bot is running.
