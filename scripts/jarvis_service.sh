#!/bin/bash
# Jarvis Trading Bot Service Script
# Used by systemd to run the bot as a background service

BOT_DIR="/home/juujuaddy/forex_trading_bot"
cd "$BOT_DIR"

# Activate virtual environment
source venv/bin/activate

# Create logs directory
mkdir -p logs

# Kill any existing processes
pkill -f tradingview_webhook_server.py 2>/dev/null || true
pkill -f live_data_poller.py 2>/dev/null || true
sleep 2

# Start webhook server
echo "[$(date)] Starting webhook server..."
python scripts/tradingview_webhook_server.py >> logs/webhook.log 2>&1 &
WEBHOOK_PID=$!
sleep 3

# Start data poller
echo "[$(date)] Starting data poller..."
python scripts/live_data_poller.py >> logs/poller.log 2>&1 &
POLLER_PID=$!

echo "[$(date)] Jarvis started - Webhook PID: $WEBHOOK_PID, Poller PID: $POLLER_PID"

# Keep script running and monitor processes
while true; do
    # Check if processes are still running
    if ! ps -p $WEBHOOK_PID > /dev/null 2>&1; then
        echo "[$(date)] Webhook server died, restarting..."
        python scripts/tradingview_webhook_server.py >> logs/webhook.log 2>&1 &
        WEBHOOK_PID=$!
    fi
    
    if ! ps -p $POLLER_PID > /dev/null 2>&1; then
        echo "[$(date)] Data poller died, restarting..."
        python scripts/live_data_poller.py >> logs/poller.log 2>&1 &
        POLLER_PID=$!
    fi
    
    sleep 60
done
