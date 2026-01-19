"""
Download real market data from H2 2025 and run backtest
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from backtesting.data_fetcher import DataFetcher
from backtesting.backtest_engine import BacktestEngine

def main():
    print("=" * 70)
    print("REAL MARKET DATA BACKTEST - H2 2025")
    print("=" * 70)
    
    # Define pairs to test - using Futures or ETFs that track forex
    # FXE = Euro, FXB = British Pound, FXY = Japanese Yen
    pairs = [
        ('FXE', 'EUR/USD'),
        ('FXB', 'GBP/USD'),
        ('FXY', 'USD/JPY')
    ]
    
    # Use recent available data
    start_date = "2024-07-01"
    end_date = "2024-12-31"
    
    print(f"\nDate Range: {start_date} to {end_date}")
    print(f"Instruments: {', '.join([p[1] for p in pairs])}")
    print("(Using currency ETFs as proxy for forex pairs)")
    print("\nDownloading data (this may take a moment)...\n")
    
    # Download data for all pairs
    historical_data = {}
    
    for ticker, display_name in pairs:
        print(f"Downloading {display_name} ({ticker})...", end=" ")
        
        data = DataFetcher.fetch_from_yfinance(
            symbol=ticker,
            start_date=start_date,
            end_date=end_date,
            interval="1h"  # 1-hour candles
        )
        
        if not data:
            print(f"❌ Failed")
            continue
        
        historical_data[display_name] = data
        print(f"✓ {len(data)} candles")
    
    if not historical_data:
        print("\n❌ No data downloaded. Exiting.")
        return
    
    print(f"\n{'='*70}")
    print("RUNNING BACKTEST")
    print(f"{'='*70}")
    
    # Configuration
    account_balance = 10000.0
    risk_per_trade = 1.0
    symbols = list(historical_data.keys())
    
    print(f"\nConfig:")
    print(f"  Account: ${account_balance:,.0f}")
    print(f"  Risk per trade: {risk_per_trade}%")
    print(f"  Symbols: {', '.join(symbols)}")
    print(f"  Daily limit: 1.5%")
    print(f"  Weekly limit: 3%")
    print(f"  Max trades/day: 2")
    
    # Run backtest
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
        return_pct = ((stats['final_balance'] - account_balance) / account_balance * 100)
        print(f"  Return: {return_pct:.2f}%")
        
        print("\nTrade Metrics:")
        print(f"  Avg Win: ${stats['avg_win']:,.2f}")
        print(f"  Avg Loss: ${stats['avg_loss']:,.2f}")
        print(f"  Profit Factor: {stats['profit_factor']:.2f}")
        
        if result.drawdown_curve:
            max_dd = max(result.drawdown_curve)
            print(f"  Max Drawdown: {max_dd:.2f}%")
    else:
        print("\n⚠️  No trades were executed during this period")
    
    print(f"\nJournal saved to: {os.path.join(project_root, 'data/backtest_journal.db')}")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
