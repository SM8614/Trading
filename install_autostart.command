#!/bin/bash
# Double-click to make the bot start automatically every time you log in to this Mac.
# Run uninstall_autostart.command to undo.
cd "$(dirname "$0")"
DIR="$(pwd)"
LAUNCHER="$DIR/start.command"
chmod +x "$LAUNCHER" 2>/dev/null

echo "Adding the Algo bot to your Login Items..."
echo "(macOS may ask to let Terminal control System Events — click OK.)"
osascript <<OSA
tell application "System Events"
  if exists login item "start.command" then delete login item "start.command"
  make login item at end with properties {path:"$LAUNCHER", hidden:false}
end tell
OSA
if [ $? -eq 0 ]; then
  echo "Done. The bot will start in a Terminal window each time you log in."
  echo "You can see or remove it in System Settings > General > Login Items."
else
  echo "Could not add the login item. Add it by hand: System Settings > General > Login Items > + > choose start.command in this folder."
fi

echo
echo "Optional: wake the Mac from sleep automatically at 2:15 PM ET on weekdays so the daily scan isn't missed."
echo "This needs your Mac password (it runs: sudo pmset repeat wakeorpoweron MTWRF 14:15:00)."
echo "Note: the time is in this Mac's time zone ($(date +%Z)). Skip if you're not in US Eastern time or adjust later."
read -p "Set the wake schedule? [y/N] " ans
if [[ "$ans" =~ ^[Yy]$ ]]; then
  sudo pmset repeat wakeorpoweron MTWRF 14:15:00 && echo "Wake schedule set. Check with: pmset -g sched"
fi
echo
read -n1 -p "Press any key to close..."
