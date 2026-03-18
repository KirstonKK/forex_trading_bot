"""
Live Data Poller - Multi-Source OHLCV Data
Sources (tried in order):
1. yfinance (free, no API key)
2. Twelve Data (free tier, 800/day — requires TWELVE_DATA_API_KEY)
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import requests
from datetime import datetime, timedelta, timezone
import logging
import json
import pandas as pd

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

from connectors.twelve_data import TwelveDataConnector

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
# US30 added 2026-03-17: 66.7% WR, PF 5.08 in 60-day backtest (NYSE open only 13-15 UTC)
PAIRS = ['EURUSD', 'GBPUSD', 'US30']

# Data freshness threshold (seconds)
STALE_DATA_THRESHOLD = 300  # 5 minutes

# Initialize Twelve Data connector (fallback when yfinance fails)
twelve_data = TwelveDataConnector()
if twelve_data.available:
    logger.info("✓ Twelve Data connector ready (fallback data source)")
else:
    logger.warning("⚠ Twelve Data API key not set — only yfinance available")
    logger.warning("  Set TWELVE_DATA_API_KEY in forex-bot.env for fallback data")

# Track which source is working for each symbol
# 'yfinance' or 'twelvedata'
_symbol_source: dict = {}
# Track consecutive yfinance failures per symbol
_yf_fail_count: dict = {}

# Polling intervals (seconds) per data source
# yfinance: aggressive — unlimited API, catch candle closes quickly
# Twelve Data: conservative — 800 calls/day budget
#   3 pairs × (132 + 88 + 22 + 6) = 3 × 248 = 744 calls/day ≈ headroom
_POLL_INTERVALS = {
    'yfinance':   {'5m': 30,   '15m': 120,  '1h': 300,  '4h': 1200},
    'twelvedata': {'5m': 600,  '15m': 900,  '1h': 3600, '4h': 14400},
}

def _poll_interval(pair, timeframe):
    """Get polling interval in seconds based on active data source."""
    source = _symbol_source.get(pair, 'yfinance')
    return _POLL_INTERVALS.get(source, _POLL_INTERVALS['yfinance'])[timeframe]


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

# Multi-source data fetching


def _fetch_yfinance(symbol, interval='5m', period='1d'):
    """Fetch candles from yfinance. Returns list of candle dicts or empty list."""
    if not YFINANCE_AVAILABLE:
        return []
    
    symbol_map = {
        'EURUSD': 'EURUSD=X',
        'GBPUSD': 'GBPUSD=X',
        'USDJPY': 'USDJPY=X',
        'AUDUSD': 'AUDUSD=X',
        'XAUUSD': 'GC=F',
        'US30':   'YM=F',
        'US_30':  'YM=F',
    }
    
    ticker_symbol = symbol_map.get(symbol, symbol)
    
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period=period, interval=interval)
        
        if df.empty:
            return []
        
        candles = []
        timestamps = df.index.astype('int64') // 10**9
        for i in range(len(df)):
            row = df.iloc[i]
            candles.append({
                'time': int(timestamps[i]),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': int(row['Volume']) if pd.notna(row['Volume']) else 1000
            })
        return candles
    except Exception:
        return []


def _fetch_twelvedata(symbol, interval='5m', period='1d'):
    """Fetch candles from Twelve Data. Returns list of candle dicts or empty list."""
    if not twelve_data.available:
        return []
    
    # Map yfinance period to Twelve Data outputsize
    period_to_size = {
        '1d':  30,    # ~30 candles for 5m in a day
        '5d':  100,
        '1mo': 200,
        '3mo': 500,
    }
    outputsize = period_to_size.get(period, 100)
    
    # Map yfinance interval names to our connector's format
    interval_map = {
        '5m':  '5m',
        '15m': '15m',
        '1h':  '1h',
        '4h':  '4h',
        '1d':  '1d',
    }
    td_interval = interval_map.get(interval, interval)
    
    return twelve_data.fetch_candles(symbol, interval=td_interval, outputsize=outputsize)


def fetch_real_historical_data(symbol, interval='5m', period='1d'):
    """
    Fetch OHLCV candle data, trying yfinance first then Twelve Data.
    
    Auto-tracks which source works per symbol and skips broken sources
    to avoid wasting time on repeated failures.
    """
    global _symbol_source, _yf_fail_count
    
    source = _symbol_source.get(symbol)
    yf_fails = _yf_fail_count.get(symbol, 0)
    
    # If yfinance has failed 3+ times for this symbol, skip it
    try_yfinance = (source != 'twelvedata') and (yf_fails < 3)
    
    if try_yfinance:
        candles = _fetch_yfinance(symbol, interval, period)
        if candles:
            if source != 'yfinance':
                logger.info(f"  📡 {symbol}: using yfinance")
                _symbol_source[symbol] = 'yfinance'
            _yf_fail_count[symbol] = 0
            return candles
        else:
            _yf_fail_count[symbol] = yf_fails + 1
            if _yf_fail_count[symbol] >= 3:
                logger.warning(f"  ⚠ {symbol}: yfinance failed 3x, switching to Twelve Data")
    
    # Fallback to Twelve Data
    candles = _fetch_twelvedata(symbol, interval, period)
    if candles:
        if source != 'twelvedata':
            logger.info(f"  📡 {symbol}: using Twelve Data (yfinance unavailable)")
            _symbol_source[symbol] = 'twelvedata'
        return candles
    
    # Both sources failed
    if source:
        logger.error(f"  ❌ {symbol}: all data sources failed for {interval}")
    return []


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


def initial_data_load():
    """Load initial historical data - 4H, 1H, 15M, 5M."""
    logger.info("Loading initial data (fetching REAL historical candles)...")
    logger.info("Timeframes: 4H, 1H, 15M, 5M")
    
    for pair in PAIRS:
        logger.info(f"Fetching data for {pair}...")
        
        # Fetch real historical data for each timeframe
        candles_5m = fetch_real_historical_data(pair, interval='5m', period='5d')
        candles_15m = fetch_real_historical_data(pair, interval='15m', period='5d')
        candles_1h = fetch_real_historical_data(pair, interval='1h', period='1mo')
        
        # Try native 4H first, fall back to aggregating from 1H
        candles_4h = fetch_real_historical_data(pair, interval='4h', period='1mo')
        if not candles_4h:
            candles_4h_raw = fetch_real_historical_data(pair, interval='1h', period='3mo')
            if candles_4h_raw:
                candles_4h = []
                for i in range(0, len(candles_4h_raw), 4):
                    chunk = candles_4h_raw[i:i+4]
                    if len(chunk) == 4:
                        candles_4h.append({
                            'time': chunk[0]['time'],
                            'open': chunk[0]['open'],
                            'high': max(c['high'] for c in chunk),
                            'low': min(c['low'] for c in chunk),
                            'close': chunk[-1]['close'],
                            'volume': sum(c['volume'] for c in chunk)
                        })
        
        if not candles_5m and not candles_15m and not candles_1h and not candles_4h:
            logger.warning(f"Could not fetch any data for {pair}, skipping...")
            continue
        
        # Send candles for each available timeframe
        for label, candles in [('5M', candles_5m), ('15M', candles_15m), ('1H', candles_1h), ('4H', candles_4h)]:
            if candles:
                batch = candles[-100:]
                logger.info(f"  Sending {len(batch)} real {label} candles...")
                for candle in batch:
                    send_candle_to_webhook(pair, candle, label)
                    time.sleep(0.01)
        
        logger.info(f"✓ Completed {pair} (4H:{len((candles_4h or [])[-100:])}, 1H:{len((candles_1h or [])[-100:])}, 15M:{len((candles_15m or [])[-100:])}, 5M:{len((candles_5m or [])[-100:])})")
    
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
                
                # ===== REAL 5M candles =====
                interval_5m = _poll_interval(pair, '5m')
                if pair not in last_5m_update or (now - last_5m_update[pair]) > interval_5m:
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
                
                # ===== REAL 15M candles =====
                interval_15m = _poll_interval(pair, '15m')
                if pair not in last_15m_update or (now - last_15m_update[pair]) > interval_15m:
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
                
                # ===== REAL 1H candles =====
                interval_1h = _poll_interval(pair, '1h')
                if pair not in last_1h_update or (now - last_1h_update[pair]) > interval_1h:
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
                
                # ===== REAL 4H candles =====
                interval_4h = _poll_interval(pair, '4h')
                if pair not in last_4h_update or (now - last_4h_update[pair]) > interval_4h:
                    # Try native 4H fetch first (Twelve Data supports it directly)
                    candles_4h = fetch_real_historical_data(pair, interval='4h', period='1mo')
                    if not candles_4h:
                        # Fallback: aggregate from 1H candles
                        candles_1h_for_4h = fetch_real_historical_data(pair, interval='1h', period='1mo')
                        if candles_1h_for_4h:
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
                return False, 0.0
    except:
        pass
    return False, 0.0


if __name__ == '__main__':
    print("\n" + "="*70)
    print("LIVE FOREX DATA POLLER - MULTI-SOURCE")
    print("="*70)
    print("Source 1: yfinance (free, no API key)")
    print("Source 2: Twelve Data (free tier, 800/day)")
    print(f"Webhook URL: {WEBHOOK_URL}")
    print(f"Tracking: {', '.join(PAIRS)}")
    
    if twelve_data.available:
        print(f"Twelve Data: ✓ API key set ({twelve_data.daily_calls_remaining} calls remaining)")
    else:
        print("Twelve Data: ✗ No API key (set TWELVE_DATA_API_KEY in forex-bot.env)")
    
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
        logger.info("🔄 Activating multi-source data polling...")
    
    # Load initial historical data
    try:
        initial_data_load()
    except Exception as e:
        logger.error(f"❌ Failed to load initial data: {e}")
        logger.info("Continuing with live polling only...")
    
    # Start live polling
    poll_live_data()
