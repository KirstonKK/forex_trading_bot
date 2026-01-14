"""
MT5 Connection Test Script

Validates that your MT5 setup is working correctly:
1. Credentials validation
2. Account balance check
3. Price quote verification
4. Candlestick data retrieval
5. SMC strategy analysis

Usage:
    python3 test_mt5_connection.py

Set environment variables first:
    export MT5_LOGIN=your_login
    export MT5_PASSWORD=your_password
    export MT5_SERVER=your_server_name
"""

import os
import sys
import logging
from connectors.mt5_connector import MT5Connector
from core.smc_strategy import SMCStrategy
from core.enhanced_risk_manager import EnhancedRiskManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_credentials():
    """Test 1: Validate credentials are available."""
    print("\n" + "="*60)
    print("TEST 1: Credentials Validation")
    print("="*60)
    
    login = os.getenv('MT5_LOGIN')
    password = os.getenv('MT5_PASSWORD')
    server = os.getenv('MT5_SERVER')
    
    if not login:
        print("❌ MT5_LOGIN not set")
        return False, None, None, None
    if not password:
        print("❌ MT5_PASSWORD not set")
        return False, None, None, None
    if not server:
        print("❌ MT5_SERVER not set")
        return False, None, None, None
    
    print(f"✓ MT5_LOGIN: {login}")
    print(f"✓ MT5_PASSWORD: (hidden)")
    print(f"✓ MT5_SERVER: {server}")
    
    return True, int(login), password, server


def test_connection(login, password, server):
    """Test 2: Connect to MT5."""
    print("\n" + "="*60)
    print("TEST 2: MT5 Connection")
    print("="*60)
    
    try:
        mt5 = MT5Connector(login, password, server)
        print("✓ Connected to MT5")
        return True, mt5
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("\nTroubleshooting:")
        print("  - Check login/password (case sensitive)")
        print("  - Verify server name (e.g., OANDA_Global-Demo-1)")
        print("  - Ensure MT5 terminal is running on your computer")
        print("  - Install MetaTrader5 Python package: pip install MetaTrader5")
        return False, None


def test_balance(mt5):
    """Test 3: Get account balance."""
    print("\n" + "="*60)
    print("TEST 3: Account Balance")
    print("="*60)
    
    try:
        balance = mt5.get_account_balance()
        print(f"✓ Account Balance: ${balance:,.2f}")
        return True, balance
    except Exception as e:
        print(f"❌ Failed to get balance: {e}")
        return False, None


def test_prices(mt5, symbols=['EURUSD', 'GBPUSD', 'XAUUSD']):
    """Test 4: Get live prices."""
    print("\n" + "="*60)
    print("TEST 4: Live Price Quotes")
    print("="*60)
    
    try:
        prices = mt5.get_prices(symbols)
        
        if not prices:
            print("❌ No prices returned")
            return False
        
        for symbol, price_data in prices.items():
            bid = price_data['bid']
            ask = price_data['ask']
            spread = ask - bid
            print(f"✓ {symbol}: Bid={bid:.5f}, Ask={ask:.5f}, Spread={spread:.5f}")
        
        return True
    except Exception as e:
        print(f"❌ Failed to get prices: {e}")
        return False


def test_candles(mt5, symbol='EURUSD'):
    """Test 5: Get candlestick data."""
    print("\n" + "="*60)
    print("TEST 5: Candlestick Data")
    print("="*60)
    
    try:
        candles = mt5.get_candles(symbol, timeframe='M5', count=20)
        
        if not candles or not candles['close']:
            print(f"❌ No candles returned for {symbol}")
            return False
        
        print(f"✓ Retrieved {len(candles['close'])} candles for {symbol} (M5)")
        
        # Show last 3 candles
        print("\nLast 3 candles:")
        for i in range(max(0, len(candles['close'])-3), len(candles['close'])):
            time_str = candles['time'][i].strftime('%Y-%m-%d %H:%M')
            o = candles['open'][i]
            h = candles['high'][i]
            l = candles['low'][i]
            c = candles['close'][i]
            print(f"  {time_str}: O={o:.5f}, H={h:.5f}, L={l:.5f}, C={c:.5f}")
        
        return True, candles
    except Exception as e:
        print(f"❌ Failed to get candles: {e}")
        return False, None


