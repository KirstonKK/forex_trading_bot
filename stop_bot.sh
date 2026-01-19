#!/bin/bash

# Stop Forex Trading Bot

echo "Stopping Forex Trading Bot..."

# Kill processes
pkill -f tradingview_webhook_server.py 2>/dev/null && echo "✓ Stopped webhook server" || echo "  Webhook server not running"
pkill -f live_data_poller.py 2>/dev/null && echo "✓ Stopped data poller" || echo "  Data poller not running"

echo ""
echo "✓ Bot stopped"
