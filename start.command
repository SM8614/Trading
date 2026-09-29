#!/bin/bash
# Double-click to start the paper trader. Keep this window open; close it (or Ctrl+C) to stop.
cd "$(dirname "$0")"
if [ ! -f local_settings.py ] || grep -q "YOUR_PAPER" local_settings.py; then
  echo "Add your Alpaca paper API keys first: copy local_settings.example.py to local_settings.py and fill it in."; read -n1 -p "Press any key to close..."; exit 1
fi
if [ ! -d .venv ]; then
  echo "First run: setting up Python environment (one time, ~1 min)..."
  python3 -m venv .venv || { echo "Python 3 is required. Install it from python.org"; read -n1; exit 1; }
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r requirements.txt
fi
# caffeinate keeps the Mac from sleeping while the bot runs
# Open the dashboard once it is actually up (waits up to 2 minutes)
( for i in $(seq 1 120); do curl -s -o /dev/null http://localhost:8765/ && { open http://localhost:8765; break; }; sleep 1; done ) &
caffeinate -i ./.venv/bin/python main.py
echo
echo "The bot has stopped. If that was unexpected, the error is shown above."
read -n1 -p "Press any key to close..."
