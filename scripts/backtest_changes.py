#!/usr/bin/env python3
"""
Multi-Day Backtest — Compare OLD vs NEW strategy
==================================================
Downloads real market data from yfinance for the full trade history period
(Feb 17 - Mar 3, 2026) and replays it through the FlexibleICTStrategy
with ALL new fixes applied:

  1. LIQ_SWEEP_ENGULF hardened (BOS required, gold blocked, HTF mandatory)
  2. Consecutive loss circuit breaker (3 losses → 4h pause)
  3. Daily loss limit (5/day)
  4. Strategy priority reordered (HTF_LIQUIDITY_BOS first everywhere)
  5. RR caps per setup type (Opt4 max 3:1, Opt5/6 max 5:1)

Then compares "new strategy" backtest results against actual historical
trade results to measure improvement.

Usage:
    python scripts/backtest_changes.py
"""

import sys
import os
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from copy import deepcopy
from collections import Counter, defaultdict

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


# ── data download ────────────────────────────────────────────────────
def download_mtf_data(yf_symbol: str, start: str, end: str) -> Dict[str, List[dict]]:
    """Download multi-timeframe candles from yfinance."""
    import yfinance as yf

    mtf = {}
    intervals = {'5M': '5m', '15M': '15m', '1H': '1h'}

    for tf, yf_interval in intervals.items():
        print(f"  {tf} ({yf_interval})...", end=" ", flush=True)
        try:
            data = yf.download(
                yf_symbol,
                start=start,
                end=end,
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

    # Build 4H from 1H
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
        print(f"  4H built from 1H: {len(candles_4h)} candles")

    return mtf


# ── trade simulator ──────────────────────────────────────────────────
def simulate_trade(signal: dict, candles_5m: List[dict], start_idx: int,
                   max_candles: int = 576) -> dict:
    """Walk 5M candles to see if TP or SL hit first.
    max_candles=576 = 48 hours (2 trading days)."""
    entry = signal['entry_price']
    sl = signal['stop_loss']
    tp = signal['take_profit']
    direction = signal['direction']
    sl_dist = abs(entry - sl)
    tp_dist = abs(tp - entry)
    is_gold = sl_dist > 1  # Gold distances are in dollars, forex in pips

    end_idx = min(start_idx + max_candles, len(candles_5m))

    for i in range(start_idx, end_idx):
        c = candles_5m[i]
        if direction == 'long':
            if c['low'] <= sl:
                pips = -round(sl_dist * 10000, 1) if not is_gold else -round(sl_dist, 1)
                return {'result': 'LOSS', 'pips': pips,
                        'rr': round(tp_dist / sl_dist, 1) if sl_dist else 0,
                        'exit_time': c['time'], 'exit_idx': i}
            if c['high'] >= tp:
                pips = round(tp_dist * 10000, 1) if not is_gold else round(tp_dist, 1)
                return {'result': 'WIN', 'pips': pips,
                        'rr': round(tp_dist / sl_dist, 1) if sl_dist else 0,
                        'exit_time': c['time'], 'exit_idx': i}
        else:
            if c['high'] >= sl:
                pips = -round(sl_dist * 10000, 1) if not is_gold else -round(sl_dist, 1)
                return {'result': 'LOSS', 'pips': pips,
                        'rr': round(tp_dist / sl_dist, 1) if sl_dist else 0,
                        'exit_time': c['time'], 'exit_idx': i}
            if c['low'] <= tp:
                pips = round(tp_dist * 10000, 1) if not is_gold else round(tp_dist, 1)
                return {'result': 'WIN', 'pips': pips,
                        'rr': round(tp_dist / sl_dist, 1) if sl_dist else 0,
                        'exit_time': c['time'], 'exit_idx': i}

    return {'result': 'EXPIRED', 'pips': 0, 'rr': 0, 'exit_time': 'expired', 'exit_idx': end_idx}


# ── load actual trade history for comparison ────────────────────────
def load_actual_results():
    """Load actual trade results from trade_history.json."""
    with open(os.path.join(project_root, 'data', 'trade_history.json'), 'r') as f:
        trades = json.load(f)

    # Only include filled trades (have a status)
    filled = [t for t in trades if t.get('status') in ('win', 'loss')]
    return filled


# ── main backtest ────────────────────────────────────────────────────
def run_multi_day_backtest():
    from core.flexible_ict_strategy import FlexibleICTStrategy
    import logging

    logging.basicConfig(level=logging.WARNING)
    logger = logging.getLogger('backtest')

    # ── configuration ──
    # Cover the full trade history period + a few days lookback for 4H
    trade_start = datetime(2026, 2, 17, tzinfo=timezone.utc)
    trade_end = datetime(2026, 3, 4, tzinfo=timezone.utc)   # Inclusive to Mar 3
    lookback_start = (trade_start - timedelta(days=7)).strftime('%Y-%m-%d')
    end_date = trade_end.strftime('%Y-%m-%d')

    yf_map = {
        'EUR_USD': '6E=F',
        'GBP_USD': '6B=F',
        'XAU_USD': 'GC=F',
    }

    symbols = ['EUR_USD', 'GBP_USD', 'XAU_USD']

    print("=" * 72)
    print("  MULTI-DAY BACKTEST — Feb 17 to Mar 3, 2026")
    print("  Strategy: FlexibleICTStrategy with ALL fixes applied")
    print("  Fixes: Opt4 hardened, circuit breaker, priority reorder, RR caps")
    print("=" * 72)

    # ── download data ──
    all_mtf = {}
    for symbol in symbols:
        yf_ticker = yf_map[symbol]
        print(f"\n📥 Downloading {symbol} ({yf_ticker})...")
        all_mtf[symbol] = download_mtf_data(yf_ticker, lookback_start, end_date)

    # Verify data
    for symbol in symbols:
        n5m = len(all_mtf[symbol].get('5M', []))
        n1h = len(all_mtf[symbol].get('1H', []))
        n4h = len(all_mtf[symbol].get('4H', []))
        print(f"  {symbol}: 5M={n5m}, 1H={n1h}, 4H={n4h}")
        if n5m < 100:
            print(f"  ⚠️ WARNING: Not enough 5M data for {symbol}!")

    # ── run strategy ──
    strategy = FlexibleICTStrategy()
    strategy.current_date = None
    strategy.trades_today = {}
    strategy._recent_losses = {}
    strategy._last_signal_time = {}
    strategy._recent_signals = {}
    strategy._consecutive_losses = 0
    strategy._circuit_breaker_until = 0
    strategy._daily_losses = 0
    strategy._daily_loss_date = None

    all_results = []
    window = 150

    # Get timestamp range for actual trade period
    day_start_ts = int(trade_start.timestamp())
    day_end_ts = int(trade_end.timestamp())

    # Build chronological event stream across all symbols
    timed_events = []
    for symbol in symbols:
        candles_5m = all_mtf[symbol].get('5M', [])
        for idx, c in enumerate(candles_5m):
            if day_start_ts <= c['timestamp'] < day_end_ts:
                timed_events.append((c['timestamp'], symbol, idx))

    timed_events.sort(key=lambda x: x[0])

    print(f"\n{'='*72}")
    print(f"  REPLAYING {len(timed_events)} price events across {len(symbols)} symbols")
    print(f"  Period: {trade_start.strftime('%b %d')} to {trade_end.strftime('%b %d, %Y')}")
    print(f"{'='*72}")

    signal_num = 0
    circuit_breaker_blocks = 0
    daily_limit_blocks = 0
    current_day = None

    for ts, symbol, idx in timed_events:
        candles_5m = all_mtf[symbol].get('5M', [])

        # Print day header when day changes
        day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')
        if day != current_day:
            current_day = day
            dow = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%A')
            # Skip weekends
            if dow in ('Saturday', 'Sunday'):
                continue
            if signal_num > 0:
                print()  # Spacing between days
            print(f"\n  ─── {current_day} ({dow}) ───")

        # Need enough lookback
        if idx < window:
            continue

        # Build MTF slice
        slice_5m = candles_5m[max(0, idx - window):idx + 1]
        slice_1h = [c for c in all_mtf[symbol].get('1H', []) if c['timestamp'] <= ts][-100:]
        slice_4h = [c for c in all_mtf[symbol].get('4H', []) if c['timestamp'] <= ts][-50:]
        slice_15m = [c for c in all_mtf[symbol].get('15M', []) if c['timestamp'] <= ts][-100:]

        local_mtf = {'5M': slice_5m, '1H': slice_1h, '4H': slice_4h, '15M': slice_15m}

        # Check filters
        cap_ok = strategy.can_take_trade(ts, symbol)
        cooldown_ok = strategy.check_signal_cooldown(symbol, ts)

        if not cap_ok or not cooldown_ok:
            continue

        # Circuit breaker check (analyze() skips this in backtest_mode)
        if strategy.check_circuit_breaker(ts):
            remaining = ''
            if strategy._circuit_breaker_until > ts:
                mins_left = (strategy._circuit_breaker_until - ts) / 60
                remaining = f' ({mins_left:.0f}min left)'
            # Only log once per unique block event (avoid spam)
            circuit_breaker_blocks += 1
            continue

        # Run analysis
        strategy._last_rejection_reasons = []
        signal = strategy.analyze(slice_5m, symbol=symbol, mtf_data=local_mtf, backtest_mode=True)

        if signal:
            signal_num += 1

            # Simulate trade
            result = simulate_trade(signal, candles_5m, idx + 1)

            # Update circuit breaker state
            if result['result'] == 'LOSS':
                strategy.record_loss(symbol, signal['entry_price'], signal['direction'], ts)
            elif result['result'] == 'WIN':
                strategy.record_win(symbol)

            entry_time = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%H:%M')
            dir_icon = '🟢' if signal['direction'] == 'long' else '🔴'
            result_icon = '✅' if result['result'] == 'WIN' else ('❌' if result['result'] == 'LOSS' else '⏳')

            trade_info = {
                'num': signal_num,
                'date': day,
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
                'consec_losses': strategy._consecutive_losses,
            }
            all_results.append(trade_info)

            print(f"    #{signal_num:<3} {entry_time} {dir_icon} {symbol:<9} {signal['setup_type']:<22} "
                  f"RR 1:{signal['risk_reward']:<4.1f} {result_icon} {result['result']:<7} "
                  f"{result['pips']:>+8.1f} pips")

    # ── Load actual results for comparison ──
    actual_trades = load_actual_results()

    # ── Summary ──
    print(f"\n{'='*72}")
    print(f"  BACKTEST RESULTS — NEW STRATEGY")
    print(f"{'='*72}")

    if not all_results:
        print("  No signals generated.")
        print("  All filtered — this means the strategy is too restrictive.")
        return

    wins = [t for t in all_results if t['result'] == 'WIN']
    losses = [t for t in all_results if t['result'] == 'LOSS']
    expired = [t for t in all_results if t['result'] == 'EXPIRED']
    closed = len(wins) + len(losses)

    total_pips = sum(t['pips'] for t in all_results if t['result'] != 'EXPIRED')
    total_r = sum(t['rr'] for t in wins) - len(losses)
    wr = len(wins) / closed * 100 if closed else 0

    # Per-setup breakdown
    setup_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pips': 0, 'r': 0})
    for t in all_results:
        if t['result'] == 'EXPIRED':
            continue
        s = setup_stats[t['setup']]
        if t['result'] == 'WIN':
            s['wins'] += 1
            s['r'] += t['rr']
        else:
            s['losses'] += 1
            s['r'] -= 1
        s['pips'] += t['pips']

    # Per-symbol breakdown
    symbol_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pips': 0, 'r': 0})
    for t in all_results:
        if t['result'] == 'EXPIRED':
            continue
        s = symbol_stats[t['symbol']]
        if t['result'] == 'WIN':
            s['wins'] += 1
            s['r'] += t['rr']
        else:
            s['losses'] += 1
            s['r'] -= 1
        s['pips'] += t['pips']

    # Max consecutive losses
    max_streak = 0
    current_streak = 0
    for t in all_results:
        if t['result'] == 'LOSS':
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        elif t['result'] == 'WIN':
            current_streak = 0

    print(f"\n  📊 Overall Stats:")
    print(f"     Signals Generated : {len(all_results)}")
    print(f"     Closed Trades     : {closed}")
    print(f"     Wins              : {len(wins)}")
    print(f"     Losses            : {len(losses)}")
    print(f"     Expired/Open      : {len(expired)}")
    print(f"     Win Rate          : {wr:.1f}%")
    print(f"     Total Pips        : {total_pips:+.1f}")
    print(f"     Total R           : {total_r:+.1f}R")
    print(f"     Max Consec Losses : {max_streak}")
    print(f"     Circuit Breaker   : blocked {circuit_breaker_blocks} analysis cycles")

    print(f"\n  📈 Per Setup Type:")
    print(f"     {'Setup':<25} {'W':>3} {'L':>3} {'WR%':>6} {'Pips':>9} {'R':>7}")
    print(f"     {'─'*55}")
    for setup, s in sorted(setup_stats.items()):
        total = s['wins'] + s['losses']
        wr_s = s['wins'] / total * 100 if total else 0
        print(f"     {setup:<25} {s['wins']:>3} {s['losses']:>3} {wr_s:>5.1f}% {s['pips']:>+8.1f} {s['r']:>+6.1f}R")

    print(f"\n  🌐 Per Symbol:")
    print(f"     {'Symbol':<12} {'W':>3} {'L':>3} {'WR%':>6} {'Pips':>9} {'R':>7}")
    print(f"     {'─'*45}")
    for sym, s in sorted(symbol_stats.items()):
        total = s['wins'] + s['losses']
        wr_s = s['wins'] / total * 100 if total else 0
        print(f"     {sym:<12} {s['wins']:>3} {s['losses']:>3} {wr_s:>5.1f}% {s['pips']:>+8.1f} {s['r']:>+6.1f}R")

    # ── Comparison with actual results ──
    print(f"\n{'='*72}")
    print(f"  BEFORE vs AFTER COMPARISON")
    print(f"{'='*72}")

    actual_wins = sum(1 for t in actual_trades if t['status'] == 'win')
    actual_losses = sum(1 for t in actual_trades if t['status'] == 'loss')
    actual_closed = actual_wins + actual_losses
    actual_wr = actual_wins / actual_closed * 100 if actual_closed else 0
    actual_pips = sum(t.get('pips_result', 0) for t in actual_trades)
    actual_r = sum(t.get('rr_achieved', 0) for t in actual_trades if t['status'] == 'win') - actual_losses

    # Actual max consecutive losses
    actual_max_streak = 0
    actual_streak = 0
    for t in actual_trades:
        if t['status'] == 'loss':
            actual_streak += 1
            actual_max_streak = max(actual_max_streak, actual_streak)
        else:
            actual_streak = 0

    # Actual per-setup breakdown
    actual_setup_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pips': 0})
    for t in actual_trades:
        s = actual_setup_stats[t['setup_type']]
        if t['status'] == 'win':
            s['wins'] += 1
        else:
            s['losses'] += 1
        s['pips'] += t.get('pips_result', 0)

    print(f"\n  {'Metric':<25} {'OLD (Actual)':>15} {'NEW (Backtest)':>15} {'Change':>10}")
    print(f"  {'─'*67}")
    print(f"  {'Trades':<25} {actual_closed:>15} {closed:>15} {closed - actual_closed:>+10}")
    print(f"  {'Wins':<25} {actual_wins:>15} {len(wins):>15} {len(wins) - actual_wins:>+10}")
    print(f"  {'Losses':<25} {actual_losses:>15} {len(losses):>15} {len(losses) - actual_losses:>+10}")
    print(f"  {'Win Rate':<25} {actual_wr:>14.1f}% {wr:>14.1f}% {wr - actual_wr:>+9.1f}%")
    print(f"  {'Total Pips':<25} {actual_pips:>+14.1f} {total_pips:>+14.1f} {total_pips - actual_pips:>+9.1f}")
    print(f"  {'Total R':<25} {actual_r:>+14.1f}R {total_r:>+14.1f}R {total_r - actual_r:>+8.1f}R")
    print(f"  {'Max Consec Losses':<25} {actual_max_streak:>15} {max_streak:>15} {max_streak - actual_max_streak:>+10}")

    print(f"\n  Per-Setup Old vs New:")
    all_setups = sorted(set(list(actual_setup_stats.keys()) + list(setup_stats.keys())))
    print(f"  {'Setup':<25} {'Old W/L':>10} {'Old Pips':>10} {'New W/L':>10} {'New Pips':>10}")
    print(f"  {'─'*67}")
    for setup in all_setups:
        old = actual_setup_stats.get(setup, {'wins': 0, 'losses': 0, 'pips': 0})
        new = setup_stats.get(setup, {'wins': 0, 'losses': 0, 'pips': 0})
        print(f"  {setup:<25} {old['wins']:>3}W/{old['losses']:<3}L {old['pips']:>+9.1f} "
              f"{new['wins']:>3}W/{new['losses']:<3}L {new['pips']:>+9.1f}")

    # ── Key insights ──
    print(f"\n{'='*72}")
    print(f"  KEY INSIGHTS")
    print(f"{'='*72}")

    if total_pips > actual_pips:
        print(f"  ✅ Pips improved by {total_pips - actual_pips:+.1f}")
    else:
        print(f"  ⚠️  Pips decreased by {total_pips - actual_pips:.1f}")

    if wr > actual_wr:
        print(f"  ✅ Win rate improved from {actual_wr:.1f}% → {wr:.1f}%")
    else:
        print(f"  ⚠️  Win rate changed from {actual_wr:.1f}% → {wr:.1f}%")

    if max_streak < actual_max_streak:
        print(f"  ✅ Max losing streak reduced from {actual_max_streak} → {max_streak}")
    elif max_streak == actual_max_streak:
        print(f"  ⏸️  Max losing streak unchanged at {max_streak}")
    else:
        print(f"  ⚠️  Max losing streak increased from {actual_max_streak} → {max_streak}")

    liq_old = actual_setup_stats.get('LIQ_SWEEP_ENGULF', {'wins': 0, 'losses': 0, 'pips': 0})
    liq_new = setup_stats.get('LIQ_SWEEP_ENGULF', {'wins': 0, 'losses': 0, 'pips': 0})
    if liq_new['losses'] < liq_old['losses']:
        print(f"  ✅ LIQ_SWEEP_ENGULF losses reduced: {liq_old['losses']} → {liq_new['losses']}")
    elif liq_new['losses'] == 0 and liq_old['losses'] > 0:
        print(f"  ✅ LIQ_SWEEP_ENGULF completely avoided bad trades (was {liq_old['losses']}L)")

    if total_r > actual_r:
        print(f"  ✅ Risk-adjusted return improved: {actual_r:+.1f}R → {total_r:+.1f}R")

    print(f"\n{'='*72}")

    # Trade-by-trade table
    print(f"\n  Full Trade Log:")
    print(f"  {'#':<3} {'Date':<12} {'Time':<6} {'Symbol':<9} {'Dir':<6} {'Setup':<22} {'RR':>5} {'Result':>7} {'Pips':>8}")
    print(f"  {'─'*80}")
    for t in all_results:
        icon = '✅' if t['result'] == 'WIN' else ('❌' if t['result'] == 'LOSS' else '⏳')
        print(f"  {t['num']:<3} {t['date']:<12} {t['time']:<6} {t['symbol']:<9} {t['direction']:<6} "
              f"{t['setup']:<22} 1:{t['rr']:<4.1f} {icon}{t['result']:>6} {t['pips']:>+7.1f}")
    print(f"  {'─'*80}")


if __name__ == "__main__":
    run_multi_day_backtest()
