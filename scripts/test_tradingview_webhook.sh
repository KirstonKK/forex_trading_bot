#!/bin/bash
# Quick test script for TradingView webhook

echo "Testing TradingView Webhook Server..."
echo ""

# Check if server is running
if ! curl -s http://localhost:5001/health > /dev/null; then
    echo "❌ Server not running. Start it with:"
    echo "   python3 scripts/tradingview_webhook_server.py"
    exit 1
fi

echo "✓ Server is running"
echo ""

# Send sample 5M candles
echo "Sending sample EURUSD 5M candles..."
for i in {1..55}; do
    PRICE=$(echo "1.0300 + $i * 0.0001" | bc -l)
    TIME=$((1736967000 + i * 300))
    
    curl -s -X POST http://localhost:5001/webhook \
      -H "Content-Type: application/json" \
      -d "{
        \"secret\": \"your_secret_key_here\",
        \"symbol\": \"EURUSD\",
        \"timeframe\": \"5M\",
        \"time\": $TIME,
        \"open\": $PRICE,
        \"high\": $(echo "$PRICE + 0.0005" | bc -l),
        \"low\": $(echo "$PRICE - 0.0005" | bc -l),
        \"close\": $(echo "$PRICE + 0.0002" | bc -l),
        \"volume\": 1000
      }" > /dev/null
    
    if [ $((i % 10)) -eq 0 ]; then
        echo "  Sent $i/55 candles..."
    fi
done

echo "✓ Sent 55 5M candles"
echo ""

# Send sample 1H candles
echo "Sending sample EURUSD 1H candles..."
for i in {1..55}; do
    PRICE=$(echo "1.0300 + $i * 0.0002" | bc -l)
    TIME=$((1736900000 + i * 3600))
    
    curl -s -X POST http://localhost:5001/webhook \
      -H "Content-Type: application/json" \
      -d "{
        \"secret\": \"your_secret_key_here\",
        \"symbol\": \"EURUSD\",
        \"timeframe\": \"1H\",
        \"time\": $TIME,
        \"open\": $PRICE,
        \"high\": $(echo "$PRICE + 0.0010" | bc -l),
        \"low\": $(echo "$PRICE - 0.0010" | bc -l),
        \"close\": $(echo "$PRICE + 0.0003" | bc -l),
        \"volume\": 5000
      }" > /dev/null
    
    if [ $((i % 10)) -eq 0 ]; then
        echo "  Sent $i/55 candles..."
    fi
done

echo "✓ Sent 55 1H candles"
echo ""

# Send sample 4H candles
echo "Sending sample EURUSD 4H candles..."
for i in {1..55}; do
    PRICE=$(echo "1.0300 + $i * 0.0003" | bc -l)
    TIME=$((1736800000 + i * 14400))
    
    curl -s -X POST http://localhost:5001/webhook \
      -H "Content-Type: application/json" \
      -d "{
        \"secret\": \"your_secret_key_here\",
        \"symbol\": \"EURUSD\",
        \"timeframe\": \"4H\",
        \"time\": $TIME,
        \"open\": $PRICE,
        \"high\": $(echo "$PRICE + 0.0020" | bc -l),
        \"low\": $(echo "$PRICE - 0.0020" | bc -l),
        \"close\": $(echo "$PRICE + 0.0005" | bc -l),
        \"volume\": 10000
      }" > /dev/null
    
    if [ $((i % 10)) -eq 0 ]; then
        echo "  Sent $i/55 candles..."
    fi
done

echo "✓ Sent 55 4H candles"
echo ""

# Check for signals
echo "Checking for trading signals..."
curl -s http://localhost:5001/signals | python3 -m json.tool

echo ""
echo "Done! Check logs/webhook.log for detailed analysis"
