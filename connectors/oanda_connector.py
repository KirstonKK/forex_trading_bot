"""
OANDA v20 REST API Connector
Direct integration with OANDA broker using their REST API.
Works on any platform (macOS, Windows, Linux).
"""

import requests
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class OANDAConnector:
    """
    OANDA v20 REST API connector.
    Works on macOS without MetaTrader5 installation.
    
    Documentation: https://developer.oanda.com/rest-live-v20/introduction/
    """
    
    def __init__(self, account_id: str, api_token: str, environment: str = "practice"):
        """
        Initialize OANDA connector.
        
        Args:
            account_id: Your OANDA account ID (e.g., "101-004-XXXXXXXX-001")
            api_token: Your OANDA API token
            environment: "practice" for demo, "live" for real trading
        """
        # Validate environment to prevent accidental live trading
        if environment not in ["practice", "live"]:
            raise ValueError(f"Invalid environment: {environment}. Must be 'practice' or 'live'")
        
        self.account_id = account_id
        self.api_token = api_token
        self.environment = environment
        
        if environment == "practice":
            self.api_url = "https://api-fxpractice.oanda.com"
            self.stream_url = "https://stream-fxpractice.oanda.com"
        else:
            self.api_url = "https://api-fxtrade.oanda.com"
            self.stream_url = "https://stream-fxtrade.oanda.com"
        
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        self.connected = False
    
    def connect(self) -> bool:
        """Test connection by fetching account info."""
        try:
            response = requests.get(
                f"{self.api_url}/v3/accounts/{self.account_id}",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                self.connected = True
                logger.info(f"✓ Connected to OANDA account {self.account_id}")
                return True
            else:
                logger.error(f"Failed to connect: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from OANDA."""
        self.connected = False
        logger.info("Disconnected from OANDA")
    
    def get_account_info(self) -> Dict:
        """Get account information."""
        try:
            response = requests.get(
                f"{self.api_url}/v3/accounts/{self.account_id}/summary",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()['account']
                # Calculate leverage from margin rate (marginRate of 0.02 = 50:1 leverage)
                margin_rate = float(data.get('marginRate', '0.02'))
                leverage = int(1 / margin_rate) if margin_rate > 0 else 50
                
                return {
                    'balance': float(data['balance']),
                    'equity': float(data['NAV']),  # Net Asset Value
                    'margin': float(data.get('marginUsed', 0)),
                    'free_margin': float(data.get('marginAvailable', 0)),
                    'profit': float(data.get('unrealizedPL', 0)),
                    'currency': data['currency'],
                    'leverage': leverage
                }
            else:
                logger.error(f"Failed to get account info: {response.text}")
                return {}
                
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return {}
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current market price for a symbol.
        
        Args:
            symbol: Instrument (e.g., "EUR_USD" or "EURUSD")
        
        Returns:
            Current mid price or None if error
        """
        try:
            # Convert symbol format
            if '_' not in symbol:
                if symbol == 'XAUUSD':
                    instrument = 'XAU_USD'
                elif len(symbol) == 6:
                    instrument = f"{symbol[:3]}_{symbol[3:]}"
                else:
                    instrument = symbol
            else:
                instrument = symbol
            
            response = requests.get(
                f"{self.api_url}/v3/accounts/{self.account_id}/pricing",
                headers=self.headers,
                params={'instruments': instrument},
                timeout=5
            )
            
            if response.status_code == 200:
                prices = response.json().get('prices', [])
                if prices:
                    # Return mid price (average of bid and ask)
                    bid = float(prices[0]['bids'][0]['price'])
                    ask = float(prices[0]['asks'][0]['price'])
                    return (bid + ask) / 2
            
            return None
            
        except Exception as e:
            logger.debug(f"Error getting current price for {symbol}: {e}")
            return None
    
    def get_candles(self, symbol: str, timeframe: str, count: int) -> Dict:
        """
        Fetch candlestick data.
        
        Args:
            symbol: Instrument (e.g., "EUR_USD", "GBP_USD", "XAU_USD")
            timeframe: Granularity (M5, M15, H1, H4, D)
            count: Number of candles
        
        Returns:
            Dict with time, open, high, low, close, volume
        """
        try:
            # Convert symbol format: EURUSD -> EUR_USD
            if '_' not in symbol:
                if symbol == 'XAUUSD':
                    instrument = 'XAU_USD'
                elif len(symbol) == 6:
                    instrument = f"{symbol[:3]}_{symbol[3:]}"
                else:
                    instrument = symbol
            else:
                instrument = symbol
            
            # Map timeframe to OANDA granularity
            granularity_map = {
                'M1': 'M1',
                'M5': 'M5',
                'M15': 'M15',
                'M30': 'M30',
                'H1': 'H1',
                'H4': 'H4',
                'D1': 'D',
                'D': 'D'
            }
            granularity = granularity_map.get(timeframe, 'M5')
            
            # Fetch candles
            params = {
                'granularity': granularity,
                'count': count,
                'price': 'MBA'  # Mid, Bid, Ask
            }
            
            response = requests.get(
                f"{self.api_url}/v3/instruments/{instrument}/candles",
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get candles: {response.text}")
                return {}
            
            candles_data = response.json()['candles']
            
            # Convert to expected format
            result = {
                'time': [],
                'open': [],
                'high': [],
                'low': [],
                'close': [],
                'volume': []
            }
            
            for candle in candles_data:
                if not candle.get('complete', False):
                    continue  # Skip incomplete candles
                
                mid = candle.get('mid')
                if not mid:
                    continue  # Skip candles without mid prices
                
                try:
                    result['time'].append(int(datetime.fromisoformat(candle['time'].replace('Z', '+00:00')).timestamp()))
                    result['open'].append(float(mid['o']))
                    result['high'].append(float(mid['h']))
                    result['low'].append(float(mid['l']))
                    result['close'].append(float(mid['c']))
                    result['volume'].append(int(candle.get('volume', 0)))
                except (KeyError, ValueError) as e:
                    logger.debug(f"Skipping malformed candle: {e}")
                    continue
            
            logger.info(f"Fetched {len(result['close'])} candles for {instrument}")
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
            symbol: Instrument (e.g., "EURUSD")
            volume: Position size in units (not lots)
            order_type: "BUY" or "SELL"
            entry_price: Not used for market orders
            stop_loss: Stop loss price
            take_profit: Take profit price
        
        Returns:
            Order ID (ticket number)
        """
        try:
            # Convert symbol format
            if '_' not in symbol:
                if symbol == 'XAUUSD':
                    instrument = 'XAU_USD'
                elif len(symbol) == 6:
                    instrument = f"{symbol[:3]}_{symbol[3:]}"
                else:
                    instrument = symbol
            else:
                instrument = symbol
            
            # Convert volume from lots to units
            # For forex: 1 lot = 100,000 units
            # For gold: 1 lot = 1 unit
            if 'XAU' in instrument:
                units = int(volume)
            else:
                units = int(volume * 100000)
            
            # Set direction
            if order_type.upper() == "SELL":
                units = -units
            
            # Build order request
            order_data = {
                "order": {
                    "type": "MARKET",
                    "instrument": instrument,
                    "units": str(units),
                    "timeInForce": "FOK",  # Fill or Kill
                    "positionFill": "DEFAULT"
                }
            }
            
            # Add stop loss
            if stop_loss is not None:
                order_data["order"]["stopLossOnFill"] = {
                    "price": f"{stop_loss:.5f}"
                }
            
            # Add take profit
            if take_profit is not None:
                order_data["order"]["takeProfitOnFill"] = {
                    "price": f"{take_profit:.5f}"
                }
            
            # Place order
            response = requests.post(
                f"{self.api_url}/v3/accounts/{self.account_id}/orders",
                headers=self.headers,
                json=order_data,
                timeout=10
            )
            
            if response.status_code == 201:
                result = response.json()
                
                # Check if order was filled
                if 'orderFillTransaction' in result:
                    order_id = result['orderFillTransaction']['id']
                    logger.info(f"Order created: {order_type} {volume} {symbol} (ID: {order_id})")
                    return int(order_id)
                elif 'orderCreateTransaction' in result:
                    # Order created but not yet filled (pending)
                    order_id = result['orderCreateTransaction']['id']
                    logger.warning(f"Order created but pending fill: {order_type} {volume} {symbol} (ID: {order_id})")
                    return int(order_id)
                else:
                    logger.error(f"Order response unexpected: {result}")
                    return 0
            else:
                # Handle error response with proper JSON parsing
                try:
                    error_data = response.json()
                    error_msg = error_data.get('errorMessage', str(error_data))
                except (ValueError, requests.exceptions.JSONDecodeError):
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
                f"{self.api_url}/v3/accounts/{self.account_id}/openTrades",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get trades: {response.text}")
                return []
            
            trades = response.json()['trades']
            result = []
            
            for trade in trades:
                instrument = trade['instrument']
                units = abs(float(trade['currentUnits']))
                
                # Convert units to lots (consistent with create_order)
                if 'XAU' in instrument:
                    volume = units  # Gold: 1 lot = 1 unit
                else:
                    volume = units / 100000  # Forex: 1 lot = 100,000 units
                
                # Get current market price
                price_open = float(trade['price'])
                unrealized_pl = float(trade['unrealizedPL'])
                
                # Fetch actual current market price
                price_current = self.get_current_price(instrument)
                if price_current is None:
                    # Fallback: estimate from unrealized P&L
                    price_current = price_open
                
                result.append({
                    'ticket': int(trade['id']),
                    'symbol': instrument.replace('_', ''),
                    'volume': volume,
                    'type': 'BUY' if float(trade['currentUnits']) > 0 else 'SELL',
                    'price_open': price_open,
                    'sl': float(trade.get('stopLossOrder', {}).get('price', 0)) if trade.get('stopLossOrder') else 0,
                    'tp': float(trade.get('takeProfitOrder', {}).get('price', 0)) if trade.get('takeProfitOrder') else 0,
                    'price_current': price_current,
                    'profit': unrealized_pl,
                    'time': datetime.fromisoformat(trade['openTime'].replace('Z', '+00:00'))
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting trades: {e}")
            return []
    
    def close_trade(self, trade_id: int) -> bool:
        """Close a specific trade."""
        try:
            response = requests.put(
                f"{self.api_url}/v3/accounts/{self.account_id}/trades/{trade_id}/close",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Trade {trade_id} closed")
                return True
            else:
                logger.error(f"Failed to close trade: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error closing trade: {e}")
            return False


# Helper function to get OANDA account ID from MT5 login
def get_oanda_account_from_mt5():
    """
    OANDA MT5 accounts need to be converted to API format.
    You need to get your OANDA API token from:
    https://www.oanda.com/account/tpa/personal_token
    
    Your MT5 login doesn't directly map to API access.
    You'll need to:
    1. Log into OANDA web platform
    2. Get your account ID (format: 101-004-XXXXXXXX-001)
    3. Generate an API token
    """
    print("\n" + "="*60)
    print("OANDA API ACCESS REQUIRED")
    print("="*60)
    print("\nTo use OANDA REST API:")
    print("1. Go to: https://www.oanda.com/account/login")
    print("2. Login with your credentials")
    print("3. Navigate to: Manage API Access")
    print("4. Generate a Personal Access Token")
    print("5. Note your Account ID (format: 101-004-XXXXXXXX-001)")
    print("\nThen update your .env file with:")
    print("  OANDA_ACCOUNT_ID=your_account_id")
    print("  OANDA_API_TOKEN=your_api_token")
    print("="*60 + "\n")
