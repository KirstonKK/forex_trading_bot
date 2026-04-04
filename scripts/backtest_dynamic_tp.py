#!/usr/bin/env python3
"""
Backtest: Dynamic TP (DOL-based) vs Fixed TP (1:2 / 1:1.5)

Downloads real futures data via yfinance, runs the FlexibleICTStrategy in
backtest mode, and compares performance:
  A) Dynamic TP — DOL targets scored by confluence (current code)
  B) Fixed TP   — forced 1:2 forex / 1:1.5 gold (override)

Usage:
    python scripts/backtest_dynamic_tp.py [--months 6] [--symbol EUR_USD]
"""

import sys
import os
import json
import argparse
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from copy import deepcopy

# Add parent directory to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def download_mtf_data(yf_symbol: str, start: str, end: str) -> Dict[str, List[dict]]:
    """Download multi-timeframe candles from yfinance.
    
    Note: yfinance limits 5M/15M data to the last 60 days.
    For longer periods, we download in chunks.
    """
    import yfinance as yf
    from datetime import datetime as dt

    mtf = {}
    intervals = {'5M': '5m', '15M': '15m', '1H': '1h'}

    start_dt = dt.strptime(start, '%Y-%m-%d')
    end_dt = dt.strptime(end, '%Y-%m-%d')

    for tf, yf_interval in intervals.items():
        print(f"  Downloading {tf} ({yf_interval})...", end=" ", flush=True)
        try:
            # yfinance limits intraday: 5m/15m = 60 days, 1h = 730 days
            max_days = 55 if yf_interval in ('5m', '15m') else 729
            
            # For short-interval data, clamp start to max_days ago
            effective_start = start_dt
            if yf_interval in ('5m', '15m'):
                earliest_allowed = end_dt - timedelta(days=max_days)
                if effective_start < earliest_allowed:
                    effective_start = earliest_allowed
            
            all_candles = []
            chunk_start = effective_start
            
            while chunk_start < end_dt:
                chunk_end = min(chunk_start + timedelta(days=max_days), end_dt)
                data = yf.download(
                    yf_symbol,
                    start=chunk_start.strftime('%Y-%m-%d'),
                    end=chunk_end.strftime('%Y-%m-%d'),
                    interval=yf_interval,
                    progress=False,
                )
                
                for ts, row in data.iterrows():
                    try:
                        all_candles.append({
                            'timestamp': int(ts.timestamp()),
                            'time': ts.strftime('%Y-%m-%d %H:%M'),
                            'open': float(row['Open'].iloc[0]) if hasattr(row['Open'], 'iloc') else float(row['Open']),
                            'high': float(row['High'].iloc[0]) if hasattr(row['High'], 'iloc') else float(row['High']),
                            'low': float(row['Low'].iloc[0]) if hasattr(row['Low'], 'iloc') else float(row['Low']),
                            'close': float(row['Close'].iloc[0]) if hasattr(row['Close'], 'iloc') else float(row['Close']),
                            'volume': float(row['Volume'].iloc[0]) if hasattr(row['Volume'], 'iloc') else float(row.get('Volume', 0)),
                        })
                    except Exception:
                        pass
                
                chunk_start = chunk_end
            
            # Deduplicate by timestamp
            seen = set()
            deduped = []
            for c in all_candles:
                if c['timestamp'] not in seen:
                    seen.add(c['timestamp'])
                    deduped.append(c)
            deduped.sort(key=lambda x: x['timestamp'])
            
            mtf[tf] = deduped
            print(f"✓ {len(deduped)} candles")
        except Exception as e:
            print(f"✗ {e}")
            mtf[tf] = []

    # Build 4H from 1H (aggregate every 4 candles)
    if mtf.get('1H'):
        candles_4h = []
        buf = []
        for c in mtf['1H']:
            buf.append(c)
            if len(buf) == 4:
                candles_4h.append({
                    'timestamp': buf[0]['timestamp'],
                    'time': buf[0]['time'],
                    'open': buf[0]['open'],
                    'high': max(b['high'] for b in buf),
                    'low': min(b['low'] for b in buf),
                    'close': buf[-1]['close'],
                    'volume': sum(b['volume'] for b in buf),
                })
                buf = []
        mtf['4H'] = candles_4h
        print(f"  Built 4H from 1H: {len(candles_4h)} candles")

    return mtf


