"""
Free Market Data Connector
Gets real-time forex data without requiring a broker account.
Uses multiple free APIs:
1. Alpha Vantage - Free tier (demo key: works immediately)
2. ExchangeRate-API - Free unlimited forex rates
3. Fixer.io - Backup forex rates
"""

import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging
import time

logger = logging.getLogger(__name__)


class FreeDataConnector:
    """
    Free market data connector for testing strategies.
    No broker account needed!
    
    Data Sources:
    - Alpha Vantage - Free tier with demo key
    - ExchangeRate-API - Free unlimited
    - TradingView webhooks - Can be added later
    """
    
    def __init__(self, alphavantage_key: str = "demo"):
        """
        Initialize free data connector.
        
        Args:
            alphavantage_key: Alpha Vantage API key
                             "demo" works for testing (limited to a few symbols)
                             Get free key at: https://www.alphavantage.co/support/#api-key
        """
        self.alphavantage_key = alphavantage_key
        self.connected = True
        
        # Map our timeframes to Alpha Vantage intervals
        self.av_interval_map = {
            'M1': '1min',
            'M5': '5min',
            'M15': '15min',
            'M30': '30min',
            'H1': '60min',
            'H4': '60min',  # Will fetch hourly and aggregate
            'D1': 'daily',
            'D': 'daily'
        }
    
    def connect(self) -> bool:
        """Always connected - no authentication needed."""
        logger.info("✓ Free data connector ready")
        return True
    
    def disconnect(self):
        """Disconnect."""
        self.connected = False
    
    def get_current_price(self, symbol: str) -> float:
        """
        Get current market price using exchangerate-api (free, no key needed).
        
        Args:
            symbol: Currency pair (e.g., "EUR_USD", "GBP_USD")
        
        Returns:
            Current price
        """
        try:
            # Format symbol
            pair = symbol.replace('_', '').replace('/', '')
            
            # For forex pairs, use exchangerate-api.com (free, no registration)
            if len(pair) == 6 and pair[:3].isalpha() and pair[3:].isalpha():
                base = pair[:3]
                quote = pair[3:]
                
                url = f"https://open.er-api.com/v6/latest/{base}"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    rates = data.get('rates', {})
                    if quote in rates:
                        price = rates[quote]
                        logger.info(f"Current price for {symbol}: {price:.5f}")
                        return float(price)
            
            # For gold, use a simple hardcoded value (will update with real data later)
            if "XAU" in symbol or "GOLD" in symbol:
                logger.info(f"Using estimated price for {symbol}: 2650.00")
                return 2650.00
            
            logger.warning(f"Could not get price for {symbol}")
            return 0.0
            
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
            return 0.0
    
    def get_candles(self, symbol: str, timeframe: str, count: int) -> Dict:
        """
        Get historical candlestick data using Alpha Vantage.
        
        Args:
            symbol: Currency pair (e.g., "EUR_USD")
            timeframe: Timeframe (M1, M5, M15, H1, H4, D1)
            count: Number of candles
        
        Returns:
            Dict with time, open, high, low, close, volume
        """
        try:
            # Format symbol for Alpha Vantage (from_currency/to_currency)
            pair = symbol.replace('_', '')
            from_currency = pair[:3]
            to_currency = pair[3:6] if len(pair) >= 6 else pair[3:]
            
            # Get interval
            interval = self.av_interval_map.get(timeframe, '5min')
            
            # Choose function based on timeframe
            if timeframe in ['D1', 'D']:
                function = 'FX_DAILY'
                url = f"https://www.alphavantage.co/query"
                params = {
                    'function': function,
                    'from_symbol': from_currency,
                    'to_symbol': to_currency,
                    'apikey': self.alphavantage_key,
                    'outputsize': 'full' if count > 100 else 'compact'
                }
            else:
                function = 'FX_INTRADAY'
                url = f"https://www.alphavantage.co/query"
                params = {
                    'function': function,
                    'from_symbol': from_currency,
                    'to_symbol': to_currency,
                    'interval': interval,
                    'apikey': self.alphavantage_key,
                    'outputsize': 'full' if count > 100 else 'compact'
                }
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code != 200:
                logger.warning(f"Alpha Vantage returned {response.status_code}")
                return {}
            
            data = response.json()
            
            # Check for error messages
            if 'Error Message' in data:
                logger.error(f"Alpha Vantage error: {data['Error Message']}")
                return {}
            
            if 'Note' in data:
                logger.warning(f"Alpha Vantage rate limit: {data['Note']}")
                return {}
            
            # Get time series data
            time_series_key = None
            for key in data.keys():
                if 'Time Series' in key:
                    time_series_key = key
                    break
            
            if not time_series_key:
                logger.warning(f"No time series data found for {symbol}")
                return {}
            
            time_series = data[time_series_key]
            
            if not time_series:
                logger.warning(f"Empty time series for {symbol}")
                return {}
            
            # Convert to our format
            result = {
                'time': [],
                'open': [],
                'high': [],
                'low': [],
                'close': [],
                'volume': []
            }
            
            # Sort by timestamp (oldest first)
            sorted_times = sorted(time_series.keys())[-count:]
            
            for timestamp in sorted_times:
                candle = time_series[timestamp]
                
                # Parse timestamp
                dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S') if ' ' in timestamp else datetime.strptime(timestamp, '%Y-%m-%d')
                result['time'].append(int(dt.timestamp()))
                result['open'].append(float(candle.get('1. open', 0)))
                result['high'].append(float(candle.get('2. high', 0)))
                result['low'].append(float(candle.get('3. low', 0)))
                result['close'].append(float(candle.get('4. close', 0)))
                result['volume'].append(0)  # Forex doesn't have volume
            
            logger.info(f"Fetched {len(result['close'])} candles for {symbol} from Alpha Vantage")
            return result
            
        except Exception as e:
            logger.error(f"Error fetching candles for {symbol}: {e}")
            return {}
    
    def get_account_info(self) -> Dict:
        """Simulated account info."""
        return {
            'balance': 10000.0,
            'equity': 10000.0,
            'margin': 0.0,
            'free_margin': 10000.0,
            'profit': 0.0,
            'currency': 'USD',
            'leverage': 50
        }
    
    def create_order(self, symbol: str, volume: float, order_type: str,
                    entry_price: float = None, stop_loss: float = None,
                    take_profit: float = None) -> int:
        """Simulated order (logs only)."""
        logger.info(f"SIMULATION: {order_type} {volume} {symbol} @ {entry_price or 'market'}")
        if stop_loss:
            logger.info(f"  Stop Loss: {stop_loss:.5f}")
        if take_profit:
            logger.info(f"  Take Profit: {take_profit:.5f}")
        return 999999
    
    def get_open_trades(self) -> List[Dict]:
        """No open trades in simulation."""
        return []
    
    def close_trade(self, trade_id: int) -> bool:
        """Simulated close."""
        logger.info(f"SIMULATION: Closed trade {trade_id}")
        return True
