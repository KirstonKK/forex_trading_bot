"""
Test OANDA REST API Connection
Works on macOS without MetaTrader5 installation!
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectors.oanda_connector import OANDAConnector
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def main():
    print("\n" + "="*60)
    print("OANDA REST API CONNECTION TEST")
    print("="*60)
    
    # Get credentials from environment
    account_id = os.getenv('OANDA_ACCOUNT_ID')
    api_token = os.getenv('OANDA_API_TOKEN')
    environment = os.getenv('OANDA_ENVIRONMENT', 'practice')
    
    if not account_id or not api_token:
        print("\n❌ ERROR: Missing OANDA credentials!")
        print("\nYou need to:")
        print("1. Get your OANDA API token from:")
        print("   https://www.oanda.com/account/tpa/personal_token")
        print("\n2. Create a .env file with:")
        print("   OANDA_ACCOUNT_ID=your_account_id")
        print("   OANDA_API_TOKEN=your_api_token")
        print("   OANDA_ENVIRONMENT=practice")
        print("\nSee docs/OANDA_API_SETUP.md for detailed instructions.")
        print("="*60 + "\n")
        return
    
    print(f"\nAccount ID: {account_id}")
    print(f"Environment: {environment}")
    print(f"API Token: {'*' * (len(api_token) - 4)}{api_token[-4:]}")
    
    # Create connector
    print("\n" + "-"*60)
    print("Connecting to OANDA...")
    print("-"*60)
    
    oanda = OANDAConnector(
        account_id=account_id,
        api_token=api_token,
        environment=environment
    )
    
    # Test connection
    if not oanda.connect():
        print("\n❌ Connection failed!")
        print("Check your credentials and try again.")
        return
    
    print("✓ Connected successfully!")
    
    # Get account info
    print("\n" + "-"*60)
    print("Account Information")
    print("-"*60)
    
    account = oanda.get_account_info()
    if account:
        print(f"Balance: ${account['balance']:,.2f}")
        print(f"Equity: ${account['equity']:,.2f}")
        print(f"Margin Used: ${account['margin']:,.2f}")
        print(f"Free Margin: ${account['free_margin']:,.2f}")
        print(f"Unrealized P&L: ${account['profit']:,.2f}")
        print(f"Currency: {account['currency']}")
        print(f"Leverage: 1:{account['leverage']}")
    
    # Test fetching candles
    print("\n" + "-"*60)
    print("Testing Market Data")
    print("-"*60)
    
    symbols = ['EUR_USD', 'GBP_USD', 'XAU_USD']
    
    for symbol in symbols:
        print(f"\n{symbol}:")
        candles = oanda.get_candles(symbol, 'M5', 10)
        
        if candles and candles.get('close'):
            print(f"  ✓ Fetched {len(candles['close'])} candles")
            print(f"  Current Price: {candles['close'][-1]:.5f}")
            print(f"  High: {max(candles['high'][-5:]):.5f}")
            print(f"  Low: {min(candles['low'][-5:]):.5f}")
        else:
            print(f"  ❌ Failed to fetch candles")
    
    # Check open positions
    print("\n" + "-"*60)
    print("Open Positions")
    print("-"*60)
    
    positions = oanda.get_open_trades()
    if positions:
        print(f"\nYou have {len(positions)} open position(s):")
        for pos in positions:
            print(f"\n{pos['symbol']} - {pos['type']}")
            print(f"  Volume: {pos['volume']:.2f} lots")
            print(f"  Entry: {pos['price_open']:.5f}")
            print(f"  Current: {pos['price_current']:.5f}")
            print(f"  P&L: ${pos['profit']:.2f}")
    else:
        print("\nNo open positions")
    
    # Disconnect
    oanda.disconnect()
    
    print("\n" + "="*60)
    print("✓ TEST COMPLETE - OANDA API WORKS!")
    print("="*60)
    print("\nYou can now use OANDA with the trading bot:")
    print("  python3 scripts/live_trading_bot_oanda.py")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()
