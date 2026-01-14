"""
InfluxDB Time Series Database
Stores OHLCV candle data and technical indicators for ML training.
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class Candle:
    """OHLCV candle data point."""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str
    timeframe: str


class InfluxDBClient:
    """InfluxDB client for time series data."""

    def __init__(self, url: str = "http://localhost:8086", org: str = "trading", bucket: str = "forex"):
        """
        Initialize InfluxDB client.
        
        Args:
            url: InfluxDB server URL
            org: Organization name
            bucket: Bucket name for storing data
        """
        self.url = url
        self.org = org
        self.bucket = bucket
        self.connected = False
        self.client = None

    def connect(self, token: str) -> bool:
        """
        Connect to InfluxDB.
        
        Args:
            token: InfluxDB API token
            
        Returns:
            True if connected successfully
        """
        try:
            from influxdb_client import InfluxDBClient as IdbClient
            
            self.client = IdbClient(url=self.url, token=token, org=self.org)
            
            # Test connection
            health = self.client.health()
            self.connected = health.status == "pass"
            
            return self.connected
        except Exception as e:
            print(f"InfluxDB connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from InfluxDB."""
        if self.client:
            self.client.close()
            self.connected = False

    def write_candle(self, candle: Candle) -> bool:
        """Write a single candle to InfluxDB."""
        if not self.connected or not self.client:
            return False
        
        try:
            from influxdb_client import Point
            
            point = (
                Point("candle")
                .tag("symbol", candle.symbol)
                .tag("timeframe", candle.timeframe)
                .field("open", candle.open)
                .field("high", candle.high)
                .field("low", candle.low)
                .field("close", candle.close)
                .field("volume", candle.volume)
                .time(candle.timestamp, write_precision='s')
            )
            
            write_api = self.client.write_api()
            write_api.write(bucket=self.bucket, org=self.org, record=point)
            
            return True
        except Exception as e:
            print(f"Error writing candle: {e}")
            return False

    def write_candles_batch(self, candles: List[Candle]) -> bool:
        """Write multiple candles in batch."""
        if not self.connected or not self.client:
            return False
        
        try:
            from influxdb_client import Point
            
            points = []
            for candle in candles:
                point = (
                    Point("candle")
                    .tag("symbol", candle.symbol)
                    .tag("timeframe", candle.timeframe)
                    .field("open", candle.open)
                    .field("high", candle.high)
                    .field("low", candle.low)
                    .field("close", candle.close)
                    .field("volume", candle.volume)
                    .time(candle.timestamp, write_precision='s')
                )
                points.append(point)
            
            write_api = self.client.write_api()
            write_api.write(bucket=self.bucket, org=self.org, records=points)
            
            return True
        except Exception as e:
            print(f"Error writing candles batch: {e}")
            return False

    def write_indicator(
        self,
        symbol: str,
        timeframe: str,
        timestamp: int,
        indicator_name: str,
        value: float
    ) -> bool:
        """Write a technical indicator value."""
        if not self.connected or not self.client:
            return False
        
        try:
            from influxdb_client import Point
            
            point = (
                Point(indicator_name)
                .tag("symbol", symbol)
                .tag("timeframe", timeframe)
                .field("value", value)
                .time(timestamp, write_precision='s')
            )
            
            write_api = self.client.write_api()
            write_api.write(bucket=self.bucket, org=self.org, record=point)
            
            return True
        except Exception as e:
            print(f"Error writing indicator: {e}")
            return False

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
        start_time: Optional[int] = None
    ) -> List[Candle]:
        """
        Retrieve candles from InfluxDB.
        
        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            limit: Number of candles to retrieve
            start_time: Unix timestamp to start from
            
        Returns:
            List of candles
        """
        if not self.connected or not self.client:
            return []
        
        try:
            query_api = self.client.query_api()
            
            # Build Flux query
            query = f'''
                from(bucket:"{self.bucket}")
                |> range(start: {start_time or -10000}h)
                |> filter(fn: (r) => r._measurement == "candle")
                |> filter(fn: (r) => r.symbol == "{symbol}")
                |> filter(fn: (r) => r.timeframe == "{timeframe}")
                |> sort(desc: true)
                |> limit(n: {limit})
            '''
            
            tables = query_api.query(org=self.org, query=query)
            
            candles = []
            for table in tables:
                for record in table.records:
                    # Parse record into candle
                    if record.field in ['open', 'high', 'low', 'close', 'volume']:
                        # Note: This is simplified; full implementation would aggregate fields
                        pass
            
            return candles
        except Exception as e:
            print(f"Error querying candles: {e}")
            return []

    def get_latest_candle(self, symbol: str, timeframe: str) -> Optional[Candle]:
        """Get the most recent candle for a symbol."""
        candles = self.get_candles(symbol, timeframe, limit=1)
        return candles[0] if candles else None

    def get_candle_sequence(
        self,
        symbol: str,
        timeframe: str,
        bars: int = 100
    ) -> List[Candle]:
        """Get a sequence of candles for analysis or ML training."""
        return self.get_candles(symbol, timeframe, limit=bars)