def simulate_trade(signal: dict, candles_5m: List[dict], start_idx: int) -> dict:
    """
    Walk 5M candles from signal time to see if TP or SL hit first.
    Returns trade result dict.
    """
    entry = signal['entry_price']
    sl = signal['stop_loss']
    tp = signal['take_profit']
    direction = signal['direction']
    sl_dist = abs(entry - sl)
    tp_dist = abs(tp - entry)

    for i in range(start_idx, len(candles_5m)):
        c = candles_5m[i]
        if direction == 'long':
            # Check SL first (worse case)
            if c['low'] <= sl:
                return {
                    'result': 'loss', 'pips': -round(sl_dist * 10000, 1) if sl_dist < 1 else -round(sl_dist, 1),
                    'rr': round(tp_dist / sl_dist, 1) if sl_dist > 0 else 0,
                    'exit_time': c['time'], 'bars': i - start_idx
                }
            if c['high'] >= tp:
                return {
                    'result': 'win', 'pips': round(tp_dist * 10000, 1) if tp_dist < 1 else round(tp_dist, 1),
                    'rr': round(tp_dist / sl_dist, 1) if sl_dist > 0 else 0,
                    'exit_time': c['time'], 'bars': i - start_idx
                }
        else:  # short
            if c['high'] >= sl:
                return {
                    'result': 'loss', 'pips': -round(sl_dist * 10000, 1) if sl_dist < 1 else -round(sl_dist, 1),
                    'rr': round(tp_dist / sl_dist, 1) if sl_dist > 0 else 0,
                    'exit_time': c['time'], 'bars': i - start_idx
                }
            if c['low'] <= tp:
                return {
                    'result': 'win', 'pips': round(tp_dist * 10000, 1) if tp_dist < 1 else round(tp_dist, 1),
                    'rr': round(tp_dist / sl_dist, 1) if sl_dist > 0 else 0,
                    'exit_time': c['time'], 'bars': i - start_idx
                }

    return {'result': 'open', 'pips': 0, 'rr': 0, 'exit_time': 'N/A', 'bars': len(candles_5m) - start_idx}


