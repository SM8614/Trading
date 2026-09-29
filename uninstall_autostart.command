#!/bin/bash
# Double-click to stop the bot from starting automatically at login.
osascript -e 'tell application "System Events" to if exists login item "start.command" then delete login item "start.command"' \
  && echo "Removed the Algo bot from Login Items."
read -p "Also remove the weekday wake schedule (needs your password)? [y/N] " ans
if [[ "$ans" =~ ^[Yy]$ ]]; then sudo pmset repeat cancel && echo "Wake schedule removed."; fi
read -n1 -p "Press any key to close..."
