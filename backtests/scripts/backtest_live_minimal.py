#!/usr/bin/env python3
"""
Minimal Live Data Backtest
Fetches 2 weeks of live data for quick testing.
"""

import sys
import json
import os
from datetime import datetime, timedelta

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from backtesting.backtest_engine import BacktestEngine
from utils.logger import Logger


def fetch_live_data_minimal():
    """Fetch minimal live data using direct HTTP requests."""
    print("Fetching minimal live data (2 weeks)...")
    
    try:
        import requests
        
        historical_data = {}
        symbols_map = {
            'EURUSD': 'EURUSD=X',
            'GBPUSD': 'GBPUSD=X',
            'XAUUSD': 'GC=F'
        }
        
        for symbol, yf_symbol in symbols_map.items():
            print(f"  Fetching {symbol}...", end=" ", flush=True)
            
            try:
                # Try to fetch from yfinance API
                url = f"https://query1.finance.yahoo.com/v7/finance/download/{yf_symbol}"
                
                end_date = datetime.now()
                start_date = end_date - timedelta(days=14)  # 2 weeks only
                
                params = {
                    'period1': int(start_date.timestamp()),
                    'period2': int(end_date.timestamp()),
                    'interval': '1h',
                    'events': 'history'
                }
                
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    lines = response.text.strip().split('\n')
                    
                    if len(lines) > 1:
                        candles = []
                        for line in lines[1:]:  # Skip header
                            parts = line.split(',')
                            if len(parts) >= 6:
                                try:
                                    date_str = parts[0]
                                    # Parse date
                                    dt = datetime.strptime(date_str, '%Y-%m-%d')
                                    timestamp = int(dt.timestamp())
                                    
                                    candle = {
                                        'timestamp': timestamp,
                                        'open': float(parts[1]),
                                        'high': float(parts[2]),
                                        'low': float(parts[3]),
                                        'close': float(parts[4]),
                                        'volume': float(parts[5]) if parts[5] != 'null' else 0
                                    }
                                    candles.append(candle)
                                except:
                                    continue
                        
                        if candles:
                            historical_data[symbol] = candles
                            print(f"✓ ({len(candles)} candles)")
                        else:
                            print("✗ No valid data")
                    else:
                        print("✗ Empty response")
                else:
                    print(f"✗ HTTP {response.status_code}")
            
            except Exception as e:
                print(f"✗ Error: {str(e)[:30]}")
        
        return historical_data
    
    except ImportError:
        print("  requests not available")
        return {}


def main():
    print("\n" + "="*70)
    print("SMC STRATEGY - MINIMAL LIVE DATA BACKTEST")
    print("="*70)
    
    logger = Logger.get_logger()
    
    # Fetch live data
    historical_data = fetch_live_data_minimal()
    
    if not historical_data:
        print("\nError: Could not fetch live data")
        print("Tip: Check internet connection or try sample data with: python3 run_quick_backtest.py")
        return
    
    print(f"\nData Summary:")
    total_candles = sum(len(candles) for candles in historical_data.values())
    print(f"  Total candles: {total_candles}")
    for symbol, candles in historical_data.items():
        print(f"    {symbol}: {len(candles)} candles")
    
    # Run backtest
    print(f"\nRunning backtest...")
    engine = BacktestEngine(
        account_balance=10000.0,
        risk_per_trade=1.0,
        symbols=list(historical_data.keys())
    )
    
    result = engine.backtest(historical_data)
    
    # Results
    stats = result.statistics
    
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    
    print(f"\nTrade Summary:")
    print(f"  Total Trades: {stats['total_trades']}")
    
    if stats['total_trades'] > 0:
        print(f"  Winning: {stats['winning_trades']} ({stats['win_rate']:.1f}%)")
        print(f"  Losing: {stats['losing_trades']}")
        
        print(f"\nP&L Summary:")
        print(f"  Total P&L: ${stats['total_pnl']:,.2f}")
        print(f"  Initial Balance: $10,000.00")
        print(f"  Final Balance: ${stats['final_balance']:,.2f}")
        print(f"  Return: {((stats['final_balance'] - 10000.0) / 10000.0 * 100):.2f}%")
        
        print(f"\nTrade Metrics:")
        print(f"  Avg Win: ${stats['avg_win']:,.2f}")
        print(f"  Avg Loss: ${stats['avg_loss']:,.2f}")
        print(f"  Profit Factor: {stats['profit_factor']:.2f}")
        
        if result.drawdown_curve:
            max_dd = max(result.drawdown_curve)
            print(f"  Max Drawdown: {max_dd:.2f}%")
    else:
        print(f"  No trades generated in 2-week period")
    
    print(f"\nJournal saved to: {os.path.join(project_root, 'data/backtest_journal.db')}")
    print("="*70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nBacktest interrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