def run_backtest(mtf_data: Dict[str, List[dict]], symbol: str,
                 force_fixed_tp: bool = False) -> List[dict]:
    """
    Run FlexibleICTStrategy over historical data.

    Args:
        mtf_data: Multi-timeframe candle data
        symbol: e.g. 'EUR_USD'
        force_fixed_tp: If True, override dynamic TP with fixed RR
    """
    from core.flexible_ict_strategy import FlexibleICTStrategy

    strategy = FlexibleICTStrategy()
    candles_5m = mtf_data.get('5M', [])
    if len(candles_5m) < 200:
        print(f"  ⚠️  Insufficient 5M data ({len(candles_5m)} candles, need 200+)")
        return []

    trades = []
    window = 150  # Lookback window for each analysis
    rejection_counts = {}

    # Walk through time
    cooldown_until = 0

    for i in range(window, len(candles_5m), 3):  # Step by 3 candles (15 min)
        candle = candles_5m[i]
        ts = candle['timestamp']

        # Cooldown: don't signal for 4 hours after last signal
        if ts < cooldown_until:
            continue

        # Build MTF slice ending at current time
        slice_5m = candles_5m[max(0, i - window):i + 1]

        # Find matching 1H and 4H candles up to current time
        slice_1h = [c for c in mtf_data.get('1H', []) if c['timestamp'] <= ts][-100:]
        slice_4h = [c for c in mtf_data.get('4H', []) if c['timestamp'] <= ts][-50:]
        slice_15m = [c for c in mtf_data.get('15M', []) if c['timestamp'] <= ts][-100:]

        local_mtf = {'5M': slice_5m, '1H': slice_1h, '4H': slice_4h, '15M': slice_15m}

        # Reset strategy state for clean analysis
        strategy._last_rejection_reasons = []
        strategy._last_sweep_found = False
        strategy._last_bos_found = False
        # Reset daily trade counter (allow unlimited in backtest)
        strategy.trades_today = {}
        # Reset signal cooldown (allow signals every iteration in backtest)
        strategy._last_signal_time = {}
        strategy._recent_signals = {}

        signal = strategy.analyze(slice_5m, symbol=symbol, mtf_data=local_mtf, backtest_mode=True)
        
        # Debug: track rejection reasons
        if not signal:
            reasons = strategy.get_last_rejection_reasons()
            for r in reasons:
                rejection_counts[r] = rejection_counts.get(r, 0) + 1

        if signal:
            # If force_fixed_tp, recalculate TP with fixed RR
            if force_fixed_tp:
                entry = signal['entry_price']
                sl = signal['stop_loss']
                sl_dist = abs(entry - sl)
                is_gold = 'XAU' in symbol
                rr = 1.5 if is_gold else 2.0
                if signal['direction'] == 'long':
                    signal['take_profit'] = entry + sl_dist * rr
                else:
                    signal['take_profit'] = entry - sl_dist * rr
                signal['risk_reward'] = rr

            # Simulate the trade
            result = simulate_trade(signal, candles_5m, i + 1)

            trade = {
                'signal_time': candle['time'],
                'symbol': symbol,
                'setup': signal['setup_type'],
                'direction': signal['direction'],
                'entry': signal['entry_price'],
                'sl': signal['stop_loss'],
                'tp': signal['take_profit'],
                'rr': signal['risk_reward'],
                'confirmations': signal['confirmations'],
                **result,
            }
            trades.append(trade)

            # Apply cooldown (4 hours)
            cooldown_until = ts + 4 * 3600

    # Print rejection summary
    if rejection_counts:
        print(f"\n  Rejection reasons (top 10):")
        sorted_reasons = sorted(rejection_counts.items(), key=lambda x: -x[1])
        for reason, count in sorted_reasons[:10]:
            print(f"    [{count:>5}x] {reason}")

    return trades


def print_results(trades: List[dict], label: str):
    """Print backtest summary."""
    if not trades:
        print(f"\n{'='*60}")
        print(f"  {label}: NO TRADES")
        print(f"{'='*60}")
        return {}

    wins = [t for t in trades if t['result'] == 'win']
    losses = [t for t in trades if t['result'] == 'loss']
    opens = [t for t in trades if t['result'] == 'open']

    total = len(wins) + len(losses)
    wr = (len(wins) / total * 100) if total > 0 else 0

    # P&L in R units (risk = 1R)
    total_r = sum(t['rr'] for t in wins) - len(losses)
    avg_win_rr = sum(t['rr'] for t in wins) / len(wins) if wins else 0
    pf = sum(t['rr'] for t in wins) / len(losses) if losses else float('inf')

    # Pip-based stats
    total_pips = sum(t['pips'] for t in trades if t['result'] != 'open')
    avg_pips = total_pips / total if total > 0 else 0

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Total Signals : {len(trades)} ({len(opens)} still open)")
    print(f"  Closed Trades : {total}")
    print(f"  Wins          : {len(wins)}")
    print(f"  Losses        : {len(losses)}")
    print(f"  Win Rate      : {wr:.1f}%")
    print(f"  Avg Win RR    : 1:{avg_win_rr:.1f}")
    print(f"  Profit Factor : {pf:.2f}")
    print(f"  Total R       : {total_r:+.1f}R")
    print(f"  Total Pips    : {total_pips:+.1f}")
    print(f"  Avg Pips/Trade: {avg_pips:+.1f}")

    # Show RR distribution
    rr_buckets = {}
    for t in wins:
        bucket = f"1:{int(t['rr'])}"
        rr_buckets[bucket] = rr_buckets.get(bucket, 0) + 1
    if rr_buckets:
        print(f"\n  RR Distribution (wins):")
        for rr, count in sorted(rr_buckets.items()):
            print(f"    {rr}: {count} trades")

    # Show per-setup breakdown
    setup_stats = {}
    for t in trades:
        if t['result'] == 'open':
            continue
        s = t['setup']
        if s not in setup_stats:
            setup_stats[s] = {'wins': 0, 'losses': 0, 'r': 0}
        if t['result'] == 'win':
            setup_stats[s]['wins'] += 1
            setup_stats[s]['r'] += t['rr']
        else:
            setup_stats[s]['losses'] += 1
            setup_stats[s]['r'] -= 1

    if setup_stats:
        print(f"\n  Per-Setup Breakdown:")
        for setup, stats in sorted(setup_stats.items()):
            total_s = stats['wins'] + stats['losses']
            wr_s = stats['wins'] / total_s * 100 if total_s else 0
            print(f"    {setup}: {total_s} trades, {wr_s:.0f}% WR, {stats['r']:+.1f}R")

    print(f"{'='*60}")

    return {
        'total': total, 'wins': len(wins), 'losses': len(losses),
        'wr': wr, 'avg_win_rr': avg_win_rr, 'pf': pf,
        'total_r': total_r, 'total_pips': total_pips,
    }


