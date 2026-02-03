#!/bin/bash
# Bot Scheduler - Start/Stop based on trading hours
# Trading Session: 10:00-17:00 UTC, Mon-Thu only

BOT_DIR="/home/juujuaddy/forex_trading_bot"
LOG_FILE="$BOT_DIR/logs/scheduler.log"
WEBHOOK_SCRIPT="$BOT_DIR/scripts/tradingview_webhook_server.py"
POLLER_SCRIPT="$BOT_DIR/scripts/live_data_poller.py"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

start_bot() {
    # Check if already running
    if pgrep -f "tradingview_webhook_server.py" > /dev/null; then
        log "Bot already running"
        return
    fi
    
    log "Starting trading bot..."
    cd "$BOT_DIR"
    source venv/bin/activate
    
    # Start webhook server
    python "$WEBHOOK_SCRIPT" >> "$BOT_DIR/logs/webhook.log" 2>&1 &
    sleep 3
    
    # Start data poller
    python "$POLLER_SCRIPT" >> "$BOT_DIR/logs/poller.log" 2>&1 &
    
    log "Bot started successfully"
}

stop_bot() {
    log "Stopping trading bot..."
    pkill -f "tradingview_webhook_server.py" 2>/dev/null
    pkill -f "live_data_poller.py" 2>/dev/null
    log "Bot stopped"
}

status_bot() {
    if pgrep -f "tradingview_webhook_server.py" > /dev/null; then
        echo "Bot is RUNNING"
    else
        echo "Bot is STOPPED"
    fi
}

case "$1" in
    start)
        start_bot
        ;;
    stop)
        stop_bot
        ;;
    restart)
        stop_bot
        sleep 2
        start_bot
        ;;
    status)
        status_bot
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
