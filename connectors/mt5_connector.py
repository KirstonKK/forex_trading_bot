"""
MetaTrader5 (MT5) Connector

Handles all MT5 API interactions for live trading:
- Account login and balance
- Real-time price quotes
- Historical candlestick data
- Trade execution (buy/sell with SL/TP)
- Position management
"""

import MetaTrader5 as mt5
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class MT5Connector:
    """
    MetaTrader5 connector for live trading.
    
    Provides unified interface for:
    - Account authentication
    - Real-time market data
    - Trade execution and management
    """
    
    def __init__(self, login: int, password: str, server: str):
        """
        Initialize MT5 connector.
        
        Args:
            login: MT5 account login number
            password: MT5 account password
            server: MT5 server name (e.g., 'OANDA_Global-Demo-1')
        """
        self.login = login
        self.password = password
        self.server = server
        self.is_connected = False
        
        # Connect to MT5
        self._connect()
    
    def _connect(self):
        """Connect to MT5 terminal."""
        try:
            if not mt5.initialize():
                raise Exception(f"MT5 initialize failed: {mt5.last_error()}")
            
            if not mt5.login(self.login, self.password, self.server):
                raise Exception(f"MT5 login failed: {mt5.last_error()}")
            
            self.is_connected = True
            logger.info(f"Connected to MT5 account {self.login}")
            
        except Exception as e:
            logger.error(f"MT5 connection error: {e}")
            raise
    
    def disconnect(self):
        """Disconnect from MT5."""
        mt5.shutdown()
        self.is_connected = False
        logger.info("Disconnected from MT5")
    
    def get_account_balance(self) -> float:
        """
        Get current account balance.
        
        Returns:
            Account balance in account currency
        """
        try:
            account_info = mt5.account_info()
            if account_info is None:
                raise Exception(f"Failed to get account info: {mt5.last_error()}")
            
            balance = account_info.balance
            logger.debug(f"Account balance: {balance}")
            return balance
            
        except Exception as e:
            logger.error(f"Error getting account balance: {e}")
            raise
    
    def get_prices(self, symbols: list) -> dict:
        """
        Get current bid/ask prices for symbols.
        
        Args:
            symbols: List of symbol names (e.g., ['EURUSD', 'GBPUSD'])
        
        Returns:
            Dict mapping symbol -> {'bid': bid_price, 'ask': ask_price}
        """
        try:
            prices = {}
            
            for symbol in symbols:
                # Get tick data
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    logger.warning(f"Could not get price for {symbol}: {mt5.last_error()}")
                    continue
                
                prices[symbol] = {
                    'bid': tick.bid,
                    'ask': tick.ask,
                    'timestamp': datetime.fromtimestamp(tick.time)
                }
            
            logger.debug(f"Prices: {prices}")
            return prices
            
        except Exception as e:
            logger.error(f"Error getting prices: {e}")
            raise
    
    def get_candles(self, symbol: str, timeframe: str = 'M1', count: int = 100) -> dict:
        """
        Get historical candlestick data.
        
        Args:
            symbol: Symbol name (e.g., 'EURUSD')
            timeframe: Timeframe code ('M1', 'M5', 'M15', 'H1', 'D1', etc.)
            count: Number of candles to retrieve
        
        Returns:
            Dict with keys: 'open', 'high', 'low', 'close', 'volume', 'time'
        """
        try:
            # Map timeframe string to MT5 constant
            timeframe_map = {
                'M1': mt5.TIMEFRAME_M1,
                'M5': mt5.TIMEFRAME_M5,
                'M15': mt5.TIMEFRAME_M15,
                'M30': mt5.TIMEFRAME_M30,
                'H1': mt5.TIMEFRAME_H1,
                'H4': mt5.TIMEFRAME_H4,
                'D1': mt5.TIMEFRAME_D1,
                'W1': mt5.TIMEFRAME_W1,
                'MN1': mt5.TIMEFRAME_MN1,
            }
            
            if timeframe not in timeframe_map:
                raise ValueError(f"Unknown timeframe: {timeframe}")
            
            mt5_timeframe = timeframe_map[timeframe]
            
            # Fetch candlestick data
            rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, count)
            
            if rates is None or len(rates) == 0:
                raise Exception(f"Failed to get candles for {symbol}: {mt5.last_error()}")
            
            # Convert to dict format
            candles = {
                'time': [datetime.fromtimestamp(r['time']) for r in rates],
                'open': [float(r['open']) for r in rates],
                'high': [float(r['high']) for r in rates],
                'low': [float(r['low']) for r in rates],
                'close': [float(r['close']) for r in rates],
                'volume': [int(r['tick_volume']) for r in rates],
            }
            
            logger.debug(f"Got {len(rates)} candles for {symbol}")
            return candles
            
        except Exception as e:
            logger.error(f"Error getting candles for {symbol}: {e}")
            raise
    
    def create_order(self, symbol: str, volume: float, order_type: str, 
                    entry_price: float = None, stop_loss: float = None, 
                    take_profit: float = None) -> int:
        """
        Create a market or pending order.
        
        Args:
            symbol: Symbol name (e.g., 'EURUSD')
            volume: Order volume (in lots)
            order_type: 'BUY' or 'SELL'
            entry_price: Entry price for pending orders (None for market)
            stop_loss: Stop loss price
            take_profit: Take profit price
        
        Returns:
            Order ticket number (position ID)
        """
        try:
            # Map order type to MT5 constants
            if order_type.upper() == 'BUY':
                mt5_order_type = mt5.ORDER_TYPE_BUY
            elif order_type.upper() == 'SELL':
                mt5_order_type = mt5.ORDER_TYPE_SELL
            else:
                raise ValueError(f"Unknown order type: {order_type}")
            
            # Get current price
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                raise Exception(f"Cannot get price for {symbol}")
            
            price = tick.ask if order_type.upper() == 'BUY' else tick.bid
            
            # Create order request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": mt5_order_type,
                "price": price,
                "sl": stop_loss if stop_loss else 0,
                "tp": take_profit if take_profit else 0,
                "deviation": 20,
                "magic": 123456,
                "comment": "SMC Strategy Trade",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            # Send order
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                raise Exception(f"Order failed: {result.comment}")
            
            logger.info(f"Order created: {order_type} {volume} {symbol} @ {price}, "
                       f"SL: {stop_loss}, TP: {take_profit}")
            
            return result.order
            
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            raise
    
    def close_position(self, symbol: str) -> bool:
        """
        Close all positions for a symbol at market price.
        
        Args:
            symbol: Symbol name
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get open positions for symbol
            positions = mt5.positions_get(symbol=symbol)
            
            if not positions:
                logger.warning(f"No open positions for {symbol}")
                return False
            
            for position in positions:
                # Get current price
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    continue
                
                # Create close order (opposite of position type)
                close_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                price = tick.bid if position.type == mt5.ORDER_TYPE_BUY else tick.ask
                
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": position.volume,
                    "type": close_type,
                    "position": position.ticket,
                    "price": price,
                    "deviation": 20,
                    "magic": 123456,
                    "comment": "SMC Strategy Close",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                
                result = mt5.order_send(request)
                
                if result.retcode != mt5.TRADE_RETCODE_DONE:
                    logger.error(f"Failed to close position: {result.comment}")
                    return False
                
                logger.info(f"Closed position: {symbol} {position.volume} lots")
            
            return True
            
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            raise
    
    def get_open_trades(self) -> list:
        """
        Get all open positions.
        
        Returns:
            List of open positions with details
        """
        try:
            positions = mt5.positions_get()
            
            if not positions:
                return []
            
            trades = []
            for pos in positions:
                trades.append({
                    'ticket': pos.ticket,
                    'symbol': pos.symbol,
                    'type': 'BUY' if pos.type == mt5.ORDER_TYPE_BUY else 'SELL',
                    'volume': pos.volume,
                    'open_price': pos.price_open,
                    'current_price': pos.price_current,
                    'sl': pos.sl,
                    'tp': pos.tp,
                    'profit': pos.profit,
                    'open_time': datetime.fromtimestamp(pos.time),
                })
            
            logger.debug(f"Open trades: {len(trades)}")
            return trades
            
        except Exception as e:
            logger.error(f"Error getting open trades: {e}")
            raise
    
    def get_symbol_info(self, symbol: str) -> dict:
        """
        Get symbol information (spread, contract size, etc).
        
        Args:
            symbol: Symbol name
        
        Returns:
            Dict with symbol info
        """
        try:
            info = mt5.symbol_info(symbol)
            if info is None:
                raise Exception(f"Symbol not found: {symbol}")
            
            return {
                'symbol': info.name,
                'bid': info.bid,
                'ask': info.ask,
                'spread': info.ask - info.bid,
                'contract_size': info.trade_contract_size,
                'point': info.point,
                'digits': info.digits,
            }
            
        except Exception as e:
            logger.error(f"Error getting symbol info: {e}")
            raise
