#!/usr/bin/env python3
"""
Out-of-sample validation backtest — tests on different date range
to confirm the fixes aren't overfitted.
"""

import sys
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict
from collections import defaultdict

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def download_mtf_data(yf_symbol, start, end):
    import yfinance as yf
    mtf = {}
    intervals = {'5M': '5m', '15M': '15m', '1H': '1h'}
    for tf, yf_interval in intervals.items():
        print(f"  {tf}...", end=" ", flush=True)
        try:
            data = yf.download(yf_symbol, start=start, end=end, interval=yf_interval, progress=False)
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
            print(f"OK {len(candles)}")
        except Exception as e:
            print(f"FAIL {e}")
            mtf[tf] = []
    if mtf.get('1H'):
        c4h, buf = [], []
        for c in mtf['1H']:
            buf.append(c)
            if len(buf) == 4:
                c4h.append({'timestamp': buf[0]['timestamp'], 'time': buf[0]['time'],
                            'open': buf[0]['open'], 'high': max(b['high'] for b in buf),
                            'low': min(b['low'] for b in buf), 'close': buf[-1]['close'],
                            'volume': sum(b['volume'] for b in buf)})
                buf = []
        mtf['4H'] = c4h
        print(f"  4H built: {len(c4h)}")
    return mtf


def simulate_trade(signal, candles_5m, start_idx, max_candles=576):
    entry, sl, tp = signal['entry_price'], signal['stop_loss'], signal['take_profit']
    direction = signal['direction']
    sl_dist, tp_dist = abs(entry - sl), abs(tp - entry)
    for i in range(start_idx, min(start_idx + max_candles, len(candles_5m))):
        c = candles_5m[i]
        if direction == 'long':
            if c['low'] <= sl:
                return {'result': 'LOSS', 'pips': -round(sl_dist*10000, 1) if sl_dist < 1 else -round(sl_dist,1)}
            if c['high'] >= tp:
                return {'result': 'WIN', 'pips': round(tp_dist*10000, 1) if tp_dist < 1 else round(tp_dist,1)}
        else:
            if c['high'] >= sl:
                return {'result': 'LOSS', 'pips': -round(sl_dist*10000, 1) if sl_dist < 1 else -round(sl_dist,1)}
            if c['low'] <= tp:
                return {'result': 'WIN', 'pips': round(tp_dist*10000, 1) if tp_dist < 1 else round(tp_dist,1)}
    return {'result': 'OPEN', 'pips': 0}


