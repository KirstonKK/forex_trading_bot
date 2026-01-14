#!/usr/bin/env python3
"""
Quick backtest with minimal resource usage.
Uses sample data - no internet required.
"""

import sys
from datetime import datetime

# Add project to path
import os
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from backtesting.backtest_engine import BacktestEngine
from backtesting.data_fetcher import DataFetcher
from utils.logger import Logger


def main():
    print("\n" + "="*70)
    print("SMC STRATEGY BACKTEST - SAMPLE DATA")
    print("="*70)
    
    # Configuration
    account_balance = 10000.0
    risk_per_trade = 1.0
    symbols = ["EURUSD", "GBPUSD", "XAUUSD"]
    
    print("\nConfig:")
    print(f"  Account: ${account_balance:,.0f}")
    print(f"  Risk per trade: {risk_per_trade}%")
    print(f"  Symbols: {', '.join(symbols)}")
    print("  Daily limit: 1.5%")
    print("  Weekly limit: 3%")
    print("  Max trades/day: 2")
    
    # Generate sample data
    print("\nGenerating synthetic data...")
    data_fetcher = DataFetcher()
    historical_data = data_fetcher.fetch_sample_data()
    
    total_candles = sum(len(candles) for candles in historical_data.values())
    print(f"  Total candles: {total_candles:,}")
    for symbol, candles in historical_data.items():
        print(f"    {symbol}: {len(candles)} candles")
    
    # Run backtest
    print("\nRunning backtest...")
    engine = BacktestEngine(
        account_balance=account_balance,
        risk_per_trade=risk_per_trade,
        symbols=symbols
    )
    
    result = engine.backtest(historical_data)
    
    # Results
    stats = result.statistics
    
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    
    print("\nTrade Summary:")
    print(f"  Total Trades: {stats['total_trades']}")
    print(f"  Winning: {stats['winning_trades']} ({stats['win_rate']:.1f}%)")
    print(f"  Losing: {stats['losing_trades']}")
    
    if stats['total_trades'] > 0:
        print("\nP&L Summary:")
        print(f"  Total P&L: ${stats['total_pnl']:,.2f}")
        print(f"  Initial Balance: ${account_balance:,.2f}")
        print(f"  Final Balance: ${stats['final_balance']:,.2f}")
        print(f"  Return: {((stats['final_balance'] - account_balance) / account_balance * 100):.2f}%")
        
        print("\nTrade Metrics:")
        print(f"  Avg Win: ${stats['avg_win']:,.2f}")
        print(f"  Avg Loss: ${stats['avg_loss']:,.2f}")
        print(f"  Profit Factor: {stats['profit_factor']:.2f}")
        
        if result.drawdown_curve:
            max_dd = max(result.drawdown_curve)
            print(f"  Max Drawdown: {max_dd:.2f}%")
    
    print(f"\nJournal saved to: {os.path.join(project_root, 'data/backtest_journal.db')}")
    print("="*70)
    
    return result


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nBacktest interrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
