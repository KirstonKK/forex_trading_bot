#!/bin/bash

# Forex Trading Bot Startup Script
# Launches webhook server + data poller + monitors for signals

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Bot directory
BOT_DIR="/home/juujuaddy/forex_trading_bot"
cd "$BOT_DIR"

echo ""
echo "========================================================================"
echo -e "${BLUE}FOREX TRADING BOT - ICT/SMC STRATEGY${NC}"
echo "========================================================================"
echo ""

# Check if venv exists
if [ ! -d "venv" ]; then
    echo -e "${RED}❌ Virtual environment not found${NC}"
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Kill existing processes
echo -e "${YELLOW}Stopping existing processes...${NC}"
pkill -f tradingview_webhook_server.py 2>/dev/null || true
pkill -f live_data_poller.py 2>/dev/null || true
sleep 2

# Create logs directory
mkdir -p logs

# Start webhook server
echo -e "${GREEN}✓ Starting webhook server (port 5000)...${NC}"
python scripts/tradingview_webhook_server.py > logs/webhook_startup.log 2>&1 &
WEBHOOK_PID=$!
sleep 3

# Check if webhook server started
if ps -p $WEBHOOK_PID > /dev/null; then
    echo -e "${GREEN}✓ Webhook server running (PID: $WEBHOOK_PID)${NC}"
else
    echo -e "${RED}❌ Webhook server failed to start${NC}"
    cat logs/webhook_startup.log
    exit 1
fi

# Start data poller
echo -e "${GREEN}✓ Starting live data poller (10-second intervals)...${NC}"
python scripts/live_data_poller.py > logs/poller_startup.log 2>&1 &
POLLER_PID=$!
sleep 5

# Check if poller started
if ps -p $POLLER_PID > /dev/null; then
    echo -e "${GREEN}✓ Data poller running (PID: $POLLER_PID)${NC}"
else
    echo -e "${RED}❌ Data poller failed to start${NC}"
    cat logs/poller_startup.log
    exit 1
fi

echo ""
echo "========================================================================"
echo -e "${GREEN}✓ SYSTEM ONLINE - Fetching Real Market Data${NC}"
echo "========================================================================"
echo ""
echo "📊 Data Source: yfinance (Real futures contracts: 6E=F, 6B=F, 6J=F, 6A=F)"
echo "⏱️  Update Frequency: Every 10 seconds"
echo "📈 Pairs Tracked: EURUSD, GBPUSD, USDJPY, AUDUSD"
echo "🎯 Strategy: ICT/SMC (HTF Structure + Order Blocks + BOS + ChoCH)"
echo ""
echo "Endpoints:"
echo "  • Dashboard:  http://localhost:5000"
echo "  • Health:     http://localhost:5000/health"
echo "  • Signals:    http://localhost:5000/signals"
echo "  • Data:       http://localhost:5000/data"
echo ""
echo "Process IDs:"
echo "  • Webhook Server: $WEBHOOK_PID"
echo "  • Data Poller:    $POLLER_PID"
echo ""
echo "Logs:"
echo "  • Webhook: tail -f logs/webhook.log"
echo "  • Poller:  tail -f logs/poller_startup.log"
echo ""
echo "========================================================================"
echo ""

# Wait for initial data load (about 30 seconds)
echo -e "${YELLOW}⏳ Loading initial historical data (30 seconds)...${NC}"
sleep 30

# Check for signals
echo -e "${YELLOW}Checking for trading signals...${NC}"
SIGNALS=$(curl -s http://localhost:5000/signals 2>/dev/null || echo "error")

if [[ $SIGNALS == *"error"* ]]; then
    echo -e "${RED}⚠️  Could not connect to server${NC}"
elif [[ $SIGNALS == *"no_setup"* ]]; then
    echo -e "${BLUE}📊 Bot analyzing market - No setups detected yet${NC}"
    echo "   (This is normal - strategy waits for high-probability ICT setups)"
else
    echo -e "${GREEN}🎯 SIGNAL DETECTED!${NC}"
    echo "$SIGNALS"
fi

echo ""
echo "========================================================================"
echo -e "${GREEN}✓ Bot is now monitoring markets 24/7${NC}"
echo ""
echo "To monitor signals in real-time:"
echo "  watch -n 5 'curl -s http://localhost:5000/signals | python3 -m json.tool'"
echo ""
echo "To stop the bot:"
echo "  bash stop_bot.sh"
echo ""
echo "To view live logs:"
echo "  tail -f logs/webhook.log"
echo "========================================================================"
echo ""
