#!/usr/bin/env python3
"""Quick test script to send sample market data to webhook server."""

import requests
import time
from datetime import datetime

# Webhook configuration
WEBHOOK_URL = "http://localhost:5000/webhook"
SECRET = "your_secret_key_here"

def send_candle(symbol, timeframe, timestamp, open_price, high_price, low_price, close_price):
    """Send a single candle to the webhook."""
    data = {
        "secret": SECRET,
        "symbol": symbol,
        "timeframe": timeframe,
        "time": int(timestamp),
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "volume": 1000
    }
    
    try:
        response = requests.post(WEBHOOK_URL, json=data)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def main():
    """Send sample candles to test the strategy."""
    print("📊 Testing TradingView Webhook with Sample Data")
    print("=" * 60)
    
    # Send 55 candles for each timeframe to meet the 50 candle requirement
    base_time = int(datetime.now().timestamp())
    base_price = 1.0800
    
    print("\n📈 Sending 4H candles...")
    for i in range(55):
        timestamp = base_time - (55 - i) * 14400  # 4 hours = 14400 seconds
        price = base_price + (i * 0.0005)
        result = send_candle("EURUSD", "4H", timestamp, price, price + 0.0010, price - 0.0005, price + 0.0003)
        if i % 10 == 0:
            print(f"  Sent {i+1}/55 candles - Status: {result.get('status', 'unknown')}")
        time.sleep(0.1)
    
    print("\n📈 Sending 1H candles...")
    for i in range(55):
        timestamp = base_time - (55 - i) * 3600  # 1 hour = 3600 seconds
        price = base_price + (i * 0.0002)
        result = send_candle("EURUSD", "1H", timestamp, price, price + 0.0008, price - 0.0003, price + 0.0002)
        if i % 10 == 0:
            print(f"  Sent {i+1}/55 candles - Status: {result.get('status', 'unknown')}")
        time.sleep(0.1)
    
    print("\n📈 Sending 5M candles...")
    for i in range(55):
        timestamp = base_time - (55 - i) * 300  # 5 minutes = 300 seconds
        price = base_price + (i * 0.00005)
        result = send_candle("EURUSD", "5M", timestamp, price, price + 0.0003, price - 0.0002, price + 0.0001)
        if i % 10 == 0:
            print(f"  Sent {i+1}/55 candles - Status: {result.get('status', 'unknown')}")
        time.sleep(0.1)
    
    print("\n✅ All candles sent!")
    print("\n🔍 Checking for signals...")
    
    try:
        response = requests.get("http://localhost:5000/signals")
        signals = response.json()
        print(f"\n📊 Strategy Analysis Results:")
        print(f"Status: {signals.get('status', 'unknown')}")
        
        if signals.get('signals'):
            for symbol, signal in signals['signals'].items():
                print(f"\n{symbol}:")
                if isinstance(signal, dict) and 'status' in signal:
                    print(f"  {signal}")
                else:
                    print(f"  Type: {signal.get('type', 'N/A')}")
                    print(f"  Entry: {signal.get('entry', 0):.5f}")
                    print(f"  Stop Loss: {signal.get('stop_loss', 0):.5f}")
                    print(f"  Take Profit: {signal.get('take_profit', 0):.5f}")
                    print(f"  Risk/Reward: 1:{signal.get('risk_reward', 0):.2f}")
        else:
            print("  No signals detected")
    except Exception as e:
        print(f"Error checking signals: {e}")
    
    print("\n" + "=" * 60)
    print("Test complete! Check logs/webhook.log for detailed analysis")

if __name__ == "__main__":
    main()
