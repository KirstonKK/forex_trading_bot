#!/bin/bash
# Start both webhook server and data poller as background processes

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

BASE_DIR="/home/juujuaddy/forex_trading_bot"
cd "$BASE_DIR"

# Activate virtual environment
source "$BASE_DIR/venv/bin/activate"

# Start webhook server in background
echo "Starting webhook server..."
python "$BASE_DIR/scripts/tradingview_webhook_server.py" >> "$BASE_DIR/logs/webhook.log" 2>> "$BASE_DIR/logs/webhook_error.log" &
WEBHOOK_PID=$!
echo "Webhook server started with PID: $WEBHOOK_PID"

# Wait for webhook server to initialize
sleep 5

# Check if webhook is running
if ! kill -0 $WEBHOOK_PID 2>/dev/null; then
    echo "ERROR: Webhook server failed to start!"
    exit 1
fi

# Start data poller in background
echo "Starting data poller..."
python "$BASE_DIR/scripts/live_data_poller.py" >> "$BASE_DIR/logs/poller.log" 2>> "$BASE_DIR/logs/poller_error.log" &
POLLER_PID=$!
echo "Data poller started with PID: $POLLER_PID"

# Keep script running and monitor processes
echo "Both services started. Monitoring..."
while true; do
    # Check if webhook is still running
    if ! kill -0 $WEBHOOK_PID 2>/dev/null; then
        echo "ERROR: Webhook server died! Restarting..."
        python "$BASE_DIR/scripts/tradingview_webhook_server.py" >> "$BASE_DIR/logs/webhook.log" 2>> "$BASE_DIR/logs/webhook_error.log" &
        WEBHOOK_PID=$!
        sleep 5
    fi
    
    # Check if poller is still running
    if ! kill -0 $POLLER_PID 2>/dev/null; then
        echo "ERROR: Data poller died! Restarting..."
        python "$BASE_DIR/scripts/live_data_poller.py" >> "$BASE_DIR/logs/poller.log" 2>> "$BASE_DIR/logs/poller_error.log" &
        POLLER_PID=$!
    fi
    
    sleep 30
done
