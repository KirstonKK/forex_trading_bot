"""
Twelve Data API Connector
Free tier: 8 requests/min, 800 requests/day
Provides OHLCV candle data for forex, indices, stocks.

Get a free API key at: https://twelvedata.com/pricing (Basic plan = free)
"""

import os
import time
import requests
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class TwelveDataConnector:
    """
    Fetches OHLCV candle data from Twelve Data's free API.
    
    Rate limits (free tier):
    - 8 API credits per minute
    - 800 API credits per day
    """
    
    BASE_URL = "https://api.twelvedata.com"
    
    # Map internal symbols to Twelve Data symbols
    SYMBOL_MAP = {
        'EURUSD': 'EUR/USD',
        'GBPUSD': 'GBP/USD',
        'USDJPY': 'USD/JPY',
        'AUDUSD': 'AUD/USD',
        'XAUUSD': 'XAU/USD',
        'US30':   'DJI',       # Dow Jones Industrial Average
        'US_30':  'DJI',
    }
    
    # Map internal timeframes to Twelve Data intervals
    INTERVAL_MAP = {
        '5m':  '5min',
        '15m': '15min',
        '1h':  '1h',
        '4h':  '4h',
        '1d':  '1day',
    }
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("TWELVE_DATA_API_KEY", "")
        if not self.api_key:
            logger.warning("TWELVE_DATA_API_KEY not set — Twelve Data connector disabled")
        
        # Rate limiting
        self._minute_calls: List[float] = []
        self._day_calls: List[float] = []
        self._daily_limit = 780  # Stay under 800
        self._minute_limit = 7   # Stay under 8
    
    @property
    def available(self) -> bool:
        return bool(self.api_key)
    
    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits. Returns True if OK to call."""
        now = time.time()
        
        # Clean old entries
        self._minute_calls = [t for t in self._minute_calls if now - t < 60]
        self._day_calls = [t for t in self._day_calls if now - t < 86400]
        
        if len(self._minute_calls) >= self._minute_limit:
            return False
        if len(self._day_calls) >= self._daily_limit:
            return False
        return True
    
    def _wait_for_rate_limit(self):
        """Wait until rate limit allows a new call."""
        now = time.time()
        self._minute_calls = [t for t in self._minute_calls if now - t < 60]
        
        if len(self._minute_calls) >= self._minute_limit:
            oldest = min(self._minute_calls)
            wait = 60 - (now - oldest) + 0.5
            if wait > 0:
                logger.debug(f"Twelve Data rate limit: waiting {wait:.1f}s")
                time.sleep(wait)
    
    def _record_call(self):
        now = time.time()
        self._minute_calls.append(now)
        self._day_calls.append(now)
    
    @property
    def daily_calls_remaining(self) -> int:
        now = time.time()
        self._day_calls = [t for t in self._day_calls if now - t < 86400]
        return max(0, self._daily_limit - len(self._day_calls))
    
    def fetch_candles(self, symbol: str, interval: str = '5m',
                      outputsize: int = 30) -> List[Dict]:
        """
        Fetch OHLCV candles from Twelve Data.
        
        Args:
            symbol: Internal symbol (e.g., 'EURUSD', 'GBPUSD', 'US30')
            interval: Candle interval ('5m', '15m', '1h', '4h')
            outputsize: Number of candles to return (max 5000 on free)
        
        Returns:
            List of candle dicts: [{'time': unix_ts, 'open': ..., 'high': ...,
                                     'low': ..., 'close': ..., 'volume': ...}, ...]
            Ordered oldest-first (ascending time).
        """
        if not self.available:
            return []
        
        td_symbol = self.SYMBOL_MAP.get(symbol, symbol)
        td_interval = self.INTERVAL_MAP.get(interval, interval)
        
        # Wait for rate limit if needed
        self._wait_for_rate_limit()
        
        if not self._check_rate_limit():
            logger.warning(f"Twelve Data daily limit reached ({self._daily_limit})")
            return []
        
        params = {
            'symbol': td_symbol,
            'interval': td_interval,
            'outputsize': outputsize,
            'apikey': self.api_key,
        }
        
        try:
            resp = requests.get(
                f"{self.BASE_URL}/time_series",
                params=params,
                timeout=15
            )
            self._record_call()
            
            data = resp.json()
            
            if data.get('status') == 'error':
                msg = data.get('message', 'Unknown error')
                logger.warning(f"Twelve Data error for {symbol}/{interval}: {msg}")
                return []
            
            values = data.get('values', [])
            if not values:
                logger.warning(f"Twelve Data: no values for {symbol}/{interval}")
                return []
            
            # Convert to internal candle format
            # Twelve Data returns newest-first; we reverse to oldest-first
            candles = []
            for v in reversed(values):
                try:
                    dt = datetime.strptime(v['datetime'], '%Y-%m-%d %H:%M:%S')
                    dt = dt.replace(tzinfo=timezone.utc)
                    unix_ts = int(dt.timestamp())
                    
                    candles.append({
                        'time': unix_ts,
                        'open': float(v['open']),
                        'high': float(v['high']),
                        'low': float(v['low']),
                        'close': float(v['close']),
                        'volume': int(v.get('volume', 0) or 0),
                    })
                except (ValueError, KeyError) as e:
                    logger.debug(f"Skipping malformed candle: {e}")
                    continue
            
            return candles
            
        except requests.RequestException as e:
            logger.error(f"Twelve Data request failed for {symbol}: {e}")
            return []
        except (ValueError, KeyError) as e:
            logger.error(f"Twelve Data parse error for {symbol}: {e}")
            return []
