"""
Simulation Mode - Test bot without MT5 connection
Uses yfinance for real market data simulation
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SimulatedMT5Connector:
    """Simulated MT5 connector for testing without real connection."""
    
    def __init__(self, login: int, password: str, server: str):
        self.login = login
        self.server = server
        self.connected = False
        self.positions = []
        
    def connect(self) -> bool:
        """Simulate connection."""
        logger.info(f"[SIMULATION] Connecting to {self.server} with login {self.login}")
        self.connected = True
        logger.info("✓ [SIMULATION] Connected successfully")
        return True
    
    def disconnect(self):
        """Simulate disconnection."""
        logger.info("[SIMULATION] Disconnected")
        self.connected = False
    
    def get_account_info(self) -> Dict:
        """Simulate account info."""
        return {
            'balance': 10000.0,
            'equity': 10000.0,
            'margin': 0.0,
            'free_margin': 10000.0,
            'profit': 0.0,
            'currency': 'USD',
            'leverage': 100
        }
    
    def get_candles(self, symbol: str, timeframe: str, count: int) -> Dict:
        """
        Simulate getting candles using yfinance for real data.
        """
        try:
            import yfinance as yf
            import pandas as pd
            import numpy as np
            
            # Map forex symbols to yfinance format
            symbol_map = {
                'EURUSD': 'EURUSD=X',
                'GBPUSD': 'GBPUSD=X',
                'USDJPY': 'USDJPY=X',
                'XAUUSD': 'GC=F'  # Gold futures
            }
            
            yf_symbol = symbol_map.get(symbol, f"{symbol}=X")
            
            # Map timeframe to period
            timeframe_map = {
                'M5': '5m',
                'M15': '15m',
                'H1': '1h',
                'H4': '4h',
                'D1': '1d'
            }
            
            interval = timeframe_map.get(timeframe, '5m')
            
            # Fetch data
            logger.info(f"[SIMULATION] Fetching {count} candles for {symbol} ({yf_symbol})")
            
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period='5d', interval=interval)
            
            if df.empty:
                logger.warning(f"[SIMULATION] No data for {symbol}, using synthetic data")
                # Generate synthetic data
                dates = pd.date_range(end=datetime.now(), periods=count, freq='5T')
                base_price = 1.0850 if symbol == 'EURUSD' else 1.2650
                df = pd.DataFrame({
                    'Open': base_price + np.random.randn(count) * 0.001,
                    'High': base_price + np.random.randn(count) * 0.001 + 0.0005,
                    'Low': base_price + np.random.randn(count) * 0.001 - 0.0005,
                    'Close': base_price + np.random.randn(count) * 0.001,
                    'Volume': np.random.randint(1000, 10000, count)
                }, index=dates)
            
            # Take last N candles
            df = df.tail(count)
            
            return {
                'time': [int(ts.timestamp()) for ts in df.index],
                'open': df['Open'].values.tolist(),
                'high': df['High'].values.tolist(),
                'low': df['Low'].values.tolist(),
                'close': df['Close'].values.tolist(),
                'volume': df['Volume'].values.tolist()
            }
            
        except ImportError:
            logger.warning("[SIMULATION] yfinance not installed, using synthetic data")
            # Generate synthetic data
            import random
            base_price = 1.0850 if symbol == 'EURUSD' else 1.2650
            
            candles = {
                'time': [int((datetime.now() - timedelta(minutes=5*i)).timestamp()) for i in range(count)],
                'open': [],
                'high': [],
                'low': [],
                'close': [],
                'volume': []
            }
            
            for _ in range(count):
                o = base_price + random.uniform(-0.002, 0.002)
                c = o + random.uniform(-0.001, 0.001)
                h = max(o, c) + random.uniform(0, 0.0005)
                l = min(o, c) - random.uniform(0, 0.0005)
                
                candles['open'].append(o)
                candles['high'].append(h)
                candles['low'].append(l)
                candles['close'].append(c)
                candles['volume'].append(random.randint(1000, 10000))
            
            return candles
    
    def create_order(self, symbol: str, volume: float, order_type: str,
                    entry_price: float = None, stop_loss: float = None,
                    take_profit: float = None) -> int:
        """Simulate order creation."""
        order_id = len(self.positions) + 1
        
        self.positions.append({
            'ticket': order_id,
            'symbol': symbol,
            'volume': volume,
            'type': order_type,
            'price': entry_price or 1.0850,
            'sl': stop_loss,
            'tp': take_profit,
            'time': datetime.now()
        })
        
        logger.info(f"[SIMULATION] Order created: {order_type} {volume} {symbol} @ {entry_price:.5f}")
        logger.info(f"[SIMULATION]   SL: {stop_loss:.5f}, TP: {take_profit:.5f}")
        
        return order_id
    
    def get_open_trades(self) -> List[Dict]:
        """Simulate getting open positions."""
        return [{
            'ticket': pos['ticket'],
            'symbol': pos['symbol'],
            'volume': pos['volume'],
            'type': pos['type'],
            'price_open': pos['price'],
            'sl': pos['sl'],
            'tp': pos['tp'],
            'price_current': pos['price'] + 0.0010,  # Simulate price movement
            'profit': 10.0,
            'time': pos['time']
        } for pos in self.positions]


def test_simulation():
    """Test the bot in simulation mode."""
    print("\n" + "="*60)
    print("SIMULATION MODE - Testing Bot Logic")
    print("="*60)
    print("\nUsing:")
    print(f"  Server: Exness-MT5Trial9 (SIMULATED)")
    print(f"  Login: 297946265")
    print(f"  Mode: Paper trading simulation")
    print("\n" + "="*60)
    
    # Import bot components
    from core.smc_strategy import SMCStrategy
    from core.enhanced_risk_manager import EnhancedRiskManager
    
    # Create simulated connector
    mt5 = SimulatedMT5Connector(
        login=297946265,
        password="11Kenm!!",
        server="Exness-MT5Trial9"
    )
    
    # Connect
    if not mt5.connect():
        print("❌ Connection failed")
        return
    
    # Get account info
    account = mt5.get_account_info()
    print(f"\n💰 Account Balance: ${account['balance']:,.2f}")
    print(f"   Equity: ${account['equity']:,.2f}")
    print(f"   Free Margin: ${account['free_margin']:,.2f}")
    print(f"   Leverage: 1:{account['leverage']}")
    
    # Initialize strategy
    strategy = SMCStrategy()
    risk_manager = EnhancedRiskManager(
        account_balance=account['balance'],
        risk_per_trade=0.01
    )
    
    # Test analysis on symbols
    symbols = ['EURUSD', 'GBPUSD']
    
    print("\n" + "="*60)
    print("ANALYZING SYMBOLS")
    print("="*60)
    
    for symbol in symbols:
        print(f"\n📊 {symbol}")
        print("-" * 40)
        
        try:
            # Fetch candles
            candles = mt5.get_candles(symbol, 'M5', 100)
            print(f"✓ Fetched {len(candles['close'])} candles")
            print(f"  Current Price: {candles['close'][-1]:.5f}")
            print(f"  High: {max(candles['high'][-20:]):.5f}")
            print(f"  Low: {min(candles['low'][-20:]):.5f}")
            
            # Analyze with strategy
            signal = strategy.analyze(candles)
            
            if signal:
                print(f"\n🎯 SIGNAL DETECTED!")
                print(f"  Direction: {signal['direction']}")
                print(f"  Entry: {signal['entry_price']:.5f}")
                print(f"  Stop Loss: {signal['stop_loss']:.5f}")
                print(f"  Take Profit: {signal['take_profit']:.5f}")
                print(f"  Confidence: {signal.get('confidence', 0):.1%}")
                
                # Calculate position size
                position_size = risk_manager.calculate_position_size(
                    entry_price=signal['entry_price'],
                    stop_loss=signal['stop_loss']
                )
                print(f"  Position Size: ${position_size:,.2f}")
                
                # Simulate order
                order_id = mt5.create_order(
                    symbol=symbol,
                    volume=position_size / 100000,  # Convert to lots
                    order_type=signal['direction'],
                    entry_price=signal['entry_price'],
                    stop_loss=signal['stop_loss'],
                    take_profit=signal['take_profit']
                )
                print(f"  Order ID: {order_id}")
                
            else:
                print("  No signal detected")
                
        except Exception as e:
            print(f"❌ Error analyzing {symbol}: {e}")
            logger.exception(e)
    
    # Check positions
    print("\n" + "="*60)
    print("OPEN POSITIONS")
    print("="*60)
    
    positions = mt5.get_open_trades()
    if positions:
        for pos in positions:
            print(f"\n{pos['symbol']} - {pos['type']}")
            print(f"  Entry: {pos['price_open']:.5f}")
            print(f"  Current: {pos['price_current']:.5f}")
            print(f"  P&L: ${pos['profit']:,.2f}")
    else:
        print("\nNo open positions")
    
    # Disconnect
    mt5.disconnect()
    
    print("\n" + "="*60)
    print("SIMULATION COMPLETE")
    print("="*60)
    print("\nNext Steps:")
    print("  1. Install MT5 terminal on Windows/VPS")
    print("  2. Use the bot with real MT5 connection")
    print("  3. Or integrate with broker REST API")
    print("="*60 + "\n")


if __name__ == '__main__':
    test_simulation()
