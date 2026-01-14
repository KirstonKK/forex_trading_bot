"""
Historical Data Fetcher
Fetches OHLCV data from free sources for backtesting.
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta


class DataFetcher:
    """Fetch historical forex data for backtesting."""

    @staticmethod
    def fetch_from_yfinance(
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1h"
    ) -> List[Dict]:
        """
        Fetch data from yfinance (free).
        
        Args:
            symbol: Forex pair or asset (e.g., "EURUSD=X", "GC=F" for gold)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            interval: Interval (1m, 5m, 15m, 1h, 1d)
            
        Returns:
            List of OHLCV dictionaries
        """
        try:
            import yfinance as yf
            
            data = yf.download(symbol, start=start_date, end=end_date, interval=interval, progress=False)
            
            candles = []
            for timestamp, row in data.iterrows():
                candle = {
                    'timestamp': int(timestamp.timestamp()),
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': float(row['Volume']) if 'Volume' in row else 0
                }
                candles.append(candle)
            
            return candles
        except ImportError:
            print("yfinance not installed. Install with: pip install yfinance")
            return []
        except Exception as e:
            print(f"Error fetching data: {e}")
            return []

    @staticmethod
    def fetch_sample_data() -> Dict[str, List[Dict]]:
        """
        Generate sample data for testing without internet.
        
        Returns:
            Dict of {symbol: [candles]} with synthetic data
        """
        import random
        import math
        
        data = {}
        symbols = {
            'EURUSD': 1.0850,
            'GBPUSD': 1.2700,
            'XAUUSD': 2050
        }
        
        for symbol, start_price in symbols.items():
            candles = []
            price = start_price
            base_time = datetime.now() - timedelta(days=200)
            
            # Generate 200 days of hourly data (4800 candles)
            for i in range(4800):
                # Random walk
                daily_change = random.gauss(0, 0.002)
                intraday_volatility = random.gauss(0, 0.0005)
                
                open_price = price
                close_price = price * (1 + daily_change + intraday_volatility)
                high_price = max(open_price, close_price) * (1 + abs(random.gauss(0, 0.0003)))
                low_price = min(open_price, close_price) * (1 - abs(random.gauss(0, 0.0003)))
                
                candle = {
                    'timestamp': int((base_time + timedelta(hours=i)).timestamp()),
                    'open': open_price,
                    'high': high_price,
                    'low': low_price,
                    'close': close_price,
                    'volume': random.randint(100000, 1000000)
                }
                
                candles.append(candle)
                price = close_price
            
            data[symbol] = candles
        
        return data

    @staticmethod
    def get_forex_pair_mapping() -> Dict[str, str]:
        """Get yfinance symbol mapping for forex pairs."""
        return {
            'EURUSD': 'EURUSD=X',
            'GBPUSD': 'GBPUSD=X',
            'USDJPY': 'USDJPY=X',
            'XAUUSD': 'GC=F',  # Gold futures
            'XAGUSD': 'SI=F'   # Silver futures
        }
