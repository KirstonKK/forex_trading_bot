"""
Forex API Connector
Integration with forex brokers (MT5, Interactive Brokers).
"""

from typing import List, Dict, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta


class BrokerType(Enum):
    MT5 = "mt5"
    IB = "interactive_brokers"


@dataclass
class Symbol:
    """Forex symbol information."""
    name: str
    bid: float
    ask: float
    bid_volume: float
    ask_volume: float
    spread: float


@dataclass
class HistoricalData:
    """Historical price data."""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class ForexConnector:
    """Base class for forex broker connections."""

    def __init__(self, broker_type: BrokerType):
        self.broker_type = broker_type
        self.connected = False

    def connect(self) -> bool:
        """Establish connection to broker."""
        raise NotImplementedError

    def disconnect(self) -> bool:
        """Disconnect from broker."""
        raise NotImplementedError

    def get_symbol(self, symbol: str) -> Optional[Symbol]:
        """Get current bid/ask prices for a symbol."""
        raise NotImplementedError

    def get_symbols(self, filter_pattern: str = "") -> List[Symbol]:
        """Get list of available symbols."""
        raise NotImplementedError

    def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        bars: int
    ) -> List[HistoricalData]:
        """
        Get historical price data.
        
        Args:
            symbol: Trading pair (e.g., "EURUSD")
            timeframe: Candle timeframe (e.g., "H1", "D1")
            bars: Number of bars to fetch
            
        Returns:
            List of historical candles
        """
        raise NotImplementedError

    def place_order(
        self,
        symbol: str,
        order_type: str,
        quantity: float,
        price: float
    ) -> str:
        """Place a market or limit order."""
        raise NotImplementedError

    def close_order(self, order_id: str) -> bool:
        """Close an open order."""
        raise NotImplementedError

    def get_account_info(self) -> Dict:
        """Get account balance, equity, margin info."""
        raise NotImplementedError


class MT5Connector(ForexConnector):
    """MetaTrader 5 connector."""

    def __init__(self, login: int, password: str, server: str):
        super().__init__(BrokerType.MT5)
        self.login = login
        self.password = password
        self.server = server

    def connect(self) -> bool:
        """Connect to MT5 terminal."""
        try:
            import MetaTrader5 as mt5
            
            if not mt5.initialize(
                path="C:\\Program Files\\MetaTrader 5\\terminal64.exe",
                login=self.login,
                password=self.password,
                server=self.server
            ):
                return False
            
            self.connected = True
            return True
        except Exception as e:
            print(f"MT5 connection failed: {e}")
            return False

    def disconnect(self) -> bool:
        """Disconnect from MT5."""
        try:
            import MetaTrader5 as mt5
            mt5.shutdown()
            self.connected = False
            return True
        except Exception:
            return False

    def get_symbol(self, symbol: str) -> Optional[Symbol]:
        """Get current symbol data from MT5."""
        try:
            import MetaTrader5 as mt5
            
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            
            return Symbol(
                name=symbol,
                bid=tick.bid,
                ask=tick.ask,
                bid_volume=getattr(tick, 'bid_volume', 0),
                ask_volume=getattr(tick, 'ask_volume', 0),
                spread=tick.ask - tick.bid
            )
        except Exception:
            return None

    def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        bars: int
    ) -> List[HistoricalData]:
        """Get historical data from MT5."""
        try:
            import MetaTrader5 as mt5
            
            tf_map = {
                "M1": mt5.TIMEFRAME_M1,
                "M5": mt5.TIMEFRAME_M5,
                "H1": mt5.TIMEFRAME_H1,
                "D1": mt5.TIMEFRAME_D1,
            }
            
            timeframe_obj = tf_map.get(timeframe)
            if not timeframe_obj:
                return []
            
            rates = mt5.copy_rates_from_pos(symbol, timeframe_obj, 0, bars)
            if rates is None:
                return []
            
            data = []
            for rate in rates:
                data.append(HistoricalData(
                    timestamp=rate[0],
                    open=rate[1],
                    high=rate[2],
                    low=rate[3],
                    close=rate[4],
                    volume=rate[5]
                ))
            
            return data
        except Exception:
            return []

    def get_account_info(self) -> Dict:
        """Get MT5 account information."""
        try:
            import MetaTrader5 as mt5
            
            account = mt5.account_info()
            if account is None:
                return {}
            
            return {
                "balance": account.balance,
                "equity": account.equity,
                "margin": account.margin,
                "margin_free": account.margin_free,
                "currency": account.currency
            }
        except Exception:
            return {}



