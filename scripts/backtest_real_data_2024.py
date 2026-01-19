#!/usr/bin/env python3
"""
Backtest with REAL market data from 2024
Downloads actual forex futures data from Yahoo Finance
"""

import sys
import os
from datetime import datetime

# Add project to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from backtesting.data_fetcher import DataFetcher
from backtesting.backtest_engine import BacktestEngine


def main():
    print("=" * 70)
    print("REAL MARKET DATA BACKTEST - 2024")
    print("=" * 70)
    
    # Real futures contracts that track forex pairs
    instruments = [
        ('6E=F', 'EURUSD'),  # Euro FX Futures
        ('6B=F', 'GBPUSD'),  # British Pound Futures
        ('GC=F', 'XAUUSD'),  # Gold Futures
    ]
    
    # Most recent 6 months (within Yahoo's 730 day limit for hourly data)
    start_date = "2025-07-01"
    end_date = "2026-01-14"  # Yesterday
    
    print(f"\nPeriod: {start_date} to {end_date}")
    print(f"Data Source: Yahoo Finance (Real Futures Contracts)")
    print(f"Instruments: {', '.join([name for _, name in instruments])}")
    print("\n⏳ Downloading REAL market data (this may take a moment)...\n")
    
    # Download real data
    historical_data = {}
    
    for ticker, display_name in instruments:
        print(f"📊 Downloading {display_name} ({ticker})...", end=" ", flush=True)
        
        data = DataFetcher.fetch_from_yfinance(
            symbol=ticker,
            start_date=start_date,
            end_date=end_date,
            interval="1h"  # Hourly candles
        )
        
        if not data or len(data) == 0:
            print(f"❌ Failed")
            continue
        
        historical_data[display_name] = data
        
        # Calculate stats
        first_price = data[0]['open']
        last_price = data[-1]['close']
        price_change = ((last_price - first_price) / first_price * 100)
        first_date = datetime.fromtimestamp(data[0]['timestamp']).strftime('%Y-%m-%d')
        last_date = datetime.fromtimestamp(data[-1]['timestamp']).strftime('%Y-%m-%d')
        
        print(f"✅ {len(data)} candles")
        print(f"     Date Range: {first_date} to {last_date}")
        print(f"     Price: {first_price:.5f} → {last_price:.5f} ({price_change:+.2f}%)")
    
    if not historical_data:
        print("\n❌ No data downloaded. Please check your internet connection.")
        return
    
    # Configuration
    print(f"\n{'='*70}")
    print("BACKTEST CONFIGURATION")
    print(f"{'='*70}")
    
    account_balance = 10000.0
    risk_per_trade = 1.0
    symbols = list(historical_data.keys())
    
    print(f"\n  Account Balance: ${account_balance:,.0f}")
    print(f"  Risk per Trade: {risk_per_trade}%")
    print(f"  Daily Risk Limit: 1.5%")
    print(f"  Weekly Risk Limit: 3%")
    print(f"  Max Trades/Day: 2")
    print(f"  Symbols: {', '.join(symbols)}")
    
    # Run backtest
    print(f"\n{'='*70}")
    print("RUNNING BACKTEST ON REAL MARKET DATA...")
    print(f"{'='*70}\n")
    
    engine = BacktestEngine(
        account_balance=account_balance,
        risk_per_trade=risk_per_trade,
        symbols=symbols
    )
    
    result = engine.backtest(historical_data)
    
    # Results
    stats = result.statistics
    
    print("\n" + "="*70)
    print("RESULTS - REAL MARKET DATA")
    print("="*70)
    
    print("\n📊 Trade Summary:")
    print(f"  Total Trades: {stats['total_trades']}")
    print(f"  Winning: {stats['winning_trades']} ({stats['win_rate']:.1f}%)")
    print(f"  Losing: {stats['losing_trades']}")
    
    if stats['total_trades'] > 0:
        print("\n💰 P&L Summary:")
        print(f"  Total P&L: ${stats['total_pnl']:,.2f}")
        print(f"  Initial Balance: ${account_balance:,.2f}")
        print(f"  Final Balance: ${stats['final_balance']:,.2f}")
        return_pct = ((stats['final_balance'] - account_balance) / account_balance * 100)
        
        emoji = "🟢" if return_pct > 0 else "🔴" if return_pct < 0 else "⚪"
        print(f"  Return: {emoji} {return_pct:+.2f}%")
        
        print("\n📈 Trade Metrics:")
        print(f"  Avg Win: ${stats['avg_win']:,.2f}")
        print(f"  Avg Loss: ${stats['avg_loss']:,.2f}")
        
        pf_emoji = "✅" if stats['profit_factor'] > 1.5 else "⚠️" if stats['profit_factor'] > 1.0 else "❌"
        print(f"  Profit Factor: {pf_emoji} {stats['profit_factor']:.2f}")
        
        if result.drawdown_curve:
            max_dd = max(result.drawdown_curve)
            dd_emoji = "✅" if max_dd < 5 else "⚠️" if max_dd < 10 else "❌"
            print(f"  Max Drawdown: {dd_emoji} {max_dd:.2f}%")
        
        # Strategy assessment
        print("\n" + "="*70)
        print("STRATEGY ASSESSMENT (REAL DATA)")
        print("="*70)
        
        if return_pct > 10:
            rating = "🌟 EXCELLENT"
        elif return_pct > 5:
            rating = "✅ GOOD"
        elif return_pct > 0:
            rating = "⚪ ACCEPTABLE"
        else:
            rating = "❌ NEEDS IMPROVEMENT"
        
        print(f"\n  Overall Rating: {rating}")
        print(f"  Win Rate: {'✅ Strong' if stats['win_rate'] > 50 else '⚠️ Needs Work'}")
        print(f"  Profit Factor: {'✅ Healthy' if stats['profit_factor'] > 1.5 else '⚠️ Marginal' if stats['profit_factor'] > 1.0 else '❌ Losing'}")
        if result.drawdown_curve:
            print(f"  Risk Management: {'✅ Good' if max_dd < 10 else '⚠️ Risky'}")
    else:
        print("\n⚠️  No trades were executed during this period")
        print("     Consider adjusting strategy parameters")
    
    print(f"\n💾 Journal saved to: {os.path.join(project_root, 'data/backtest_journal.db')}")
    print("="*70 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Backtest interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
