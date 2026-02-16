#!/bin/bash
# ─────────────────────────────────────────────────
# Forex Trading Bot — Stop Script
# ─────────────────────────────────────────────────

echo "Stopping Forex Trading Bot..."

# Stop systemd services
sudo systemctl stop jarvis-webhook.service 2>/dev/null && echo "✅ Stopped webhook server" || echo "  Webhook service not running"
sudo systemctl stop jarvis-poller.service 2>/dev/null && echo "✅ Stopped data poller" || echo "  Poller service not running"

# Also kill any orphan processes not managed by systemd
pkill -f tradingview_webhook_server.py 2>/dev/null
pkill -f live_data_poller.py 2>/dev/null

echo ""
echo "✅ Bot stopped"
echo ""
echo "To restart:  bash restart_bot.sh"
echo "To start:    bash start_bot.sh"
