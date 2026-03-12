"""
Live Data Poller - FALLBACK ONLY
Primary: TradingView webhooks (real exchange data)
Fallback: yfinance polling (only if TradingView data is stale)
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

from integrations.news_filter import is_reduced_liquidity_day

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Server configuration
WEBHOOK_URL = "http://localhost:5000/webhook"
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "").strip()
if not WEBHOOK_SECRET:
    raise RuntimeError("WEBHOOK_SECRET is required. Set WEBHOOK_SECRET environment variable.")
HEALTH_URL = "http://localhost:5000/health"
DATA_URL = "http://localhost:5000/data"

# Currency pairs to track (XAU_USD removed 2026-03-12: 17.6% WR, -1755 pips)
PAIRS = ['EURUSD', 'GBPUSD']

# Data freshness threshold (seconds)
STALE_DATA_THRESHOLD = 300  # 5 minutes


def is_forex_market_open():
    """
    Check if forex markets are currently open.
    Forex markets are open from Sunday 5pm EST to Friday 5pm EST.
    Also checks for bank holidays (reduced liquidity days).
    Returns: (is_open: bool, next_open: datetime or None, message: str)
    """
    now_est = datetime.now(EST)
    weekday = now_est.weekday()  # Monday=0, Sunday=6
    hour = now_est.hour
    
    # ── Bank holiday check ──
    is_holiday, holiday_name = is_reduced_liquidity_day(now_est.date())
    if is_holiday:
        # Calculate next trading day (skip to tomorrow, recheck then)
        next_open = now_est.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return False, next_open, f"Market skip: {holiday_name} — reduced liquidity"
    
    # ── Weekend check ──
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

# Use yfinance for real OHLCV data (no more single-tick fake candles)
import yfinance as yf


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
        
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period=period, interval=interval)
        
        if df.empty:
            logger.warning(f"  No data returned for {ticker_symbol} ({interval})")
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
    """Poll for real OHLCV candles across ALL timeframes from yfinance."""
    logger.info("Starting live polling with REAL CANDLE DATA on all timeframes...")
    
    last_5m_update = {}
    last_15m_update = {}
    last_1h_update = {}
    last_4h_update = {}
    
    # Track last candle timestamps to detect new candles
    last_5m_candle_time = {}
    last_15m_candle_time = {}
    last_1h_candle_time = {}
    last_4h_candle_time = {}
    
    while True:
        try:
            # Check if forex market is open (weekday detection)
            is_open, next_open, message = is_forex_market_open()
            if not is_open:
                wait_for_market_open()
                # Reset update timers after weekend
                last_5m_update = {}
                last_15m_update = {}
                last_1h_update = {}
                last_4h_update = {}
                last_5m_candle_time = {}
                last_15m_candle_time = {}
                last_1h_candle_time = {}
                last_4h_candle_time = {}
                continue
            
            for pair in PAIRS:
                now = time.time()
                
                # ===== REAL 5M candles every 30 seconds =====
                # (5M candles close every 5 min, polling every 30s catches them promptly)
                if pair not in last_5m_update or (now - last_5m_update[pair]) > 30:
                    candles_5m = fetch_real_historical_data(pair, interval='5m', period='5d')
                    if candles_5m:
                        # Only send candles newer than what we last sent
                        prev_time = last_5m_candle_time.get(pair, 0)
                        new_candles = [c for c in candles_5m if c['time'] > prev_time]
                        
                        if new_candles:
                            # Send the latest real candles (last 3 new ones max to avoid spam)
                            for c in new_candles[-3:]:
                                send_candle_to_webhook(pair, c, '5M')
                            last_5m_candle_time[pair] = candles_5m[-1]['time']
                            logger.info(f"Current {pair}: {candles_5m[-1]['close']:.5f} (5M real candle)")
                        else:
                            # No new candle yet, just log current price
                            logger.info(f"Current {pair}: {candles_5m[-1]['close']:.5f}")
                        
                        last_5m_update[pair] = now
                    else:
                        logger.warning(f"Could not fetch 5M data for {pair}")
                
                # ===== REAL 15M candles every 2 minutes =====
                if pair not in last_15m_update or (now - last_15m_update[pair]) > 120:
                    candles_15m = fetch_real_historical_data(pair, interval='15m', period='5d')
                    if candles_15m:
                        prev_time = last_15m_candle_time.get(pair, 0)
                        new_candles = [c for c in candles_15m if c['time'] > prev_time]
                        if new_candles:
                            for c in new_candles[-3:]:
                                send_candle_to_webhook(pair, c, '15M')
                            last_15m_candle_time[pair] = candles_15m[-1]['time']
                            logger.info(f"  📊 Updated 15M data for {pair} ({len(new_candles)} new candles)")
                        last_15m_update[pair] = now
                
                # ===== REAL 1H candles every 5 minutes =====
                if pair not in last_1h_update or (now - last_1h_update[pair]) > 300:
                    candles_1h = fetch_real_historical_data(pair, interval='1h', period='5d')
                    if candles_1h:
                        prev_time = last_1h_candle_time.get(pair, 0)
                        new_candles = [c for c in candles_1h if c['time'] > prev_time]
                        if new_candles:
                            for c in new_candles[-3:]:
                                send_candle_to_webhook(pair, c, '1H')
                            last_1h_candle_time[pair] = candles_1h[-1]['time']
                            logger.info(f"  📊 Updated 1H data for {pair} ({len(new_candles)} new candles)")
                        last_1h_update[pair] = now
                
                # ===== REAL 4H candles every 20 minutes =====
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
                        if candles_4h:
                            prev_time = last_4h_candle_time.get(pair, 0)
                            new_candles = [c for c in candles_4h if c['time'] > prev_time]
                            if new_candles:
                                for c in new_candles[-3:]:
                                    send_candle_to_webhook(pair, c, '4H')
                                last_4h_candle_time[pair] = candles_4h[-1]['time']
                                logger.info(f"  📊 Updated 4H data for {pair} ({len(new_candles)} new candles)")
                        last_4h_update[pair] = now
            
            # Wait 30 seconds between polls (aligned with 5M candle detection)
            time.sleep(30)
            
        except KeyboardInterrupt:
            logger.info("Stopping poller...")
            break
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.error(f"Error in polling loop: {e}")
            time.sleep(30)  # Wait 30 seconds on error
        except Exception as e:
            logger.error(f"Unexpected error in polling loop: {e}", exc_info=True)
            time.sleep(30)


def check_tradingview_data():
    """Check if TradingView is sending recent data."""
    try:
        response = requests.get(DATA_URL, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('symbols'):
                # Check if any data is recent (within last 5 minutes)
                now = time.time()
                for symbol_data in data['symbols'].values():
                    if symbol_data.get('candles'):
                        for tf_candles in symbol_data['candles'].values():
                            if tf_candles:
                                latest = max(c.get('timestamp', 0) for c in tf_candles)
                                age = now - latest
                                if age < STALE_DATA_THRESHOLD:
                                    return True, age
                return False, None
    except:
        pass
    return False, None


if __name__ == '__main__':
    print("\n" + "="*70)
    print("LIVE FOREX DATA POLLER - FALLBACK MODE")
    print("="*70)
    print("PRIMARY: TradingView webhooks (real exchange data)")
    print("FALLBACK: yfinance polling (if TradingView data is stale)")
    print(f"Webhook URL: {WEBHOOK_URL}")
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
        response = requests.get(HEALTH_URL, timeout=5)
        if response.status_code == 200:
            logger.info("✓ Webhook server is running")
        else:
            logger.error("Webhook server returned unexpected status")
            sys.exit(1)
    except:
        logger.error("❌ Webhook server is not running!")
        logger.error("Start it with: python3 scripts/tradingview_webhook_server.py")
        sys.exit(1)
    
    # Check if TradingView is already providing data
    has_tv_data, data_age = check_tradingview_data()
    if has_tv_data:
        logger.info(f"✅ TradingView is ACTIVE (data is {data_age:.0f}s old)")
        logger.info("📺 Poller will run in MONITORING mode only")
        logger.info("💡 TradingView webhooks are primary data source")
        # Still poll but at much slower rate to fill gaps
        while True:
            time.sleep(60)  # Check every minute
            has_tv, age = check_tradingview_data()
            if not has_tv or age > STALE_DATA_THRESHOLD:
                logger.warning("⚠️ TradingView data is stale, activating fallback polling...")
                break
    else:
        logger.warning("⚠️ No recent TradingView data found")
        logger.info("🔄 Activating yfinance fallback polling...")
    
    # Load initial historical data
    try:
        initial_data_load()
    except Exception as e:
        logger.error(f"❌ Failed to load initial data: {e}")
        logger.info("Continuing with live polling only...")
    
    # Start live polling
    poll_live_data()
