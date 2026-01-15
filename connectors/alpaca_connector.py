"""
Alpaca Markets API Connector
Commission-free trading with REST API.
Works on macOS without any desktop software!
"""

import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class AlpacaConnector:
    """
    Alpaca Markets API connector.
    Free paper trading account with full API access.
    
    Documentation: https://alpaca.markets/docs/
    """
    
    def __init__(self, api_key: str, api_secret: str, paper: bool = True):
        """
        Initialize Alpaca connector.
        
        Args:
            api_key: Your Alpaca API key
            api_secret: Your Alpaca API secret
            paper: True for paper trading (default), False for live trading
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.paper = paper
        
        if paper:
            self.base_url = "https://paper-api.alpaca.markets"
            self.data_url = "https://data.alpaca.markets"
        else:
            self.base_url = "https://api.alpaca.markets"
            self.data_url = "https://data.alpaca.markets"
        
        self.headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
            "Content-Type": "application/json"
        }
        self.connected = False
    
    def connect(self) -> bool:
        """Test connection by fetching account info."""
        try:
            response = requests.get(
                f"{self.base_url}/v2/account",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                self.connected = True
                account_type = "Paper Trading" if self.paper else "Live Trading"
                logger.info(f"✓ Connected to Alpaca ({account_type})")
                return True
            else:
                logger.error(f"Failed to connect: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from Alpaca."""
        self.connected = False
        logger.info("Disconnected from Alpaca")
    
    def get_account_info(self) -> Dict:
        """Get account information."""
        try:
            response = requests.get(
                f"{self.base_url}/v2/account",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'balance': float(data['cash']),
                    'equity': float(data['equity']),
                    'margin': float(data.get('initial_margin', 0)),
                    'free_margin': float(data['buying_power']),
                    'profit': float(data['equity']) - float(data['last_equity']),
                    'currency': data['currency'],
                    'leverage': int(data.get('multiplier', 1))
                }
            else:
                logger.error(f"Failed to get account info: {response.text}")
                return {}
                
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return {}
    
    def get_candles(self, symbol: str, timeframe: str, count: int) -> Dict:
        """
        Fetch candlestick data.
        
        Args:
            symbol: Currency pair (e.g., "EURUSD", "GBPUSD")
            timeframe: Timeframe (M1, M5, M15, H1, H4, D1)
            count: Number of candles
        
        Returns:
            Dict with time, open, high, low, close, volume
        """
        try:
            # Map timeframe to Alpaca format
            timeframe_map = {
                'M1': '1Min',
                'M5': '5Min',
                'M15': '15Min',
                'M30': '30Min',
                'H1': '1Hour',
                'H4': '4Hour',
                'D1': '1Day',
                'D': '1Day'
            }
            tf = timeframe_map.get(timeframe, '5Min')
            
            # Calculate start time (get more than needed, then take last N)
            end = datetime.now()
            if 'Min' in tf:
                minutes = int(tf.replace('Min', ''))
                start = end - timedelta(minutes=minutes * count * 2)
            elif 'Hour' in tf:
                hours = int(tf.replace('Hour', ''))
                start = end - timedelta(hours=hours * count * 2)
            else:
                start = end - timedelta(days=count * 2)
            
            # Format symbol for Alpaca (no separator for forex)
            alpaca_symbol = symbol.replace('_', '')
            
            # Fetch bars
            params = {
                'start': start.isoformat() + 'Z',
                'end': end.isoformat() + 'Z',
                'timeframe': tf,
                'limit': count
            }
            
            response = requests.get(
                f"{self.data_url}/v1beta3/forex/us/bars",
                headers=self.headers,
                params={**params, 'symbols': alpaca_symbol},
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get candles: {response.text}")
                return {}
            
            data = response.json()
            bars = data.get('bars', {}).get(alpaca_symbol, [])
            
            if not bars:
                logger.warning(f"No data returned for {symbol}")
                return {}
            
            # Convert to expected format
            result = {
                'time': [],
                'open': [],
                'high': [],
                'low': [],
                'close': [],
                'volume': []
            }
            
            for bar in bars[-count:]:  # Take last N candles
                result['time'].append(int(datetime.fromisoformat(bar['t'].replace('Z', '+00:00')).timestamp()))
                result['open'].append(float(bar['o']))
                result['high'].append(float(bar['h']))
                result['low'].append(float(bar['l']))
                result['close'].append(float(bar['c']))
                result['volume'].append(int(bar.get('v', 0)))
            
            logger.info(f"Fetched {len(result['close'])} candles for {symbol}")
            return result
            
        except Exception as e:
            logger.error(f"Error fetching candles for {symbol}: {e}")
            return {}
    
    def create_order(self, symbol: str, volume: float, order_type: str,
                    entry_price: float = None, stop_loss: float = None,
                    take_profit: float = None) -> int:
        """
        Create a market order.
        
        Args:
            symbol: Currency pair (e.g., "EURUSD")
            volume: Position size in notional value (dollars)
            order_type: "BUY" or "SELL"
            entry_price: Not used for market orders
            stop_loss: Stop loss price
            take_profit: Take profit price
        
        Returns:
            Order ID
        """
        try:
            # Format symbol for Alpaca
            alpaca_symbol = symbol.replace('_', '')
            
            # Determine side
            side = "buy" if order_type.upper() == "BUY" else "sell"
            
            # Build order request
            order_data = {
                "symbol": alpaca_symbol,
                "notional": str(volume),  # Dollar amount
                "side": side,
                "type": "market",
                "time_in_force": "day"
            }
            
            # Add stop loss
            if stop_loss is not None:
                order_data["stop_loss"] = {
                    "stop_price": f"{stop_loss:.5f}"
                }
            
            # Add take profit
            if take_profit is not None:
                order_data["take_profit"] = {
                    "limit_price": f"{take_profit:.5f}"
                }
            
            # Place order
            response = requests.post(
                f"{self.base_url}/v2/orders",
                headers=self.headers,
                json=order_data,
                timeout=10
            )
            
            if response.status_code == 200 or response.status_code == 201:
                result = response.json()
                order_id = result['id']
                logger.info(f"Order created: {order_type} ${volume} {symbol} (ID: {order_id})")
                return int(order_id) if order_id.isdigit() else hash(order_id) % 1000000
            else:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('message', str(error_data))
                except:
                    error_msg = response.text
                logger.error(f"Order failed ({response.status_code}): {error_msg}")
                return 0
                
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return 0
    
    def get_open_trades(self) -> List[Dict]:
        """Get all open positions."""
        try:
            response = requests.get(
                f"{self.base_url}/v2/positions",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get positions: {response.text}")
                return []
            
            positions = response.json()
            result = []
            
            for pos in positions:
                result.append({
                    'ticket': hash(pos['asset_id']) % 1000000,
                    'symbol': pos['symbol'],
                    'volume': abs(float(pos['qty'])),
                    'type': 'BUY' if float(pos['qty']) > 0 else 'SELL',
                    'price_open': float(pos['avg_entry_price']),
                    'sl': 0,  # Alpaca handles SL differently
                    'tp': 0,  # Alpaca handles TP differently
                    'price_current': float(pos['current_price']),
                    'profit': float(pos['unrealized_pl']),
                    'time': datetime.now()
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    def close_trade(self, symbol: str) -> bool:
        """Close a position by symbol."""
        try:
            alpaca_symbol = symbol.replace('_', '')
            
            response = requests.delete(
                f"{self.base_url}/v2/positions/{alpaca_symbol}",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Position {symbol} closed")
                return True
            else:
                logger.error(f"Failed to close position: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False
