"""
Test Alpaca API Connection
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectors.alpaca_connector import AlpacaConnector
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_alpaca_connection():
    """Test Alpaca API with provided credentials."""
    
    # Credentials from user
    # Note: Replace with your actual credentials
    api_key = input("Enter your Alpaca API Key: ").strip()
    api_secret = input("Enter your Alpaca API Secret: ").strip()
    
    print("\n" + "="*60)
    print("ALPACA API CONNECTION TEST")
    print("="*60)
    print(f"API Key: {api_key[:10]}...")
    print(f"Mode: Paper Trading (Demo)")
    print("="*60 + "\n")
    
    # Initialize connector
    connector = AlpacaConnector(
        api_key=api_key,
        api_secret=api_secret,
        paper=True  # Paper trading mode
    )
    
    # Test 1: Connection
    print("Test 1: Testing connection...")
    if connector.connect():
        print("✓ Connection successful!\n")
    else:
        print("✗ Connection failed!")
        print("Please verify your credentials and try again.")
        return
    
    # Test 2: Account Info
    print("Test 2: Fetching account information...")
    account = connector.get_account_info()
    if account:
        print("✓ Account info retrieved:")
        print(f"  Balance: ${account.get('balance', 0):,.2f}")
        print(f"  Equity: ${account.get('equity', 0):,.2f}")
        print(f"  Buying Power: ${account.get('free_margin', 0):,.2f}")
        print(f"  Currency: {account.get('currency', 'USD')}")
        print(f"  Leverage: 1:{account.get('leverage', 1)}")
        print()
    else:
        print("✗ Failed to get account info\n")
    
    # Test 3: Market Data
    print("Test 3: Fetching market data for EURUSD...")
    candles = connector.get_candles("EURUSD", "M5", 10)
    if candles and candles.get('close'):
        print(f"✓ Received {len(candles['close'])} candles")
        print(f"  Latest close: {candles['close'][-1]:.5f}")
        print(f"  Latest high: {candles['high'][-1]:.5f}")
        print(f"  Latest low: {candles['low'][-1]:.5f}")
        print()
    else:
        print("✗ Failed to get market data")
        print("Note: Alpaca may have limited forex data availability")
        print()
    
    # Test 4: Check Open Positions
    print("Test 4: Checking open positions...")
    positions = connector.get_open_trades()
    print(f"✓ Open positions: {len(positions)}")
    if positions:
        for pos in positions:
            print(f"  {pos['symbol']}: {pos['type']} {pos['volume']} @ {pos['price_open']:.5f}")
            print(f"    Current: {pos['price_current']:.5f}, P&L: ${pos['profit']:.2f}")
    else:
        print("  No open positions")
    print()
    
    # Summary
    print("="*60)
    print("CONNECTION TEST COMPLETE")
    print("="*60)
    print("\nAlpaca connector is ready for live trading!")
    print("\nTo use with your trading bot:")
    print("1. Update config.json to use 'alpaca' broker")
    print("2. Add credentials to environment variables:")
    print("   export ALPACA_API_KEY='your_key'")
    print("   export ALPACA_API_SECRET='your_secret'")
    print("   export ALPACA_PAPER=true  # For demo mode")
    print("\nNote: Alpaca is primarily for stocks/crypto.")
    print("Forex availability may be limited. Check their docs.")
    print("="*60 + "\n")
    
    connector.disconnect()

if __name__ == "__main__":
    try:
        test_alpaca_connection()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nError during test: {e}")
        import traceback
        traceback.print_exc()
