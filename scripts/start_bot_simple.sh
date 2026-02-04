#!/bin/bash
# Simple startup script - runs both services with exec to avoid orphans

cd /home/juujuaddy/forex_trading_bot
source /home/juujuaddy/forex_trading_bot/venv/bin/activate

# Start webhook server in foreground (systemd will manage it)
echo "Starting webhook server and data poller..."
python /home/juujuaddy/forex_trading_bot/scripts/tradingview_webhook_server.py &
WEBHOOK_PID=$!

# Wait for webhook to start
sleep 5

# Start poller in foreground
exec python /home/juujuaddy/forex_trading_bot/scripts/live_data_poller.py