def test_strategy(candles, symbol='EURUSD'):
    """Test 6: SMC Strategy Analysis."""
    print("\n" + "="*60)
    print("TEST 6: SMC Strategy Analysis")
    print("="*60)
    
    try:
        strategy = SMCStrategy()
        signal = strategy.analyze(candles)
        
        if signal:
            print(f"✓ Signal detected for {symbol}")
            print(f"  Direction: {signal['direction']}")
            print(f"  Entry Price: {signal['entry_price']:.5f}")
            print(f"  Stop Loss: {signal['stop_loss']:.5f}")
            print(f"  Take Profit: {signal['take_profit']:.5f}")
            print(f"  Risk/Reward: {signal.get('rr_ratio', 'N/A'):.2f}")
            return True
        else:
            print("✓ No signal detected (normal - signals are rare)")
            return True
    except Exception as e:
        print(f"❌ Strategy analysis failed: {e}")
        return False


def test_risk_manager(balance):
    """Test 7: Risk Manager Validation."""
    print("\n" + "="*60)
    print("TEST 7: Risk Manager")
    print("="*60)
    
    try:
        risk_mgr = EnhancedRiskManager(
            account_balance=balance,
            risk_per_trade=0.01,  # 1%
            daily_loss_limit=0.015,  # 1.5%
            weekly_loss_limit=0.03   # 3%
        )
        
        # Test position sizing
        position_risk = risk_mgr.calculate_position_size(
            entry_price=1.0850,
            stop_loss=1.0800,
            current_balance=balance
        )
        
        print(f"✓ Risk Manager initialized")
        print(f"  Account Balance: ${balance:,.2f}")
        print(f"  Risk per Trade: 1.0%")
        print(f"  Daily Loss Limit: 1.5%")
        print(f"  Weekly Loss Limit: 3.0%")
        print(f"\nPosition Risk Calculation (EURUSD example):")
        print(f"  Entry: 1.0850")
        print(f"  Stop Loss: 1.0800")
        print(f"  Risk Amount: ${position_risk:.2f}")
        
        return True
    except Exception as e:
        print(f"❌ Risk Manager test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("MT5 TRADING BOT - CONNECTION TEST")
    print("="*60)
    
    results = []
    
    # Test 1: Credentials
    creds_ok, login, password, server = test_credentials()
    results.append(("Credentials", creds_ok))
    
    if not creds_ok:
        print_summary(results)
        return 1
    
    # Test 2: Connection
    conn_ok, mt5 = test_connection(login, password, server)
    results.append(("MT5 Connection", conn_ok))
    
    if not conn_ok:
        print_summary(results)
        return 1
    
    # Test 3: Balance
    balance_ok, balance = test_balance(mt5)
    results.append(("Account Balance", balance_ok))
    
    if not balance_ok:
        print_summary(results)
        return 1
    
    # Test 4: Prices
    prices_ok = test_prices(mt5)
    results.append(("Live Prices", prices_ok))
    
    # Test 5: Candles
    candles_ok, candles = test_candles(mt5, 'EURUSD')
    results.append(("Candlestick Data", candles_ok))
    
    # Test 6: Strategy (if candles available)
    if candles_ok:
        strategy_ok = test_strategy(candles)
        results.append(("SMC Strategy", strategy_ok))
    
    # Test 7: Risk Manager
    if balance_ok:
        risk_ok = test_risk_manager(balance)
        results.append(("Risk Manager", risk_ok))
    
    # Cleanup
    if mt5:
        mt5.disconnect()
    
    # Print summary
    print_summary(results)
    
    # Return success if all tests passed
    all_passed = all(passed for _, passed in results)
    return 0 if all_passed else 1


def print_summary(results):
    """Print test summary."""
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for test_name, passed in results:
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(passed for _, passed in results)
    
    print("="*60)
    if all_passed:
        print("\n✓ All tests passed! You're ready to run the live bot:")
        print("  python3 live_trading_bot.py")
    else:
        print("\n❌ Some tests failed. See errors above.")
        print("\nTroubleshooting:")
        print("  1. Install MetaTrader5: pip install MetaTrader5")
        print("  2. Verify MT5 credentials (case sensitive)")
        print("  3. Check that MT5 terminal is running")
        print("  4. Ensure symbols are available on your server")
    print("="*60 + "\n")


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
