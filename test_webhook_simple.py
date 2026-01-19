#!/usr/bin/env python3
"""
Simple test to send sample market data to the webhook server.
This simulates real TradingView data to test your strategy.
"""

import requests
import json
import time
from datetime import datetime, timedelta

# Server URL
BASE_URL = "http://127.0.0.1:5000"

# Sample data configuration
SECRET = "your_secret_key_here"
SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD"]

def send_candle(symbol, timeframe, timestamp, open_price, high, low, close, volume=1000):
    """Send a single candle to the webhook."""
    data = {
        "secret": SECRET,
        "symbol": symbol,
        "timeframe": timeframe,
        "time": int(timestamp),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume
    }
    
    try:
        response = requests.post(f"{BASE_URL}/webhook", json=data, timeout=5)
        return response.json()
    except Exception as e:
        print(f"Error sending candle: {e}")
        return None

def generate_realistic_candles(base_price, count, volatility=0.001):
    """Generate realistic-looking candle data."""
    candles = []
    price = base_price
    
    for i in range(count):
        # Simulate some price movement
        change = (i % 7 - 3) * volatility  # Zigzag pattern
        open_price = price
        close_price = price + change
        high = max(open_price, close_price) + abs(change) * 0.3
        low = min(open_price, close_price) - abs(change) * 0.3
        
        candles.append({
            'open': open_price,
            'high': high,
            'low': low,
            'close': close_price
        })
        
        price = close_price
    
    return candles

def main():
    print("=" * 70)
    print("TESTING TRADINGVIEW WEBHOOK WITH SAMPLE DATA")
    print("=" * 70)
    
    # Check server health
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"✓ Server is running: {response.json()['status']}")
        print()
    except Exception as e:
        print(f"✗ Server not responding: {e}")
        print("Make sure the webhook server is running!")
        return
    
    # Generate sample data for EURUSD
    symbol = "EURUSD"
    print(f"Sending sample data for {symbol}...")
    print()
    
    # Start timestamp (simulate last few hours)
    now = datetime.now()
    
    # Generate and send 4H candles (need 50+)
    print("Sending 4H timeframe candles...")
    candles_4h = generate_realistic_candles(1.0800, 55, volatility=0.003)
    timestamp_4h = int((now - timedelta(hours=55*4)).timestamp())
    
    for i, candle in enumerate(candles_4h):
        result = send_candle(
            symbol, "4H",
            timestamp_4h + i * 14400,  # 4 hours in seconds
            candle['open'], candle['high'], candle['low'], candle['close']
        )
        if (i + 1) % 10 == 0:
            print(f"  Sent {i + 1}/55 candles")
    print(f"✓ Sent 55 4H candles")
    print()
    
    # Generate and send 1H candles (need 50+)
    print("Sending 1H timeframe candles...")
    candles_1h = generate_realistic_candles(1.0800, 55, volatility=0.001)
    timestamp_1h = int((now - timedelta(hours=55)).timestamp())
    
    for i, candle in enumerate(candles_1h):
        result = send_candle(
            symbol, "1H",
            timestamp_1h + i * 3600,  # 1 hour in seconds
            candle['open'], candle['high'], candle['low'], candle['close']
        )
        if (i + 1) % 10 == 0:
            print(f"  Sent {i + 1}/55 candles")
    print(f"✓ Sent 55 1H candles")
    print()
    
    # Generate and send 5M candles (need 50+) with a potential setup
    print("Sending 5M timeframe candles...")
    candles_5m = generate_realistic_candles(1.0810, 55, volatility=0.0002)
    timestamp_5m = int((now - timedelta(minutes=55*5)).timestamp())
    
    for i, candle in enumerate(candles_5m):
        result = send_candle(
            symbol, "5M",
            timestamp_5m + i * 300,  # 5 minutes in seconds
            candle['open'], candle['high'], candle['low'], candle['close']
        )
        if (i + 1) % 10 == 0:
            print(f"  Sent {i + 1}/55 candles")
        
        # Check the last response for signals
        if result and i == len(candles_5m) - 1:
            print(f"\n✓ Sent 55 5M candles")
            print()
            print("=" * 70)
            print("FINAL RESULT:")
            print("=" * 70)
            print(json.dumps(result, indent=2))
            print()
            
            if result.get('status') == 'signal_detected':
                signal = result.get('signal', {})
                print("🎯 SIGNAL DETECTED!")
                print(f"   Symbol: {symbol}")
                print(f"   Type: {signal.get('type')}")
                print(f"   Entry: {signal.get('entry'):.5f}")
                print(f"   Stop Loss: {signal.get('stop_loss'):.5f}")
                print(f"   Take Profit: {signal.get('take_profit'):.5f}")
                print(f"   Risk/Reward: 1:{signal.get('risk_reward'):.2f}")
            elif result.get('status') == 'no_signal':
                print("ℹ️  No signal - waiting for setup")
            elif result.get('status') == 'collecting_data':
                print("ℹ️  Still collecting data")
                print(f"   Candles: {result.get('candles')}")
    
    print()
    print("=" * 70)
    print("Test complete! Check the webhook server logs for details.")
    print("=" * 70)

if __name__ == "__main__":
    main()
