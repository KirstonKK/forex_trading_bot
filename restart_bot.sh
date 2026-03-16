#!/bin/bash
# ─────────────────────────────────────────────────
# Forex Trading Bot — Restart Script
# Uses systemd services for auto-restart on crash/reboot
# ─────────────────────────────────────────────────

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "════════════════════════════════════════════════════════"
echo -e "${YELLOW}  RESTARTING FOREX TRADING BOT${NC}"
echo "════════════════════════════════════════════════════════"
echo ""

# Pre-flight: ensure env file exists before restarting (prevents crash-loop)
ENV_FILE="/home/vanhansen53/forex_trading_bot/forex-bot.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}❌ Missing $ENV_FILE${NC}"
    echo ""
    echo "  The bot needs this file for WEBHOOK_SECRET and Telegram keys."
    echo "  Run the setup script to create it:"
    echo ""
    echo "    bash scripts/setup_env.sh"
    echo ""
    exit 1
fi
# Verify WEBHOOK_SECRET is actually set (not blank or placeholder)
if ! grep -q '^WEBHOOK_SECRET=.\{10,\}' "$ENV_FILE" || grep -q 'replace_with' "$ENV_FILE"; then
    echo -e "${RED}❌ WEBHOOK_SECRET is missing or still a placeholder in $ENV_FILE${NC}"
    echo "  Run: bash scripts/setup_env.sh"
    exit 1
fi

# Also kill any orphan processes not managed by systemd
pkill -f tradingview_webhook_server.py 2>/dev/null
pkill -f live_data_poller.py 2>/dev/null
sleep 1

# Restart services
echo -e "${YELLOW}⏳ Restarting webhook server...${NC}"
sudo systemctl restart jarvis-webhook.service
sleep 2

STATUS=$(systemctl is-active jarvis-webhook.service)
if [ "$STATUS" = "active" ]; then
    echo -e "${GREEN}✅ Webhook server running${NC}"
else
    echo -e "${RED}❌ Webhook server FAILED${NC}"
    sudo journalctl -u jarvis-webhook.service --no-pager -n 10
    exit 1
fi

echo -e "${YELLOW}⏳ Restarting data poller...${NC}"
sudo systemctl restart jarvis-poller.service
sleep 3

STATUS=$(systemctl is-active jarvis-poller.service)
if [ "$STATUS" = "active" ]; then
    echo -e "${GREEN}✅ Data poller running${NC}"
else
    echo -e "${RED}❌ Data poller FAILED${NC}"
    sudo journalctl -u jarvis-poller.service --no-pager -n 10
    exit 1
fi

echo ""
echo "════════════════════════════════════════════════════════"
echo -e "${GREEN}  ✅ BOT ONLINE — New code loaded${NC}"
echo "════════════════════════════════════════════════════════"
echo ""
echo "  Services:"
echo "    • jarvis-webhook   $(systemctl is-active jarvis-webhook.service)"
echo "    • jarvis-poller    $(systemctl is-active jarvis-poller.service)"
echo ""
echo "  Commands:"
echo "    Status:    sudo systemctl status jarvis-webhook jarvis-poller"
echo "    Logs:      sudo journalctl -u jarvis-webhook -f"
echo "    Restart:   bash restart_bot.sh"
echo "    Stop:      bash stop_bot.sh"
echo ""

# Quick health check
sleep 5
echo -e "${YELLOW}⏳ Health check...${NC}"
HEALTH=$(curl -s http://localhost:5000/health 2>/dev/null)
if echo "$HEALTH" | grep -q "running"; then
    echo -e "${GREEN}✅ Server healthy${NC}"
    echo "$HEALTH" | python3 -m json.tool 2>/dev/null
else
    echo -e "${RED}⚠️  Server not responding yet (may need 30s to load data)${NC}"
fi
echo ""
