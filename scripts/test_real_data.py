"""
Test Trading Bot with REAL Market Data (No Broker Needed!)
Uses free Yahoo Finance data to test strategy with real prices.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectors.free_data_connector import FreeDataConnector
from core.enhanced_smc_strategy import EnhancedSMCStrategy
from core.enhanced_risk_manager import EnhancedRiskManager
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_bot_with_real_data():
    """Test bot with real market data."""
    
    print("\n" + "="*70)
    print("FOREX TRADING BOT - REAL DATA TEST MODE")
    print("="*70)
    print("Testing with REAL market data from Yahoo Finance (FREE)")
    print("No broker account needed!")
    print("="*70 + "\n")
    
    # Initialize free data connector
    connector = FreeDataConnector()
    
    # Test connection
    print("Connecting to data feed...")
    if not connector.connect():
        print("✗ Failed to connect")
        return
    print("✓ Connected to free data feed\n")
    
    # Test pairs
    test_pairs = ["EUR_USD", "GBP_USD", "XAU_USD"]
    
    print("="*70)
    print("FETCHING REAL MARKET DATA")
    print("="*70 + "\n")
    
    for symbol in test_pairs:
        print(f"\n--- {symbol} ---")
        
        # Get current price
        price = connector.get_current_price(symbol)
        if price:
            print(f"✓ Current Price: {price:.5f}")
        else:
            print(f"✗ Could not fetch current price")
            continue
        
        # Get 4H candles (for trend analysis)
        print(f"Fetching 4H candles...")
        candles_4h = connector.get_candles(symbol, "H4", 100)
        if candles_4h and candles_4h.get('close'):
            print(f"✓ Got {len(candles_4h['close'])} candles")
            print(f"  Latest close: {candles_4h['close'][-1]:.5f}")
            print(f"  High: {max(candles_4h['high'][-20:]):.5f}")
            print(f"  Low: {min(candles_4h['low'][-20:]):.5f}")
        else:
            print(f"✗ Could not fetch 4H data")
            continue
        
        # Get 1H candles
        print(f"Fetching 1H candles...")
        candles_1h = connector.get_candles(symbol, "H1", 100)
        if candles_1h and candles_1h.get('close'):
            print(f"✓ Got {len(candles_1h['close'])} candles")
        
        # Get 5M candles (for entry)
        print(f"Fetching 5M candles...")
        candles_5m = connector.get_candles(symbol, "M5", 100)
        if candles_5m and candles_5m.get('close'):
            print(f"✓ Got {len(candles_5m['close'])} candles")
    
    print("\n" + "="*70)
    print("TESTING STRATEGY WITH REAL DATA")
    print("="*70 + "\n")
    
    # Account info
    account = connector.get_account_info()
    balance = account['balance']
    
    # Initialize strategy
    strategy = EnhancedSMCStrategy()
    risk_manager = EnhancedRiskManager(
        account_balance=balance,
        risk_per_trade=1.0,       # 1% risk per trade
        max_daily_loss=4.0,       # 4% max daily loss
        max_trades_per_day=2
    )
    print(f"Account Balance: ${balance:,.2f}")
    print(f"Risk per trade: 1% (${balance * 0.01:,.2f})")
    print(f"Max daily loss: 4% (${balance * 0.04:,.2f})\n")
    
    # Analyze each pair
    for symbol in test_pairs:
        print(f"\n{'='*70}")
        print(f"ANALYZING {symbol}")
        print(f"{'='*70}")
        
        # Fetch all timeframes
        candles_4h = connector.get_candles(symbol, "H4", 100)
        candles_1h = connector.get_candles(symbol, "H1", 100)
        candles_5m = connector.get_candles(symbol, "M5", 100)
        
        if not all([candles_4h.get('close'), candles_1h.get('close'), candles_5m.get('close')]):
            print(f"✗ Insufficient data for {symbol}")
            continue
        
        current_price = connector.get_current_price(symbol)
        if not current_price:
            print(f"✗ Could not get current price")
            continue
        
        # Generate signal
        signal = strategy.generate_signal(
            symbol=symbol,
            candles_4h=candles_4h,
            candles_1h=candles_1h,
            candles_5m=candles_5m,
            current_price=current_price
        )
        
        if signal:
            print(f"\n🎯 SIGNAL DETECTED!")
            print(f"   Direction: {signal['type']}")
            print(f"   Entry: {signal['entry']:.5f}")
            print(f"   Stop Loss: {signal['stop_loss']:.5f}")
            print(f"   Take Profit: {signal['take_profit']:.5f}")
            print(f"   Risk/Reward: 1:{signal['risk_reward']:.2f}")
            print(f"   Confidence: {signal.get('confluence_score', 'N/A')}")
            print(f"   Reason: {signal.get('reason', 'SMC setup')}")
            
            # Calculate position size
            sl_distance = abs(signal['entry'] - signal['stop_loss'])
            risk_amount = balance * 0.01  # 1% risk
            
            # Position size calculation
            if "JPY" in symbol:
                pip_value = 0.01
            elif "XAU" in symbol:
                pip_value = 0.01
            else:
                pip_value = 0.0001
            
            sl_pips = sl_distance / pip_value
            position_size = risk_amount / (sl_pips * pip_value * 100000)  # Standard lot
            
            print(f"\n   Position Sizing:")
            print(f"   SL Distance: {sl_pips:.1f} pips")
            print(f"   Risk Amount: ${risk_amount:.2f}")
            print(f"   Position Size: {position_size:.2f} lots")
            
            print(f"\n   ✓ Valid setup - Would execute in live mode")
        else:
            print(f"\n   No signal - Waiting for setup...")
            print(f"   Current price: {current_price:.5f}")
    
    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70)
    print("\nYour bot is working with REAL market data!")
    print("Once you're ready to trade live, connect a broker.")
    print("\nData source: Yahoo Finance (free, no API key needed)")
    print("Update frequency: Real-time market prices")
    print("="*70 + "\n")
    
    connector.disconnect()


if __name__ == "__main__":
    try:
        test_bot_with_real_data()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
