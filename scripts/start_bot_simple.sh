#!/bin/bash
# Startup script with Telegram alerts for start/stop events

cd /home/juujuaddy/forex_trading_bot
source /home/juujuaddy/forex_trading_bot/venv/bin/activate

# Telegram configuration
TELEGRAM_BOT_TOKEN="8001169647:AAESVk1NjD2ppFUHVDoPq_OamyGHx3gBUU0"
TELEGRAM_CHAT_ID="117216462"
TELEGRAM_GROUP_ID="-5005853931"

# Function to send Telegram alert to BOTH personal and group
send_telegram_alert() {
    local message="$1"
    # Send to personal chat
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        -d "text=${message}" \
        -d "parse_mode=HTML" > /dev/null 2>&1
    # Send to group chat
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_GROUP_ID}" \
        -d "text=${message}" \
        -d "parse_mode=HTML" > /dev/null 2>&1
}

# Cleanup function - called on shutdown
cleanup() {
    echo "Shutting down Jarvis Trading Bot..."
    send_telegram_alert "🔴 <b>Jarvis Bot Shutting Down</b>%0A%0ATime: $(date '+%Y-%m-%d %H:%M:%S UTC')%0AReason: Service stopped or VPS shutdown"
    
    # Kill child processes
    if [ ! -z "$WEBHOOK_PID" ]; then
        kill $WEBHOOK_PID 2>/dev/null
    fi
    if [ ! -z "$POLLER_PID" ]; then
        kill $POLLER_PID 2>/dev/null
    fi
    
    exit 0
}

# Set trap for shutdown signals
trap cleanup SIGTERM SIGINT SIGHUP

# Send startup alert
send_telegram_alert "🟢 <b>Jarvis Bot Starting</b>%0A%0ATime: $(date '+%Y-%m-%d %H:%M:%S UTC')%0AStatus: Initializing webhook server and data poller..."

echo "Starting webhook server and data poller..."
python /home/juujuaddy/forex_trading_bot/scripts/tradingview_webhook_server.py &
WEBHOOK_PID=$!

# Wait for webhook to start
sleep 5

# Verify webhook is running
if curl -s http://localhost:5000/health > /dev/null 2>&1; then
    send_telegram_alert "✅ <b>Jarvis Bot Online</b>%0A%0ATime: $(date '+%Y-%m-%d %H:%M:%S UTC')%0AWebhook: Running%0APoller: Starting...%0ASymbols: EUR/USD, GBP/USD, XAU/USD"
else
    send_telegram_alert "⚠️ <b>Jarvis Bot Warning</b>%0A%0AWebhook server may not be responding. Attempting to continue..."
fi

# Start poller (run in background so we can monitor both)
python /home/juujuaddy/forex_trading_bot/scripts/live_data_poller.py &
POLLER_PID=$!

# Health monitoring loop - check every 60 seconds
while true; do
    sleep 60
    
    # Check if webhook is still responding
    if ! curl -s http://localhost:5000/health > /dev/null 2>&1; then
        send_telegram_alert "🔴 <b>Jarvis Bot Alert</b>%0A%0AWebhook server not responding!%0ATime: $(date '+%Y-%m-%d %H:%M:%S UTC')%0AAction: Service will restart..."
        exit 1  # Exit with failure to trigger systemd restart
    fi
    
    # Check if poller process is still running
    if ! kill -0 $POLLER_PID 2>/dev/null; then
        send_telegram_alert "🔴 <b>Jarvis Bot Alert</b>%0A%0AData poller crashed!%0ATime: $(date '+%Y-%m-%d %H:%M:%S UTC')%0AAction: Service will restart..."
        exit 1  # Exit with failure to trigger systemd restart
    fi
done
