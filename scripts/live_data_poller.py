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
import yfinance as yf
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Server configuration
WEBHOOK_URL = "http://localhost:5000/webhook"
WEBHOOK_SECRET = "your_secret_key_here"

# Currency pairs to track
PAIRS = ['EURUSD', 'GBPUSD']

# Free forex API endpoint (ExchangeRate-API.com - no API key needed)
API_BASE = "https://api.exchangerate-api.com/v4/latest/"

def fetch_current_price(base_currency='EUR', quote_currency='USD'):
    """Fetch current exchange rate."""
    try:
        url = f"{API_BASE}{base_currency}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            rates = data.get('rates')
            if rates is None:
                logger.error("API response missing 'rates' key")
                return None
            rate = rates.get(quote_currency)
            return rate
        else:
            logger.warning(f"API returned {response.status_code}")
            return None
    except requests.RequestException as e:
        logger.error(f"Network error fetching price: {e}")
        return None
    except (ValueError, KeyError) as e:
        logger.error(f"Invalid API response: {e}")
        return None


def generate_candle_from_price(price):
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


def fetch_real_historical_data(symbol, interval='5m', period='1d'):
    """
    Fetch real historical OHLCV data from yfinance.
    
    Args:
        symbol: Forex pair like 'EURUSD' or futures contract like '6E=F'
        interval: '5m', '1h', '1d', etc.
        period: '1d', '5d', '1mo', etc.
    
    Returns:
        List of candle dictionaries
    """
    try:
        # Map forex pairs to futures contracts
        symbol_map = {
            'EURUSD': '6E=F',  # Euro futures
            'GBPUSD': '6B=F',  # British Pound futures
            'USDJPY': '6J=F',  # Japanese Yen futures
            'AUDUSD': '6A=F'   # Australian Dollar futures
        }
        
        ticker_symbol = symbol_map.get(symbol, symbol)
        logger.info(f"  Fetching {interval} data for {ticker_symbol}...")
        
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period=period, interval=interval)
        
        if df.empty:
            logger.warning(f"  No data returned for {ticker_symbol}")
            return []
        
        # Convert to list of candles
        candles = []
        for idx, row in df.iterrows():
            candles.append({
                'time': int(idx.timestamp()),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': int(row['Volume']) if pd.notna(row['Volume']) else 1000
            })
        
        logger.info(f"  ✓ Fetched {len(candles)} real {interval} candles")
        return candles
        
    except Exception as e:
        logger.error(f"  Error fetching historical data: {e}")
        return []


def initial_data_load():
    """Load initial historical data from yfinance."""
    logger.info("Loading initial data (fetching REAL historical candles from yfinance)...")
    
    for pair in PAIRS:
        logger.info(f"Fetching data for {pair}...")
        
        # Fetch real historical data for each timeframe
        candles_5m = fetch_real_historical_data(pair, interval='5m', period='5d')
        candles_1h = fetch_real_historical_data(pair, interval='1h', period='1mo')
        candles_4h = fetch_real_historical_data(pair, interval='1h', period='3mo')  # Use 1h for 4h (yfinance limitation)
        
        if not candles_5m or not candles_1h or not candles_4h:
            logger.warning(f"Could not fetch complete data for {pair}, skipping...")
            continue
        
        # Send 5M candles (keep last 60)
        logger.info(f"  Sending {len(candles_5m[-60:])} real 5M candles...")
        for candle in candles_5m[-60:]:
            send_candle_to_webhook(pair, candle, '5M')
            time.sleep(0.02)
        
        # Send 1H candles (keep last 60)
        logger.info(f"  Sending {len(candles_1h[-60:])} real 1H candles...")
        for candle in candles_1h[-60:]:
            send_candle_to_webhook(pair, candle, '1H')
            time.sleep(0.02)
        
        # Send 4H candles (aggregate from 1H, keep last 60)
        logger.info("  Sending aggregated 4H candles from 1H data...")
        candles_4h_agg = []
        for i in range(0, len(candles_4h), 4):
            chunk = candles_4h[i:i+4]
            if len(chunk) == 4:
                candles_4h_agg.append({
                    'time': chunk[0]['time'],
                    'open': chunk[0]['open'],
                    'high': max(c['high'] for c in chunk),
                    'low': min(c['low'] for c in chunk),
                    'close': chunk[-1]['close'],
                    'volume': sum(c['volume'] for c in chunk)
                })
        
        for candle in candles_4h_agg[-60:]:
            send_candle_to_webhook(pair, candle, '4H')
            time.sleep(0.02)
        
        logger.info(f"✓ Completed {pair}")
    
    logger.info("Initial data load complete!")


def poll_live_data():
    """Poll for new prices and send to webhook."""
    logger.info("Starting live polling (10-second intervals with real prices)...")
    
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
            
            # Wait 10 seconds before next poll
            logger.info("Waiting 10 seconds for next update...")
            time.sleep(10)
            
        except KeyboardInterrupt:
            logger.info("Stopping poller...")
            break
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.error(f"Error in polling loop: {e}")
            time.sleep(30)  # Wait 30 seconds on error
        except Exception as e:
            logger.error(f"Unexpected error in polling loop: {e}", exc_info=True)
            time.sleep(30)


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
        response = requests.get("http://localhost:5000/health", timeout=5)
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
