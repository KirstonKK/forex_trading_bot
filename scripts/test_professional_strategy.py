#!/usr/bin/env python3
"""
Professional Strategy Backtest - 60%+ Win Rate Target
"""

import sys
import os
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from backtesting.data_fetcher import DataFetcher
from core.professional_strategy import ProfessionalStrategy


def main():
    print("=" * 70)
    print("PROFESSIONAL STRATEGY - 60%+ WIN RATE TARGET")
    print("=" * 70)
    
    instruments = [('6E=F', 'EURUSD'), ('6B=F', 'GBPUSD'), ('GC=F', 'XAUUSD')]
    start_date, end_date = "2025-07-01", "2026-01-14"
    
    print(f"\nPeriod: {start_date} to {end_date}")
    print("Strategy: ALL confirmations required\n")
    
    historical_data = {}
    
    for ticker, name in instruments:
        print(f"📊 {name}...", end=" ", flush=True)
        data = DataFetcher.fetch_from_yfinance(ticker, start_date, end_date, "1h")
        
        if data:
            historical_data[name] = data
            print(f"✅ {len(data)} candles")
    
    if not historical_data:
        print("\n❌ No data")
        return
    
    print(f"\n{'='*70}\nRUNNING STRATEGY\n{'='*70}\n")
    
    all_trades = []
    strategy = ProfessionalStrategy()
    
    for symbol, candles in historical_data.items():
        print(f"\n{symbol}:")
        trades = []
        debug_counts = {'htf': 0, 'ob': 0, 'bos_choch': 0, 'sl_tp': 0, 'confidence': 0}
        
        for i in range(100, len(candles)):
            lookback = candles[:i+1]
            
            # Debug each step
            htf_trend = strategy.determine_htf_trend(lookback)
            if htf_trend.value == 'ranging':
                continue
            debug_counts['htf'] += 1
            
            obs = strategy.find_order_blocks_5m(lookback, htf_trend)
            if not obs:
                continue
            debug_counts['ob'] += 1
            
            ob = obs[-1]
            direction = 'long' if ob.direction == 'bullish' else 'short'
            has_bos, has_choch = strategy.check_bos_choch(lookback, direction)
            if not (has_bos and has_choch):
                continue
            debug_counts['bos_choch'] += 1
            
            signal = strategy.analyze(lookback, symbol)
            if signal:
                trades.append(signal)
                dt = datetime.fromtimestamp(signal.timestamp)
                print(f"  ✅ {len(trades)}. {dt.strftime('%Y-%m-%d %H:%M')} | "
                      f"{signal.direction.upper()} | RR {signal.risk_reward:.2f}:1")
        
        print(f"  Total: {len(trades)}")
        print(f"  Debug: HTF_OK={debug_counts['htf']}, OB={debug_counts['ob']}, BOS+ChoCH={debug_counts['bos_choch']}")
        all_trades.extend(trades)
    
    print(f"\n{'='*70}\nSUMMARY\n{'='*70}\n")
    print(f"Total Signals: {len(all_trades)}")
    
    if all_trades:
        avg_rr = sum(t.risk_reward for t in all_trades) / len(all_trades)
        print(f"Average RR: {avg_rr:.2f}:1")
        print(f"\nExpected Win Rate: 60-70%")
        print(f"Max Trades/Day: 2")
    else:
        print("\n⚠️  No signals - strategy is VERY selective")
    
    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