def run_validation():
    from core.flexible_ict_strategy import FlexibleICTStrategy
    import logging
    logging.basicConfig(level=logging.WARNING)

    # Earlier period: Feb 1 - Mar 5 (out-of-sample)
    end_dt = datetime(2026, 3, 5, tzinfo=timezone.utc)
    start_dt = end_dt - timedelta(days=30)
    lookback_start = (start_dt - timedelta(days=7)).strftime('%Y-%m-%d')
    end_date = (end_dt + timedelta(days=1)).strftime('%Y-%m-%d')

    yf_map = {'EUR_USD': '6E=F', 'GBP_USD': '6B=F'}
    symbols = ['EUR_USD', 'GBP_USD']

    print("=" * 70)
    print("  OUT-OF-SAMPLE VALIDATION")
    print(f"  Period: {start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}")
    print("=" * 70)

    all_mtf = {}
    for symbol in symbols:
        print(f"\nDownloading {symbol}...")
        all_mtf[symbol] = download_mtf_data(yf_map[symbol], lookback_start, end_date)

    strategy = FlexibleICTStrategy()
    strategy.current_date = None
    strategy.trades_today = {}
    strategy._recent_losses = {}
    strategy._last_signal_time = {}
    strategy._recent_signals = {}
    strategy._consecutive_losses = 0
    strategy._circuit_breaker_until = 0
    strategy._daily_losses = 0

    all_results = []
    window = 150
    day_start_ts = int(start_dt.timestamp())
    day_end_ts = int(end_dt.timestamp())

    timed_events = []
    for symbol in symbols:
        for idx, c in enumerate(all_mtf[symbol].get('5M', [])):
            if day_start_ts <= c['timestamp'] < day_end_ts:
                timed_events.append((c['timestamp'], symbol, idx))
    timed_events.sort(key=lambda x: x[0])
    print(f"\nEvents to process: {len(timed_events)}")

    for ts, symbol, idx in timed_events:
        candles_5m = all_mtf[symbol].get('5M', [])
        if idx < window:
            continue

        slice_5m = candles_5m[max(0, idx - window):idx + 1]
        slice_1h = [c for c in all_mtf[symbol].get('1H', []) if c['timestamp'] <= ts][-100:]
        slice_4h = [c for c in all_mtf[symbol].get('4H', []) if c['timestamp'] <= ts][-50:]
        slice_15m = [c for c in all_mtf[symbol].get('15M', []) if c['timestamp'] <= ts][-100:]
        local_mtf = {'5M': slice_5m, '1H': slice_1h, '4H': slice_4h, '15M': slice_15m}

        all_market_data = {}
        for s in symbols:
            s_5m = [c for c in all_mtf[s].get('5M', []) if c['timestamp'] <= ts][-100:]
            s_1h = [c for c in all_mtf[s].get('1H', []) if c['timestamp'] <= ts][-50:]
            all_market_data[s] = {'5M': s_5m, '1H': s_1h}
        strategy.set_all_market_data(all_market_data)

        if not strategy.can_take_trade(ts, symbol):
            continue
        if not strategy.check_signal_cooldown(symbol, ts):
            continue

        strategy._last_rejection_reasons = []
        signal = strategy.analyze(slice_5m, symbol=symbol, mtf_data=local_mtf, backtest_mode=True)

        if signal:
            result = simulate_trade(signal, candles_5m, idx + 1)
            if result['result'] == 'LOSS':
                strategy.record_loss(symbol, signal['entry_price'], signal['direction'], ts)
            elif result['result'] == 'WIN':
                strategy.record_win(symbol)

            all_results.append({
                'symbol': symbol, 'direction': signal['direction'],
                'setup': signal['setup_type'], 'result': result['result'],
                'pips': result['pips'], 'rr': signal['risk_reward'],
                'time': datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M'),
            })

    # Results
    print(f"\n{'='*70}")
    wins = [t for t in all_results if t['result'] == 'WIN']
    losses = [t for t in all_results if t['result'] == 'LOSS']
    closed = len(wins) + len(losses)
    total_pips = sum(t['pips'] for t in all_results if t['result'] != 'OPEN')
    wr = len(wins) / closed * 100 if closed else 0

    print(f"  Signals: {len(all_results)}, Closed: {closed}")
    print(f"  Wins: {len(wins)}, Losses: {len(losses)}")
    print(f"  Win Rate: {wr:.1f}%")
    print(f"  Total Pips: {total_pips:+.1f}")

    setup_results = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pips': 0})
    for t in all_results:
        if t['result'] in ('WIN', 'LOSS'):
            setup_results[t['setup']]['wins' if t['result'] == 'WIN' else 'losses'] += 1
            setup_results[t['setup']]['pips'] += t['pips']

    print(f"\n  By Setup:")
    for s in sorted(setup_results.keys()):
        r = setup_results[s]
        total_s = r['wins'] + r['losses']
        wr_s = r['wins'] / total_s * 100 if total_s > 0 else 0
        print(f"    {s:<25} W:{r['wins']:>2} L:{r['losses']:>2} WR:{wr_s:>5.1f}%  Pips:{r['pips']:>+7.1f}")

    print(f"\n  Trade list:")
    for i, t in enumerate(all_results):
        icon = '✅' if t['result'] == 'WIN' else ('❌' if t['result'] == 'LOSS' else '⏳')
        print(f"    {i+1:>2}. {t['time']} {t['symbol']:<9} {t['direction']:<6} {t['setup']:<24} 1:{t['rr']:.1f} {icon} {t['pips']:>+7.1f}p")
    print(f"{'='*70}")


if __name__ == "__main__":
    run_validation()
