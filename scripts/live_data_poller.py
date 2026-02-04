"""
Live Data Poller - Fetches real-time forex data and sends to webhook server
Uses free data sources (Alpha Vantage or direct polling) to simulate TradingView webhooks
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import requests
from datetime import datetime, timedelta, timezone
import logging
import json
import yfinance as yf
import pandas as pd

try:
    import pytz
    EST = pytz.timezone('America/New_York')
except ImportError:
    # Fallback: use fixed UTC offset for EST (-5 hours)
    EST = timezone(timedelta(hours=-5))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Server configuration
WEBHOOK_URL = "http://localhost:5000/webhook"
WEBHOOK_SECRET = "your_secret_key_here"

# Currency pairs to track
PAIRS = ['EURUSD', 'GBPUSD', 'XAUUSD']


def is_forex_market_open():
    """
    Check if forex markets are currently open.
    Forex markets are open from Sunday 5pm EST to Friday 5pm EST.
    Returns: (is_open: bool, next_open: datetime or None, message: str)
    """
    now_est = datetime.now(EST)
    weekday = now_est.weekday()  # Monday=0, Sunday=6
    hour = now_est.hour
    
    # Market is CLOSED:
    # - Friday after 5pm EST (weekday=4, hour >= 17)
    # - All day Saturday (weekday=5)
    # - Sunday before 5pm EST (weekday=6, hour < 17)
    
    if weekday == 4 and hour >= 17:  # Friday after 5pm
        # Calculate time until Sunday 5pm
        days_until_sunday = 2
        next_open = now_est.replace(hour=17, minute=0, second=0, microsecond=0) + timedelta(days=days_until_sunday)
        return False, next_open, "Market closed (Friday 5pm EST)"
    
    elif weekday == 5:  # Saturday
        # Calculate time until Sunday 5pm
        days_until_sunday = 1
        next_open = now_est.replace(hour=17, minute=0, second=0, microsecond=0) + timedelta(days=days_until_sunday)
        return False, next_open, "Market closed (Weekend - Saturday)"
    
    elif weekday == 6 and hour < 17:  # Sunday before 5pm
        next_open = now_est.replace(hour=17, minute=0, second=0, microsecond=0)
        return False, next_open, "Market closed (Sunday before 5pm EST)"
    
    # Market is open
    return True, None, "Market is open"


def wait_for_market_open():
    """
    Sleep until forex market opens. Logs status every hour while waiting.
    """
    is_open, next_open, message = is_forex_market_open()
    
    if is_open:
        return True
    
    logger.info(f"🌙 {message}")
    
    if next_open:
        time_until_open = (next_open - datetime.now(EST)).total_seconds()
        hours_until = time_until_open / 3600
        logger.info(f"⏰ Market opens at {next_open.strftime('%A %I:%M %p EST')} ({hours_until:.1f} hours)")
        logger.info("💤 Entering weekend sleep mode...")
        
        # Sleep in 1-hour chunks so we can log status
        while time_until_open > 0:
            sleep_time = min(3600, time_until_open)  # Sleep max 1 hour at a time
            time.sleep(sleep_time)
            time_until_open -= sleep_time
            
            if time_until_open > 0:
                hours_left = time_until_open / 3600
                logger.info(f"💤 Still waiting... {hours_left:.1f} hours until market opens")
        
        logger.info("🌅 Market is opening! Resuming polling...")
    
    return True

# Use yfinance for real-time forex futures data
import yfinance as yf

def fetch_current_price(base_currency='EUR', quote_currency='USD'):
    """Fetch real-time forex price from yfinance futures."""
    # Map to futures contracts for real-time data
    pair = f"{base_currency}{quote_currency}"
    symbol_map = {
        'EURUSD': '6E=F',   # Euro futures
        'GBPUSD': '6B=F',   # British Pound futures
        'USDJPY': '6J=F',   # Yen futures
        'AUDUSD': '6A=F',   # AUD futures
        'XAUUSD': 'GC=F',   # Gold futures
    }
    
    ticker_symbol = symbol_map.get(pair)
    if not ticker_symbol:
        return None
    
    try:
        ticker = yf.Ticker(ticker_symbol)
        # Get latest data
        hist = ticker.history(period='1d', interval='1m')
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])
            return price
        return None
        
    except Exception as e:
        logger.error(f"Error fetching {pair}: {e}")
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
        **candle  # Unpack all candle fields (time, open, high, low, close, volume)
    }
    
    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=5)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.warning(f"Webhook error for {symbol_name}: {e}")
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
            'AUDUSD': '6A=F',  # Australian Dollar futures
            'XAUUSD': 'GC=F'   # Gold futures
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
    """Load initial historical data from yfinance - 4H, 1H, 15M, 5M."""
    logger.info("Loading initial data (fetching REAL historical candles from yfinance)...")
    logger.info("Timeframes: 4H, 1H, 15M, 5M")
    
    for pair in PAIRS:
        logger.info(f"Fetching data for {pair}...")
        
        # Fetch real historical data for each timeframe
        candles_5m = fetch_real_historical_data(pair, interval='5m', period='5d')
        candles_15m = fetch_real_historical_data(pair, interval='15m', period='5d')
        candles_1h = fetch_real_historical_data(pair, interval='1h', period='1mo')
        candles_4h_raw = fetch_real_historical_data(pair, interval='1h', period='3mo')  # Aggregate to 4H
        
        if not candles_5m or not candles_15m or not candles_1h or not candles_4h_raw:
            logger.warning(f"Could not fetch complete data for {pair}, skipping...")
            continue
        
        # Send 5M candles (keep last 100)
        logger.info(f"  Sending {len(candles_5m[-100:])} real 5M candles...")
        for candle in candles_5m[-100:]:
            send_candle_to_webhook(pair, candle, '5M')
            time.sleep(0.01)
        
        # Send 15M candles (keep last 100)
        logger.info(f"  Sending {len(candles_15m[-100:])} real 15M candles...")
        for candle in candles_15m[-100:]:
            send_candle_to_webhook(pair, candle, '15M')
            time.sleep(0.01)
        
        # Send 1H candles (keep last 100)
        logger.info(f"  Sending {len(candles_1h[-100:])} real 1H candles...")
        for candle in candles_1h[-100:]:
            send_candle_to_webhook(pair, candle, '1H')
            time.sleep(0.01)
        
        # Send 4H candles (aggregate from 1H, keep last 100)
        logger.info("  Aggregating and sending 4H candles...")
        candles_4h_agg = []
        for i in range(0, len(candles_4h_raw), 4):
            chunk = candles_4h_raw[i:i+4]
            if len(chunk) == 4:
                candles_4h_agg.append({
                    'time': chunk[0]['time'],
                    'open': chunk[0]['open'],
                    'high': max(c['high'] for c in chunk),
                    'low': min(c['low'] for c in chunk),
                    'close': chunk[-1]['close'],
                    'volume': sum(c['volume'] for c in chunk)
                })
        
        for candle in candles_4h_agg[-100:]:
            send_candle_to_webhook(pair, candle, '4H')
            time.sleep(0.01)
        
        logger.info(f"✓ Completed {pair} (4H:{len(candles_4h_agg[-100:])}, 1H:{len(candles_1h[-100:])}, 15M:{len(candles_15m[-100:])}, 5M:{len(candles_5m[-100:])})")
    
    logger.info("Initial data load complete! All timeframes loaded.")


def poll_live_data():
    """Poll for new prices and send to webhook - ALL TIMEFRAMES."""
    logger.info("Starting live polling with MULTI-TIMEFRAME updates...")
    
    last_15m_update = {}
    last_1h_update = {}
    last_4h_update = {}
    
    while True:
        try:
            # Check if forex market is open (weekday detection)
            is_open, next_open, message = is_forex_market_open()
            if not is_open:
                wait_for_market_open()
                # Reset update timers after weekend
                last_15m_update = {}
                last_1h_update = {}
                last_4h_update = {}
                continue
            
            for pair in PAIRS:
                # Parse currency pair
                base = pair[:3]
                quote = pair[3:6]
                
                # Fetch current price from yfinance (real-time)
                price = fetch_current_price(base, quote)
                
                if price:
                    logger.info(f"Current {pair}: {price:.5f}")
                    
                    # Always send 5M candle (every poll)
                    candle = generate_candle_from_price(price)
                    send_candle_to_webhook(pair, candle, '5M')
                    
                    now = time.time()
                    
                    # Fetch fresh 15M data every 2 minutes
                    if pair not in last_15m_update or (now - last_15m_update[pair]) > 120:
                        candles_15m = fetch_real_historical_data(pair, interval='15m', period='5d')
                        if candles_15m:
                            for c in candles_15m[-3:]:
                                send_candle_to_webhook(pair, c, '15M')
                            last_15m_update[pair] = now
                            logger.info(f"  📊 Updated 15M data for {pair}")
                    
                    # Fetch fresh 1H data every 5 minutes
                    if pair not in last_1h_update or (now - last_1h_update[pair]) > 300:
                        candles_1h = fetch_real_historical_data(pair, interval='1h', period='5d')
                        if candles_1h:
                            for c in candles_1h[-3:]:
                                send_candle_to_webhook(pair, c, '1H')
                            last_1h_update[pair] = now
                            logger.info(f"  📊 Updated 1H data for {pair}")
                    
                    # Fetch fresh 4H data every 20 minutes
                    if pair not in last_4h_update or (now - last_4h_update[pair]) > 1200:
                        candles_1h_for_4h = fetch_real_historical_data(pair, interval='1h', period='1mo')
                        if candles_1h_for_4h:
                            # Aggregate to 4H
                            candles_4h = []
                            for i in range(0, len(candles_1h_for_4h), 4):
                                chunk = candles_1h_for_4h[i:i+4]
                                if len(chunk) == 4:
                                    candles_4h.append({
                                        'time': chunk[0]['time'],
                                        'open': chunk[0]['open'],
                                        'high': max(c['high'] for c in chunk),
                                        'low': min(c['low'] for c in chunk),
                                        'close': chunk[-1]['close'],
                                        'volume': sum(c['volume'] for c in chunk)
                                    })
                            for c in candles_4h[-3:]:
                                send_candle_to_webhook(pair, c, '4H')
                            last_4h_update[pair] = now
                            logger.info(f"  📊 Updated 4H data for {pair}")
                else:
                    logger.warning(f"Could not fetch price for {pair}")
            
            # Wait 5 seconds before next poll (faster updates)
            time.sleep(5)
            
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
    print("Fetching real-time forex rates from yfinance")
    print(f"Sending to: {WEBHOOK_URL}")
    print(f"Tracking: {', '.join(PAIRS)}")
    
    # Show market status
    is_open, next_open, message = is_forex_market_open()
    if is_open:
        print("📈 Market Status: OPEN")
    else:
        print(f"🌙 Market Status: CLOSED - {message}")
        if next_open:
            print(f"⏰ Opens: {next_open.strftime('%A %I:%M %p EST')}")
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
