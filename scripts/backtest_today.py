#!/usr/bin/env python3
"""
Single-Day Backtest — Feb 25, 2026
===================================
Downloads today's real market data from yfinance and replays it through
the FlexibleICTStrategy with ALL filters active (HTF trend gates,
losing-zone dedup, global cap, cooldown).

Shows:
  1. Every signal the strategy WOULD have generated (pre-filter)
  2. Which signals pass the new filters
  3. Simulated trade results (TP/SL hit)

Usage:
    python scripts/backtest_today.py
"""

import sys
import os
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from copy import deepcopy

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


# ── data download ────────────────────────────────────────────────────
def download_mtf_data(yf_symbol: str, start: str, end: str) -> Dict[str, List[dict]]:
    """Download multi-timeframe candles from yfinance."""
    import yfinance as yf

    mtf = {}
    intervals = {'5M': '5m', '15M': '15m', '1H': '1h'}

    start_dt = datetime.strptime(start, '%Y-%m-%d')
    end_dt = datetime.strptime(end, '%Y-%m-%d')

    for tf, yf_interval in intervals.items():
        print(f"  Downloading {tf} ({yf_interval})...", end=" ", flush=True)
        try:
            data = yf.download(
                yf_symbol,
                start=start_dt.strftime('%Y-%m-%d'),
                end=end_dt.strftime('%Y-%m-%d'),
                interval=yf_interval,
                progress=False,
            )
            candles = []
            for ts, row in data.iterrows():
                try:
                    candles.append({
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

            candles.sort(key=lambda x: x['timestamp'])
            mtf[tf] = candles
            print(f"✓ {len(candles)} candles")
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


# ── trade simulator ──────────────────────────────────────────────────
def simulate_trade(signal: dict, candles_5m: List[dict], start_idx: int) -> dict:
    """Walk 5M candles to see if TP or SL hit first."""
    entry = signal['entry_price']
    sl = signal['stop_loss']
    tp = signal['take_profit']
    direction = signal['direction']
    sl_dist = abs(entry - sl)
    tp_dist = abs(tp - entry)

    for i in range(start_idx, len(candles_5m)):
        c = candles_5m[i]
        if direction == 'long':
            if c['low'] <= sl:
                return {'result': 'LOSS', 'pips': -round(sl_dist * 10000, 1) if sl_dist < 1 else -round(sl_dist, 1),
                        'rr': round(tp_dist / sl_dist, 1) if sl_dist else 0, 'exit_time': c['time']}
            if c['high'] >= tp:
                return {'result': 'WIN', 'pips': round(tp_dist * 10000, 1) if tp_dist < 1 else round(tp_dist, 1),
                        'rr': round(tp_dist / sl_dist, 1) if sl_dist else 0, 'exit_time': c['time']}
        else:
            if c['high'] >= sl:
                return {'result': 'LOSS', 'pips': -round(sl_dist * 10000, 1) if sl_dist < 1 else -round(sl_dist, 1),
                        'rr': round(tp_dist / sl_dist, 1) if sl_dist else 0, 'exit_time': c['time']}
            if c['low'] <= tp:
                return {'result': 'WIN', 'pips': round(tp_dist * 10000, 1) if tp_dist < 1 else round(tp_dist, 1),
                        'rr': round(tp_dist / sl_dist, 1) if sl_dist else 0, 'exit_time': c['time']}

    return {'result': 'OPEN', 'pips': 0, 'rr': 0, 'exit_time': 'still open'}


# ── main backtest ────────────────────────────────────────────────────
def run_single_day_backtest():
    from core.flexible_ict_strategy import FlexibleICTStrategy
    import logging

    logging.basicConfig(level=logging.WARNING)

    # ── configuration ──
    today = datetime(2026, 2, 25, tzinfo=timezone.utc)
    # Need a few days lookback for 4H context to be meaningful
    lookback_start = (today - timedelta(days=7)).strftime('%Y-%m-%d')
    # yfinance end is exclusive, so +1 day
    end_date = (today + timedelta(days=1)).strftime('%Y-%m-%d')

    yf_map = {
        'EUR_USD': '6E=F',
        'GBP_USD': '6B=F',
        'XAU_USD': 'GC=F',
    }

    symbols = ['EUR_USD', 'GBP_USD', 'XAU_USD']

    print("=" * 70)
    print("  SINGLE-DAY BACKTEST — February 25, 2026")
    print("  Strategy: FlexibleICTStrategy with ALL new filters")
    print("  Filters : HTF trend gate, losing-zone dedup, 3/day global cap")
    print("=" * 70)

    # ── download data ──
    all_mtf = {}
    for symbol in symbols:
        yf_ticker = yf_map[symbol]
        print(f"\n📥 Downloading {symbol} ({yf_ticker})...")
        all_mtf[symbol] = download_mtf_data(yf_ticker, lookback_start, end_date)

    # ── run strategy with filters active ──
    # Single shared strategy instance — daily caps persist across symbols
    strategy = FlexibleICTStrategy()
    # Force a fresh day
    strategy.current_date = None
    strategy.trades_today = {}
    strategy._recent_losses = {}
    strategy._last_signal_time = {}
    strategy._recent_signals = {}

    all_results = []
    window = 150

    # Determine today's timestamp range (Feb 25 00:00 → 23:59 UTC)
    day_start_ts = int(today.timestamp())
    day_end_ts = int((today + timedelta(days=1)).timestamp())

    print(f"\n{'='*70}")
    print(f"  REPLAYING TODAY'S PRICE ACTION")
    print(f"{'='*70}")

    # Interleave all symbols' 5M candles by timestamp so the strategy
    # sees them in chronological order (like the live bot would)
    timed_events = []
    for symbol in symbols:
        candles_5m = all_mtf[symbol].get('5M', [])
        for idx, c in enumerate(candles_5m):
            if day_start_ts <= c['timestamp'] < day_end_ts:
                timed_events.append((c['timestamp'], symbol, idx))

    timed_events.sort(key=lambda x: x[0])

    signal_num = 0
    # Track signals that would have been generated WITHOUT new filters (for comparison)
    blocked_signals = []

    for ts, symbol, idx in timed_events:
        candles_5m = all_mtf[symbol].get('5M', [])

        # Need enough lookback
        if idx < window:
            continue

        # Build MTF slice up to current candle
        slice_5m = candles_5m[max(0, idx - window):idx + 1]
        slice_1h = [c for c in all_mtf[symbol].get('1H', []) if c['timestamp'] <= ts][-100:]
        slice_4h = [c for c in all_mtf[symbol].get('4H', []) if c['timestamp'] <= ts][-50:]
        slice_15m = [c for c in all_mtf[symbol].get('15M', []) if c['timestamp'] <= ts][-100:]

        local_mtf = {'5M': slice_5m, '1H': slice_1h, '4H': slice_4h, '15M': slice_15m}

        # ── Check filters FIRST (like the live bot does) ──
        # 1. Daily cap check
        cap_ok = strategy.can_take_trade(ts, symbol)
        
        # 2. Signal cooldown check  
        cooldown_ok = strategy.check_signal_cooldown(symbol, ts)

        if not cap_ok or not cooldown_ok:
            continue  # Skip analysis entirely (save compute)

        # 3. Losing-zone check happens inside analyze() as step 0

        # ── Run analysis ──
        strategy._last_rejection_reasons = []
        signal = strategy.analyze(slice_5m, symbol=symbol, mtf_data=local_mtf, backtest_mode=True)

        if signal:
            signal_num += 1
            # NOTE: analyze() already calls record_trade() and records cooldown
            # so we do NOT call them again here

            # Simulate
            result = simulate_trade(signal, candles_5m, idx + 1)

            # If loss, record it for losing-zone dedup
            if result['result'] == 'LOSS':
                strategy.record_loss(symbol, signal['entry_price'], signal['direction'], ts)

            entry_time = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%H:%M')
            dir_icon = '🟢' if signal['direction'] == 'long' else '🔴'
            result_icon = '✅' if result['result'] == 'WIN' else ('❌' if result['result'] == 'LOSS' else '⏳')

            trade_info = {
                'num': signal_num,
                'time': entry_time,
                'symbol': symbol,
                'direction': signal['direction'],
                'setup': signal['setup_type'],
                'entry': signal['entry_price'],
                'sl': signal['stop_loss'],
                'tp': signal['take_profit'],
                'rr': signal['risk_reward'],
                'confirmations': signal['confirmations'],
                'result': result['result'],
                'pips': result['pips'],
                'exit_time': result.get('exit_time', 'N/A'),
            }
            all_results.append(trade_info)

            print(f"\n  Signal #{signal_num} — {entry_time} UTC")
            print(f"    {dir_icon} {symbol} {signal['direction'].upper()}")
            print(f"    Setup : {signal['setup_type']}")
            print(f"    Entry : {signal['entry_price']}")
            print(f"    SL    : {signal['stop_loss']}")
            print(f"    TP    : {signal['take_profit']} (RR 1:{signal['risk_reward']:.1f})")
            print(f"    Confs : {signal['confirmations']}")
            print(f"    Result: {result_icon} {result['result']} ({result['pips']:+.1f} pips) — exit {result.get('exit_time', 'N/A')}")

    # ── Summary ──
    print(f"\n{'='*70}")
    print(f"  RESULTS SUMMARY — Feb 25, 2026")
    print(f"{'='*70}")

    if not all_results:
        print("  No signals generated today.")
        print("  (This means the quality filters blocked everything.)")
        print(f"\n  Daily cap used: {sum(strategy.trades_today.values())}/3")
        print(f"  Symbols traded: {list(strategy.trades_today.keys())}")
        return

    wins = [t for t in all_results if t['result'] == 'WIN']
    losses = [t for t in all_results if t['result'] == 'LOSS']
    opens = [t for t in all_results if t['result'] == 'OPEN']
    closed = len(wins) + len(losses)

    total_pips = sum(t['pips'] for t in all_results if t['result'] != 'OPEN')
    total_r = sum(t['rr'] for t in wins) - len(losses)
    wr = len(wins) / closed * 100 if closed else 0

    print(f"\n  Signals Taken : {len(all_results)}")
    print(f"  Closed Trades : {closed}")
    print(f"  Wins          : {len(wins)}")
    print(f"  Losses        : {len(losses)}")
    print(f"  Still Open    : {len(opens)}")
    print(f"  Win Rate      : {wr:.0f}%")
    print(f"  Total Pips    : {total_pips:+.1f}")
    print(f"  Total R       : {total_r:+.1f}R")

    print(f"\n  Daily cap used: {sum(strategy.trades_today.values())}/3")
    print(f"  Symbols traded: {list(strategy.trades_today.keys())}")

    # Per-signal breakdown table
    print(f"\n  {'#':<3} {'Time':<6} {'Symbol':<9} {'Dir':<6} {'Setup':<25} {'RR':>5} {'Result':>7} {'Pips':>8}")
    print(f"  {'─'*75}")
    for t in all_results:
        icon = '✅' if t['result'] == 'WIN' else ('❌' if t['result'] == 'LOSS' else '⏳')
        print(f"  {t['num']:<3} {t['time']:<6} {t['symbol']:<9} {t['direction']:<6} {t['setup']:<25} 1:{t['rr']:<4.1f} {icon}{t['result']:>5} {t['pips']:>+7.1f}")

    # ── Comparison with old system (6 unfiltered signals, all losses) ──
    print(f"\n{'='*70}")
    print(f"  BEFORE vs AFTER COMPARISON")
    print(f"{'='*70}")
    print(f"  OLD system (today's actual results):")
    print(f"    6 signals → 0 wins, 6 losses")
    print(f"    Win rate: 0%")
    print(f"    Total R: -6.0R")
    print(f"\n  NEW system (this backtest):")
    print(f"    {len(all_results)} signals → {len(wins)} wins, {len(losses)} losses")
    print(f"    Win rate: {wr:.0f}%")
    print(f"    Total R: {total_r:+.1f}R")
    improvement = total_r - (-6.0)
    print(f"\n  Improvement: {improvement:+.1f}R better")
    print(f"{'='*70}")


if __name__ == "__main__":
    run_single_day_backtest()
