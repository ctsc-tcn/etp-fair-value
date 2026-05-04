#!/bin/bash
# Runs an update script if today is a trading day (not a market holiday).
# Schedule via cron Mon–Fri only.
# Usage: cron_runner.sh update_fbtc.py

set -e

if [ -z "$1" ]; then
    echo "Usage: $(basename "$0") <script.py>" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/venv/bin/python"
SCRIPT="$SCRIPT_DIR/$1"
LOG="$SCRIPT_DIR/logs/$(basename "$1" .py)_$(date +%Y%m%d).log"

if [ ! -f "$SCRIPT" ]; then
    echo "Script not found: $SCRIPT" >&2
    exit 2
fi

mkdir -p "$SCRIPT_DIR/logs"

# Check for market holiday (exits non-zero on holiday)
if ! "$VENV" "$SCRIPT_DIR/market_holidays.py" > /dev/null 2>&1; then
    echo "$(date): Market holiday — skipping $1" >> "$LOG"
    exit 0
fi

echo "$(date): Running $1" >> "$LOG"
xvfb-run "$VENV" "$SCRIPT" >> "$LOG" 2>&1
echo "$(date): Done" >> "$LOG"
