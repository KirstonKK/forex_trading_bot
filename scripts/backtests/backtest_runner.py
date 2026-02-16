#!/usr/bin/env python3
"""
Backtest Runner
Run backtests on SMC strategy with configurable options.
"""

import sys
from datetime import datetime, timedelta
from backtesting.backtest_engine import BacktestEngine
from backtesting.data_fetcher import DataFetcher
from utils.logger import Logger


def run_backtest_sample():
    """Run backtest with sample data (no internet required)."""
    print("\n" + "="*60)
    print("BACKTEST: SMC Strategy with Sample Data")
    print("="*60)
    
    logger = Logger.get_logger()
    
    # Configuration
    account_balance = 10000.0
    risk_per_trade = 1.0
    symbols = ["EURUSD", "GBPUSD", "XAUUSD"]
    
    logger.info(f"Starting backtest with ${account_balance} account")
    logger.info(f"Symbols: {symbols}")
    logger.info(f"Risk per trade: {risk_per_trade}%")
    
    # Fetch sample data (no internet)
    print("\nGenerating sample data...")
    data_fetcher = DataFetcher()
    historical_data = data_fetcher.fetch_sample_data()
    
    for symbol in symbols:
        if symbol in historical_data:
            print(f"  {symbol}: {len(historical_data[symbol])} candles")
    
    # Run backtest
    print("\nRunning backtest...")
    engine = BacktestEngine(
        account_balance=account_balance,
        risk_per_trade=risk_per_trade,
        symbols=symbols
    )
    
    result = engine.backtest(historical_data)
    
    # Print results
    print(engine.get_results_summary(result))
    
    # Additional stats
    if result.trades:
        print("\nDetailed Statistics:")
        print(f"  Winning Trades: {result.statistics['winning_trades']}")
        print(f"  Losing Trades: {result.statistics['losing_trades']}")
        print(f"  Profit Factor: {result.statistics['profit_factor']:.2f}")
        print(f"  Average Win: ${result.statistics['avg_win']:.2f}")
        print(f"  Average Loss: ${result.statistics['avg_loss']:.2f}")
        
        if result.drawdown_curve:
            max_dd = max(result.drawdown_curve)
            print(f"  Max Drawdown: {max_dd:.2f}%")
    
    # Save results
    print("\nSaving results to journal...")
    journal_path = "data/backtest_journal.db"
    print(f"  Journal saved to: {journal_path}")
    print(f"  Total trades logged: {len(result.trades)}")
    
    return result


def run_backtest_live(
    start_date: str = None,
    end_date: str = None,
    symbols: list = None
):
    """
    Run backtest with live data from yfinance.
    
    Args:
        start_date: Start date (YYYY-MM-DD), default 6 months ago
        end_date: End date (YYYY-MM-DD), default today
        symbols: List of symbols to test
    """
    print("\n" + "="*60)
    print("BACKTEST: SMC Strategy with Live Data")
    print("="*60)
    
    logger = Logger.get_logger()
    
    if symbols is None:
        symbols = ["EURUSD", "GBPUSD", "XAUUSD"]
    
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    
    print(f"Date range: {start_date} to {end_date}")
    print(f"Symbols: {symbols}")
    
    # Fetch live data
    print("\nFetching historical data from yfinance...")
    data_fetcher = DataFetcher()
    symbol_mapping = data_fetcher.get_forex_pair_mapping()
    
    historical_data = {}
    for symbol in symbols:
        yf_symbol = symbol_mapping.get(symbol, symbol)
        print(f"  Fetching {symbol} ({yf_symbol})...", end=" ", flush=True)
        
        data = data_fetcher.fetch_from_yfinance(
            symbol=yf_symbol,
            start_date=start_date,
            end_date=end_date,
            interval="1h"
        )
        
        if data:
            historical_data[symbol] = data
            print(f"✓ ({len(data)} candles)")
        else:
            print("✗ Failed")
    
    if not historical_data:
        print("Error: No data fetched!")
        return None
    
    # Run backtest
    print("\nRunning backtest...")
    engine = BacktestEngine(
        account_balance=10000.0,
        risk_per_trade=1.0,
        symbols=list(historical_data.keys())
    )
    
    result = engine.backtest(historical_data)
    
    # Print results
    print(engine.get_results_summary(result))
    
    if result.trades:
        print("\nDetailed Statistics:")
        print(f"  Total Trades: {result.statistics['total_trades']}")
        print(f"  Winning: {result.statistics['winning_trades']}")
        print(f"  Losing: {result.statistics['losing_trades']}")
        print(f"  Win Rate: {result.statistics['win_rate']:.2f}%")
        print(f"  Profit Factor: {result.statistics['profit_factor']:.2f}")
        
        if result.drawdown_curve:
            max_dd = max(result.drawdown_curve)
            print(f"  Max Drawdown: {max_dd:.2f}%")
    
    return result


def main():
    """Main entry point."""
    print("\n" + "="*60)
    print("SMC STRATEGY BACKTEST RUNNER")
    print("="*60)
    
    # Check for arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--live":
        # Run with live data
        try:
            result = run_backtest_live()
        except KeyboardInterrupt:
            print("\n\nBacktest interrupted by user")
            return
        except Exception as e:
            print(f"\nError: {e}")
            print("\nTip: Install yfinance for live data: pip install yfinance")
            print("Falling back to sample data...")
            run_backtest_sample()
    else:
        # Run with sample data (default, no internet needed)
        try:
            result = run_backtest_sample()
        except KeyboardInterrupt:
            print("\n\nBacktest interrupted by user")
            return
        except Exception as e:
            print(f"\nError: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
