#!/bin/bash
# Stop a running Files Comparison instance. Run: ./stop.command
APP_DIR="$(cd "$(dirname "$0")" && pwd)"

if pkill -f "$APP_DIR/app.py" 2>/dev/null; then
    echo "Files Comparison stopped."
else
    echo "Files Comparison is not running."
fi
