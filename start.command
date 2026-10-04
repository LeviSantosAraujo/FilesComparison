#!/bin/bash
# Start Files Comparison in the background without holding the terminal.
# Double-clickable in Finder, or run: ./start.command
APP_DIR="$(cd "$(dirname "$0")" && pwd)"

if pgrep -f "$APP_DIR/app.py" >/dev/null 2>&1; then
    echo "Files Comparison is already running."
    exit 0
fi

nohup python3 "$APP_DIR/app.py" >> "$APP_DIR/files_comparison.log" 2>&1 &
disown
echo "Files Comparison started (PID $!). Log: $APP_DIR/files_comparison.log"
