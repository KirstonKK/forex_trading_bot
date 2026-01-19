"""
Live Data Poller - Fetches real-time forex data and sends to webhook server
Uses free data sources (Alpha Vantage or direct polling) to simulate TradingView webhooks
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import requests
from datetime import datetime, timedelta
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Server configuration
WEBHOOK_URL = "http://localhost:5001/webhook"
WEBHOOK_SECRET = "your_secret_key_here"

# Currency pairs to track
PAIRS = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD']

# Free forex API endpoint (12Forex.com - no API key needed)
API_BASE = "https://api.exchangerate-api.com/v4/latest/"

def fetch_current_price(base_currency='EUR', quote_currency='USD'):
    """Fetch current exchange rate."""
    try:
        url = f"{API_BASE}{base_currency}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            rate = data['rates'].get(quote_currency)
            return rate
        else:
            logger.warning(f"API returned {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error fetching price: {e}")
        return None


def generate_candle_from_price(price, timeframe='5M'):
    """Generate a synthetic candle from current price."""
    # Add small variations to simulate OHLC
    variation = price * 0.0002  # 0.02% variation
    
    return {
        'time': int(datetime.now().timestamp()),
        'open': round(price - variation * 0.5, 5),
        'high': round(price + variation, 5),
        'low': round(price - variation, 5),
        'close': round(price, 5),
        'volume': 1000
    }


def send_candle_to_webhook(symbol_name, candle, timeframe):
    """Send candle data to webhook server."""
    payload = {
        "secret": WEBHOOK_SECRET,
        "symbol": symbol_name,
        "timeframe": timeframe,
        "time": candle['time'],
        "open": candle['open'],
        "high": candle['high'],
        "low": candle['low'],
        "close": candle['close'],
        "volume": candle['volume']
    }
    
    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=5)
        if response.status_code == 200:
            return True
        else:
            logger.warning(f"Webhook returned {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending webhook: {e}")
        return False


def initial_data_load():
    """Load initial historical data by generating synthetic candles."""
    logger.info("Loading initial data (generating synthetic historical candles)...")
    
    for pair in PAIRS:
        logger.info(f"Generating data for {pair}...")
        
        # Parse currency pair
        base = pair[:3]
        quote = pair[3:6]
        
        # Get current price
        current_price = fetch_current_price(base, quote)
        if not current_price:
            logger.warning(f"Could not fetch price for {pair}, skipping...")
            continue
        
        logger.info(f"  Current {pair} price: {current_price:.5f}")
        
        # Generate 60 historical 5M candles
        logger.info(f"  Sending 60 synthetic 5M candles...")
        base_time = int(datetime.now().timestamp()) - (60 * 300)  # 60 candles * 5 minutes
        for i in range(60):
            candle_price = current_price * (1 + (i - 30) * 0.0001)  # Slight price walk
            candle = generate_candle_from_price(candle_price, '5M')
            candle['time'] = base_time + (i * 300)
            send_candle_to_webhook(pair, candle, '5M')
            time.sleep(0.05)
        
        # Generate 60 historical 1H candles
        logger.info(f"  Sending 60 synthetic 1H candles...")
        base_time = int(datetime.now().timestamp()) - (60 * 3600)  # 60 hours
        for i in range(60):
            candle_price = current_price * (1 + (i - 30) * 0.0002)
            candle = generate_candle_from_price(candle_price, '1H')
            candle['time'] = base_time + (i * 3600)
            send_candle_to_webhook(pair, candle, '1H')
            time.sleep(0.05)
        
        # Generate 60 historical 4H candles
        logger.info(f"  Sending 60 synthetic 4H candles...")
        base_time = int(datetime.now().timestamp()) - (60 * 14400)  # 60 * 4 hours
        for i in range(60):
            candle_price = current_price * (1 + (i - 30) * 0.0003)
            candle = generate_candle_from_price(candle_price, '4H')
            candle['time'] = base_time + (i * 14400)
            send_candle_to_webhook(pair, candle, '4H')
            time.sleep(0.05)
        
        logger.info(f"✓ Completed {pair}")
    
    logger.info("Initial data load complete!")


def poll_live_data():
    """Poll for new prices and send to webhook."""
    logger.info("Starting live polling (1-minute intervals with real prices)...")
    
    while True:
        try:
            for pair in PAIRS:
                # Parse currency pair
                base = pair[:3]
                quote = pair[3:6]
                
                # Fetch current price
                price = fetch_current_price(base, quote)
                
                if price:
                    logger.info(f"Current {pair}: {price:.5f}")
                    
                    # Generate and send 5M candle
                    candle = generate_candle_from_price(price, '5M')
                    send_candle_to_webhook(pair, candle, '5M')
                else:
                    logger.warning(f"Could not fetch price for {pair}")
            
            # Wait 1 minute before next poll (can adjust frequency)
            logger.info("Waiting 60 seconds for next update...")
            time.sleep(60)
            
        except KeyboardInterrupt:
            logger.info("Stopping poller...")
            break
        except Exception as e:
            logger.error(f"Error in polling loop: {e}")
            time.sleep(30)  # Wait 30 seconds on error


if __name__ == '__main__':
    print("\n" + "="*70)
    print("LIVE FOREX DATA POLLER")
    print("="*70)
    print("Fetching real-time forex rates from exchangerate-api.com")
    print(f"Sending to: {WEBHOOK_URL}")
    print(f"Tracking: {', '.join(PAIRS)}")
    print("="*70 + "\n")
    
    # Check if server is running
    try:
        response = requests.get("http://localhost:5001/health", timeout=5)
        if response.status_code == 200:
            logger.info("✓ Webhook server is running")
        else:
            logger.error("Webhook server returned unexpected status")
            sys.exit(1)
    except:
        logger.error("❌ Webhook server is not running!")
        logger.error("Start it with: python3 scripts/tradingview_webhook_server.py")
        sys.exit(1)
    
    # Load initial historical data
    initial_data_load()
    
    # Start live polling
    poll_live_data()
