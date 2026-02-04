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
echo "[$(date)] Stopping any existing processes..."
pkill -9 -f tradingview_webhook_server.py 2>/dev/null || true
pkill -9 -f live_data_poller.py 2>/dev/null || true

# Kill anything on port 5000 (using fuser if lsof isn't available)
fuser -k 5000/tcp 2>/dev/null || true

sleep 3

# Start webhook server
echo "[$(date)] Starting webhook server..."
python scripts/tradingview_webhook_server.py >> logs/webhook.log 2>&1 &
WEBHOOK_PID=$!
sleep 5

# Start data poller
echo "[$(date)] Starting data poller..."
python scripts/live_data_poller.py >> logs/poller.log 2>&1 &
POLLER_PID=$!

echo "[$(date)] Jarvis started - Webhook PID: $WEBHOOK_PID, Poller PID: $POLLER_PID"

# Keep script running and monitor processes by name (not PID)
while true; do
    # Check if webhook server is running (by process name)
    if ! pgrep -f "tradingview_webhook_server.py" > /dev/null 2>&1; then
        echo "[$(date)] Webhook server not found, restarting..."
        python scripts/tradingview_webhook_server.py >> logs/webhook.log 2>&1 &
        sleep 5
    fi
    
    # Check if data poller is running
    if ! pgrep -f "live_data_poller.py" > /dev/null 2>&1; then
        echo "[$(date)] Data poller not found, restarting..."
        python scripts/live_data_poller.py >> logs/poller.log 2>&1 &
        sleep 3
    fi
    
    sleep 60
done