def main():
    parser = argparse.ArgumentParser(description="Backtest Dynamic TP vs Fixed TP")
    parser.add_argument('--months', type=int, default=3, help='Months of data to test')
    parser.add_argument('--symbol', type=str, default='EUR_USD', help='Symbol to test')
    args = parser.parse_args()

    # Map symbols to yfinance tickers
    yf_map = {
        'EUR_USD': 'EURUSD=X',
        'GBP_USD': 'GBPUSD=X',
        'XAU_USD': 'GC=F',
    }

    symbols = [args.symbol] if args.symbol != 'ALL' else list(yf_map.keys())
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=args.months * 30)

    print("=" * 60)
    print("BACKTEST: DYNAMIC TP (DOL) vs FIXED TP")
    print("=" * 60)
    print(f"Period : {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}")
    print(f"Symbols: {', '.join(symbols)}")
    print()

    for symbol in symbols:
        yf_ticker = yf_map.get(symbol)
        if not yf_ticker:
            print(f"⚠️  Unknown symbol {symbol}")
            continue

        print(f"\n{'─'*60}")
        print(f"📈 {symbol} ({yf_ticker})")
        print(f"{'─'*60}")

        # Download data
        mtf = download_mtf_data(
            yf_ticker,
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d'),
        )

        if not mtf.get('5M') or len(mtf['5M']) < 200:
            print(f"  ⚠️  Insufficient data. Try shorter period or different symbol.")
            continue

        print(f"\n▶ Running backtest A: DYNAMIC TP (DOL-based)...")
        trades_dynamic = run_backtest(mtf, symbol, force_fixed_tp=False)

        print(f"▶ Running backtest B: FIXED TP (1:2 forex / 1:1.5 gold)...")
        trades_fixed = run_backtest(mtf, symbol, force_fixed_tp=True)

        stats_dyn = print_results(trades_dynamic, f"{symbol} — DYNAMIC TP (DOL)")
        stats_fix = print_results(trades_fixed, f"{symbol} — FIXED TP")

        # Head-to-head comparison
        if stats_dyn and stats_fix:
            print(f"\n  📊 HEAD-TO-HEAD COMPARISON ({symbol}):")
            print(f"  {'Metric':<20} {'Dynamic':>12} {'Fixed':>12} {'Delta':>12}")
            print(f"  {'─'*56}")
            for key, label in [
                ('total', 'Total Trades'),
                ('wr', 'Win Rate (%)'),
                ('avg_win_rr', 'Avg Win RR'),
                ('pf', 'Profit Factor'),
                ('total_r', 'Total R'),
                ('total_pips', 'Total Pips'),
            ]:
                d = stats_dyn.get(key, 0)
                f = stats_fix.get(key, 0)
                delta = d - f
                fmt = '.1f' if isinstance(d, float) else 'd'
                sign = '+' if delta > 0 else ''
                print(f"  {label:<20} {d:>12{fmt}} {f:>12{fmt}} {sign}{delta:>11{fmt}}")
            print()

    print("\n✅ Backtest complete.")


if __name__ == "__main__":
    main()
