"""
Test OANDA API Connection
Follow these steps to get your FREE API credentials:

1. Login to OANDA: https://www.oanda.com/account/login
   (Use your demo account: 1600073321)

2. Navigate to: "Manage API Access" or "API" section

3. Click "Generate" or "Personal Access Token"

4. Copy the token immediately (you'll only see it once!)

5. Your Account ID format: 101-004-XXXXXXXX-001

Then run this script and enter your credentials.
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectors.oanda_connector import OandaConnector
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_oanda_connection():
    """Test OANDA API connection."""
    
    print("\n" + "="*60)
    print("OANDA API CONNECTION TEST")
    print("="*60)
    print("Make sure you have:")
    print("1. Your Account ID (format: 101-004-XXXXXXXX-001)")
    print("2. Your API Token (generate from web platform)")
    print("="*60 + "\n")
    
    # Get credentials from user
    account_id = input("Enter your OANDA Account ID: ").strip()
    api_token = input("Enter your OANDA API Token: ").strip()
    environment = input("Environment (practice/live) [practice]: ").strip() or "practice"
    
    print("\n" + "="*60)
    print(f"Account ID: {account_id}")
    print(f"Environment: {environment}")
    print("="*60 + "\n")
    
    # Initialize connector
    connector = OandaConnector(
        account_id=account_id,
        api_token=api_token,
        environment=environment
    )
    
    # Test 1: Connection
    print("Test 1: Testing connection...")
    if connector.connect():
        print("✓ Connection successful!\n")
    else:
        print("✗ Connection failed!")
        print("Please verify your credentials and try again.")
        print("\nTroubleshooting:")
        print("- Make sure Account ID format is correct: 101-004-XXXXXXXX-001")
        print("- Generate a new API token from web platform")
        print("- Ensure you selected 'practice' environment for demo account")
        return
    
    # Test 2: Account Info
    print("Test 2: Fetching account information...")
    account = connector.get_account_info()
    if account:
        print("✓ Account info retrieved:")
        print(f"  Balance: ${account.get('balance', 0):,.2f}")
        print(f"  Equity: ${account.get('equity', 0):,.2f}")
        print(f"  Margin Available: ${account.get('free_margin', 0):,.2f}")
        print(f"  Currency: {account.get('currency', 'USD')}")
        print(f"  Leverage: 1:{account.get('leverage', 50)}")
        print(f"  Open Trades: {account.get('open_trades', 0)}")
        print()
    else:
        print("✗ Failed to get account info\n")
    
    # Test 3: Market Data - EURUSD
    print("Test 3: Fetching market data for EUR_USD...")
    candles = connector.get_candles("EUR_USD", "M5", 10)
    if candles and candles.get('close'):
        print(f"✓ Received {len(candles['close'])} candles")
        print(f"  Latest close: {candles['close'][-1]:.5f}")
        print(f"  Latest high: {candles['high'][-1]:.5f}")
        print(f"  Latest low: {candles['low'][-1]:.5f}")
        print()
    else:
        print("✗ Failed to get market data\n")
    
    # Test 4: Current Price
    print("Test 4: Getting current price for EUR_USD...")
    price = connector.get_current_price("EUR_USD")
    if price:
        print(f"✓ Current price: {price:.5f}")
        print()
    else:
        print("✗ Failed to get current price\n")
    
    # Test 5: Check Open Positions
    print("Test 5: Checking open positions...")
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
    print("\n✓ OANDA connector is ready for live trading!")
    print("\nNext steps:")
    print("1. Save credentials to .env file:")
    print("   OANDA_ACCOUNT_ID='your_account_id'")
    print("   OANDA_API_TOKEN='your_api_token'")
    print("   OANDA_ENVIRONMENT='practice'")
    print("\n2. Update config.json to use OANDA broker")
    print("\n3. Run your trading bot!")
    print("="*60 + "\n")
    
    connector.disconnect()

if __name__ == "__main__":
    try:
        test_oanda_connection()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nError during test: {e}")
        import traceback
        traceback.print_exc()
