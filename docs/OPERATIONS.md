# Operations guide

Day-to-day running, monitoring, maintenance and troubleshooting.

---

## 1. Requirements

- macOS, Linux or Windows with **Python 3.9+** (macOS's built-in `/usr/bin/python3` 3.9 works).
- Internet access to `paper-api.alpaca.markets`, `data.alpaca.markets` and Yahoo Finance.
- A free Alpaca account with **paper** API keys.
- The computer must be **on and awake at the scan time** (3:20 PM ET) on trading days for buys to happen.

## 2. Starting

**macOS:** double-click `start.command`. It:
1. checks that `local_settings.py` exists and has real keys;
2. on first run, creates `.venv` and installs `requirements.txt`;
3. waits for the dashboard to come up (up to 2 minutes) and opens it in the default browser;
4. runs `caffeinate -i .venv/bin/python main.py` so the Mac doesn't idle-sleep while the bot runs;
5. if the bot exits, keeps the window open with the error visible.

If macOS says the file can't be opened, right-click → **Open** once. If it says it's not executable: `chmod +x start.command`.

**Other systems:**
```bash
source .venv/bin/activate
python main.py
```
To keep it running after you close the terminal on Linux: `nohup python main.py &` or a `systemd` / `tmux` session.

### What you should see
```
Stock Scanner & Paper Trader — STARTING UP
  Scan time:        15:20 ET (daily)
Live dashboard: http://localhost:8765
Scheduler running. Press Ctrl+C to stop.
PORTFOLIO SUMMARY …
```

## 3. Stopping

Close the Terminal window or press **Ctrl+C**. Open positions and their bracket exits stay with Alpaca; the +15% / −5% exits keep working. The 10-day rule and new daily buys pause until you start the bot again.

To liquidate everything, use Alpaca's dashboard (*Positions → Close all*) after stopping the bot.

## 4. Daily routine

Nothing is required. Optional checks:
- After 3:30 PM ET: *Latest scan* and *Trades* on Algo Desk show what was bought.
- After the close: today's P&L on Algo Desk or the online P&L page.

## 5. Logs and state

| File | What to look for |
|------|------------------|
| `trader.log` | `DAILY SCAN STARTING`, `Progress: N/M scanned`, `BUY order placed`, `SELL (TAKE_PROFIT|STOP_LOSS|MAX_HOLD)`, `ERROR` |
| `last_scan.json` | full candidate list with every sub-score |
| `entries.json` | buy date per open position |

Useful commands:
```bash
tail -f trader.log                         # follow live
grep -E "BUY|SELL" trader.log              # all trades
grep ERROR trader.log                      # problems
python -m json.tool last_scan.json | less  # inspect scores
```

`trader.log` grows forever (a few hundred KB per month). Rename or delete it while the bot is stopped to start fresh.

## 6. Changing settings

Edit `config.py`, then restart. See [CONFIGURATION.md](CONFIGURATION.md). Bracket prices of positions already open are not changed by edits.

## 7. Rotating API keys

1. In Alpaca: *Paper Trading → API Keys → Regenerate*.
2. Put the new values in `local_settings.py`.
3. Restart the bot.
4. If you use the online P&L page, update the keys in its scheduled task.

## 8. Resetting

- **Start over with fresh paper money:** stop the bot, reset the paper account in Alpaca (choose the balance), update keys, set `ACCOUNT_BASE` to the new balance, delete `entries.json` and `last_scan.json`, start the bot.
- **Rebuild the Python environment:** delete `.venv/` and run `start.command` again.

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Browser: *Can't connect to the server* at `localhost:8765` | bot not running, still installing, or crashed | Look at the Terminal window. Start it with `start.command`. On first run wait for the install to finish. |
| Terminal: `TypeError: unsupported operand type(s) for |` | Python older than 3.9 or a file missing `from __future__ import annotations` | Use Python ≥ 3.9 and keep the `__future__` import at the top of each module. |
| *Add your Alpaca paper API keys first* | `local_settings.py` missing or still has placeholders | Create it from `local_settings.example.py`. |
| Red banner *Can't reach Alpaca … 401* | wrong or regenerated keys | Update `local_settings.py`, restart. |
| `Market is closed — skipping scan.` | weekend or holiday | Normal. |
| Scan finds `0 stocks scored` | Yahoo Finance blocked or changed format | Check internet; `pip install -U yfinance`; test with `python -c "from scanner import fetch_ohlcv_batch; print(fetch_ohlcv_batch(['AAPL']).keys())"`. |
| `Not enough budget left` | budget fully invested | Normal; buys resume when positions close. |
| `All position slots are full` | `MAX_POSITIONS` reached | Normal. |
| `Failed to place sell order … insufficient qty` | bracket legs still holding shares | The bot cancels legs and waits 2 s; if it repeats, cancel open orders for that symbol in Alpaca and let the next 5-minute check sell. |
| Nothing bought although the bot runs | Mac asleep at 3:20 PM, or scan still running at the close | Keep the Mac awake (lid open or power adapter + "prevent sleep"); move `SCAN_TIME` earlier. |
| Port 8765 already in use | another copy of the bot running | Close the other Terminal window, or change `PORT` in `dashboard.py` and `start.command`. |

## 10. FAQ

**Is any real money at risk?** No. Keys are paper keys and the client is created with `paper=True`.

**Will it trade if my Mac is off?** Existing exits (+15% / −5%) yes, because they live on Alpaca. New buys and the 10-day exit, no.

**Why buy at 3:20 PM instead of the open?** The signals are measured on nearly complete daily data, and the order fills before the close at a price close to the one scored.

**Can I run it in the cloud?** Yes, on any always-on Linux machine: clone, create `local_settings.py`, and run `python main.py` under `systemd` or `tmux`. The dashboard binds to `127.0.0.1`; use an SSH tunnel (`ssh -L 8765:localhost:8765 host`) to view it.

**How do I see results over weeks?** Algo Desk → *All days*, or the Alpaca web dashboard's portfolio history.
