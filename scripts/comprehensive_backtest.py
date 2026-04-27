#!/usr/bin/env python3
"""
Comprehensive Multi-Week Backtest
===================================
Downloads recent market data and replays through FlexibleICTStrategy
to measure current performance and diagnose issues.

Usage:
    python scripts/comprehensive_backtest.py
"""

import sys
import os
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from collections import Counter, defaultdict

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Load API keys from forex-bot.env (project root)
_env_file = os.path.join(project_root, 'forex-bot.env')
if os.path.exists(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# Twelve Data symbol map (internal → API format)
_TD_SYMBOL_MAP = {
    'EUR_USD': 'EUR/USD',
    'GBP_USD': 'GBP/USD',
    'EURUSD':  'EUR/USD',
    'GBPUSD':  'GBP/USD',
}

# yfinance fallback symbol map
_YF_SYMBOL_MAP = {
    'EUR_USD': '6E=F',
    'GBP_USD': '6B=F',
}


def _build_4h_from_1h(candles_1h: List[dict]) -> List[dict]:
    """Aggregate 1H candles into 4H candles."""
    candles_4h = []
    buf = []
    for c in candles_1h:
        buf.append(c)
        if len(buf) == 4:
            candles_4h.append({
                'timestamp': buf[0]['timestamp'],
                'time':      buf[0]['time'],
                'open':      buf[0]['open'],
                'high':      max(b['high'] for b in buf),
                'low':       min(b['low'] for b in buf),
                'close':     buf[-1]['close'],
                'volume':    sum(b['volume'] for b in buf),
            })
            buf = []
    return candles_4h


import time as _time
import requests as _req

# Global rate limiter: track all Twelve Data call timestamps
_TD_CALL_TIMES: List[float] = []
_TD_MINUTE_LIMIT = 7  # Stay safely under the 8/min free tier limit


def _td_wait():
    """Block until the per-minute rate limit allows another API call, then record it."""
    while True:
        now = _time.time()
        _TD_CALL_TIMES[:] = [t for t in _TD_CALL_TIMES if now - t < 60]
        if len(_TD_CALL_TIMES) < _TD_MINUTE_LIMIT:
            break
        oldest = min(_TD_CALL_TIMES)
        wait = 60 - (now - oldest) + 1.5
        if wait > 0:
            print(f"\n  [TD] Rate limit reached, waiting {wait:.0f}s...", end=" ", flush=True)
            _time.sleep(wait)
    _TD_CALL_TIMES.append(_time.time())


def _fetch_td_range(td_symbol: str, interval_td: str, start: str, end: str, api_key: str) -> List[dict]:
    """Fetch OHLCV candles from Twelve Data for a date range, paginating if needed."""
    BASE_URL = "https://api.twelvedata.com/time_series"
    INTERVAL_MINS = {'5min': 5, '15min': 15, '1h': 60, '4h': 240}

    all_candles: List[dict] = []
    current_end = end
    start_ts = int(datetime.strptime(start, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp())
    interval_min = INTERVAL_MINS.get(interval_td, 5)

    for _iteration in range(10):  # Max 10 paginated requests (covers 5M over 170 days)
        params = {
            'symbol':     td_symbol,
            'interval':   interval_td,
            'outputsize': 5000,
            'start_date': start,
            'end_date':   current_end,
            'apikey':     api_key,
        }
        _td_wait()  # Enforce global rate limit before every call
        try:
            resp = _req.get(BASE_URL, params=params, timeout=30)
            data = resp.json()
        except Exception as e:
            print(f"  [TD] Request error: {e}")
            break

        if data.get('status') == 'error':
            print(f"  [TD] API error: {data.get('message', 'unknown')}")
            break

        values = data.get('values', [])
        if not values:
            break

        # Twelve Data returns newest-first; parse all into candle dicts
        for v in values:
            try:
                dt = datetime.strptime(v['datetime'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                all_candles.append({
                    'timestamp': int(dt.timestamp()),
                    'time':      v['datetime'][:16],
                    'open':      float(v['open']),
                    'high':      float(v['high']),
                    'low':       float(v['low']),
                    'close':     float(v['close']),
                    'volume':    int(v.get('volume', 0) or 0),
                })
            except (ValueError, KeyError):
                continue

        if len(values) < 5000:
            break  # Received all data in range

        # Paginate backward: oldest candle is the last element (newest-first list)
        oldest_dt = datetime.strptime(values[-1]['datetime'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        if int(oldest_dt.timestamp()) <= start_ts:
            break  # Covered the full requested range

        prev_end = oldest_dt - timedelta(minutes=interval_min)
        current_end = prev_end.strftime('%Y-%m-%d %H:%M:%S')

    all_candles.sort(key=lambda c: c['timestamp'])
    # Deduplicate by timestamp (pagination overlap)
    seen: set = set()
    unique = []
    for c in all_candles:
        if c['timestamp'] not in seen:
            seen.add(c['timestamp'])
            unique.append(c)
    return unique


def _download_mtf_twelvedata(symbol: str, start: str, end: str, api_key: str) -> Dict[str, List[dict]]:
    """Download multi-timeframe data from Twelve Data (spot forex prices)."""
    td_symbol = _TD_SYMBOL_MAP.get(symbol, symbol)
    mtf: Dict[str, List[dict]] = {}
    intervals = {'5M': '5min', '15M': '15min', '1H': '1h'}

    for tf, td_interval in intervals.items():
        print(f"  {tf} ({td_interval}, Twelve Data)...", end=" ", flush=True)
        candles = _fetch_td_range(td_symbol, td_interval, start, end, api_key)
        mtf[tf] = candles
        print(f"OK {len(candles)} candles")

    if mtf.get('1H'):
        mtf['4H'] = _build_4h_from_1h(mtf['1H'])
        print(f"  4H built: {len(mtf['4H'])} candles")

    return mtf


def _download_mtf_yfinance(symbol: str, start: str, end: str) -> Dict[str, List[dict]]:
    """Download multi-timeframe data from yfinance (fallback)."""
    import yfinance as yf

    yf_symbol = _YF_SYMBOL_MAP.get(symbol, symbol)
    mtf: Dict[str, List[dict]] = {}
    intervals = {'5M': '5m', '15M': '15m', '1H': '1h'}

    for tf, yf_interval in intervals.items():
        print(f"  {tf} ({yf_interval}, yfinance fallback)...", end=" ", flush=True)
        try:
            data = yf.download(yf_symbol, start=start, end=end,
                               interval=yf_interval, progress=False)
            candles = []
            for ts, row in data.iterrows():
                try:
                    candles.append({
                        'timestamp': int(ts.timestamp()),
                        'time': ts.strftime('%Y-%m-%d %H:%M'),
                        'open':  float(row['Open'].iloc[0])   if hasattr(row['Open'],   'iloc') else float(row['Open']),
                        'high':  float(row['High'].iloc[0])   if hasattr(row['High'],   'iloc') else float(row['High']),
                        'low':   float(row['Low'].iloc[0])    if hasattr(row['Low'],    'iloc') else float(row['Low']),
                        'close': float(row['Close'].iloc[0])  if hasattr(row['Close'],  'iloc') else float(row['Close']),
                        'volume': float(row['Volume'].iloc[0]) if hasattr(row['Volume'], 'iloc') else float(row.get('Volume', 0)),
                    })
                except Exception:
                    pass
            candles.sort(key=lambda x: x['timestamp'])
            mtf[tf] = candles
            print(f"OK {len(candles)} candles")
        except Exception as e:
            print(f"FAIL {e}")
            mtf[tf] = []

    if mtf.get('1H'):
        mtf['4H'] = _build_4h_from_1h(mtf['1H'])
        print(f"  4H built: {len(mtf['4H'])} candles")

    return mtf


def download_mtf_data(symbol: str, start: str, end: str) -> Dict[str, List[dict]]:
    """Download multi-timeframe candles. Uses Twelve Data if key is available, else yfinance."""
    api_key = os.environ.get("TWELVE_DATA_API_KEY", "")
    if api_key:
        return _download_mtf_twelvedata(symbol, start, end, api_key)
    print(f"  [!] No TWELVE_DATA_API_KEY — falling back to yfinance futures")
    return _download_mtf_yfinance(symbol, start, end)


def simulate_trade(signal: dict, candles_5m: List[dict], start_idx: int,
                   max_candles: int = 576) -> dict:
    """Walk 5M candles to see if TP or SL hit first."""
    entry = signal['entry_price']
    sl = signal['stop_loss']
    tp = signal['take_profit']
    direction = signal['direction']
    sl_dist = abs(entry - sl)
    tp_dist = abs(tp - entry)

    for i in range(start_idx, min(start_idx + max_candles, len(candles_5m))):
        c = candles_5m[i]
        if direction == 'long':
            if c['low'] <= sl:
                return {'result': 'LOSS', 'pips': -round(sl_dist * 10000, 1) if sl_dist < 1 else -round(sl_dist, 1),
                        'rr': round(tp_dist / sl_dist, 1) if sl_dist else 0, 'exit_time': c.get('time', '')}
            if c['high'] >= tp:
                return {'result': 'WIN', 'pips': round(tp_dist * 10000, 1) if tp_dist < 1 else round(tp_dist, 1),
                        'rr': round(tp_dist / sl_dist, 1) if sl_dist else 0, 'exit_time': c.get('time', '')}
        else:
            if c['high'] >= sl:
                return {'result': 'LOSS', 'pips': -round(sl_dist * 10000, 1) if sl_dist < 1 else -round(sl_dist, 1),
                        'rr': round(tp_dist / sl_dist, 1) if sl_dist else 0, 'exit_time': c.get('time', '')}
            if c['low'] <= tp:
                return {'result': 'WIN', 'pips': round(tp_dist * 10000, 1) if tp_dist < 1 else round(tp_dist, 1),
                        'rr': round(tp_dist / sl_dist, 1) if sl_dist else 0, 'exit_time': c.get('time', '')}

    return {'result': 'OPEN', 'pips': 0, 'rr': 0, 'exit_time': 'still open'}


def run_backtest():
    from core.flexible_ict_strategy import FlexibleICTStrategy
    import logging
    logging.basicConfig(level=logging.WARNING)

    # Date range: 58 days back (Twelve Data handles full history; yfinance ~60 day limit)
    today = datetime.now(timezone.utc)
    lookback_start = (today - timedelta(days=58)).strftime('%Y-%m-%d')
    end_date = (today + timedelta(days=1)).strftime('%Y-%m-%d')
    start_dt = today - timedelta(days=55)  # Leave room for HTF context
    end_dt = today + timedelta(days=1)

    symbols = ['EUR_USD', 'GBP_USD']

    data_source = "Twelve Data" if os.environ.get("TWELVE_DATA_API_KEY") else "yfinance (fallback)"
    print("=" * 70)
    print("  COMPREHENSIVE BACKTEST")
    print(f"  Period: {start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}")
    print(f"  Symbols: {', '.join(symbols)}")
    print(f"  Data source: {data_source}")
    print("=" * 70)

    # Download data
    all_mtf = {}
    for symbol in symbols:
        print(f"\nDownloading {symbol}...")
        all_mtf[symbol] = download_mtf_data(symbol, lookback_start, end_date)

    # Run strategy
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

    # Interleave all symbols' 5M candles by timestamp
    timed_events = []
    for symbol in symbols:
        candles_5m = all_mtf[symbol].get('5M', [])
        for idx, c in enumerate(candles_5m):
            if day_start_ts <= c['timestamp'] < day_end_ts:
                timed_events.append((c['timestamp'], symbol, idx))

    timed_events.sort(key=lambda x: x[0])
    print(f"\nTotal 5M candle events to process: {len(timed_events)}")

    signal_num = 0
    for ts, symbol, idx in timed_events:
        candles_5m = all_mtf[symbol].get('5M', [])

        if idx < window:
            continue

        slice_5m = candles_5m[max(0, idx - window):idx + 1]
        slice_1h = [c for c in all_mtf[symbol].get('1H', []) if c['timestamp'] <= ts][-100:]
        slice_4h = [c for c in all_mtf[symbol].get('4H', []) if c['timestamp'] <= ts][-50:]
        slice_15m = [c for c in all_mtf[symbol].get('15M', []) if c['timestamp'] <= ts][-100:]

        local_mtf = {'5M': slice_5m, '1H': slice_1h, '4H': slice_4h, '15M': slice_15m}

        # Provide correlated pair data for SMT
        all_market_data = {}
        for s in symbols:
            s_5m = [c for c in all_mtf[s].get('5M', []) if c['timestamp'] <= ts][-100:]
            s_1h = [c for c in all_mtf[s].get('1H', []) if c['timestamp'] <= ts][-50:]
            all_market_data[s] = {'5M': s_5m, '1H': s_1h}
        strategy.set_all_market_data(all_market_data)

        cap_ok = strategy.can_take_trade(ts, symbol)
        cooldown_ok = strategy.check_signal_cooldown(symbol, ts)

        if not cap_ok or not cooldown_ok:
            continue

        strategy._last_rejection_reasons = []
        signal = strategy.analyze(slice_5m, symbol=symbol, mtf_data=local_mtf, backtest_mode=True)

        if signal:
            signal_num += 1
            result = simulate_trade(signal, candles_5m, idx + 1)

            if result['result'] == 'LOSS':
                strategy.record_loss(symbol, signal['entry_price'], signal['direction'], ts)
            elif result['result'] == 'WIN':
                strategy.record_win(symbol)

            entry_time = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
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
                'sl_pips': round(abs(signal['entry_price'] - signal['stop_loss']) * 10000, 1),
                'confirmations': signal['confirmations'],
                'confirmation_count': signal.get('confirmation_count', len(signal.get('confirmations', []))),
                'confidence': signal.get('confidence', 0),
                'htf_trend': signal.get('htf_trend', 'unknown'),
                'has_choch': signal.get('has_choch', False),
                'has_fib_confluence': signal.get('has_fib_confluence', False),
                'has_liquidity_sweep': signal.get('has_liquidity_sweep', False),
                'has_bos': signal.get('has_bos', False),
                'asian_sweep': signal.get('asian_sweep', False),
                'result': result['result'],
                'pips': result['pips'],
                'exit_time': result.get('exit_time', 'N/A'),
            }
            all_results.append(trade_info)

    # Print results
    print(f"\n{'='*70}")
    print(f"  BACKTEST RESULTS")
    print(f"{'='*70}")

    if not all_results:
        print("  No signals generated.")
        return

    wins = [t for t in all_results if t['result'] == 'WIN']
    losses = [t for t in all_results if t['result'] == 'LOSS']
    opens = [t for t in all_results if t['result'] == 'OPEN']
    closed = len(wins) + len(losses)

    total_pips = sum(t['pips'] for t in all_results if t['result'] != 'OPEN')
    wr = len(wins) / closed * 100 if closed else 0

    print(f"\n  Total Signals : {len(all_results)}")
    print(f"  Closed Trades : {closed}")
    print(f"  Wins          : {len(wins)}")
    print(f"  Losses        : {len(losses)}")
    print(f"  Still Open    : {len(opens)}")
    print(f"  Win Rate      : {wr:.1f}%")
    print(f"  Total Pips    : {total_pips:+.1f}")

    if wins:
        avg_win_pips = sum(t['pips'] for t in wins) / len(wins)
        print(f"  Avg Win Pips  : {avg_win_pips:+.1f}")
    if losses:
        avg_loss_pips = sum(t['pips'] for t in losses) / len(losses)
        print(f"  Avg Loss Pips : {avg_loss_pips:+.1f}")

    # By setup
    print(f"\n  === BY SETUP TYPE ===")
    setup_results = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pips': 0})
    for t in all_results:
        if t['result'] == 'WIN':
            setup_results[t['setup']]['wins'] += 1
            setup_results[t['setup']]['pips'] += t['pips']
        elif t['result'] == 'LOSS':
            setup_results[t['setup']]['losses'] += 1
            setup_results[t['setup']]['pips'] += t['pips']

    for setup in sorted(setup_results.keys()):
        s = setup_results[setup]
        total_s = s['wins'] + s['losses']
        wr_s = s['wins'] / total_s * 100 if total_s > 0 else 0
        print(f"  {setup:<25} W:{s['wins']:>2} L:{s['losses']:>2} WR:{wr_s:>5.1f}% Pips:{s['pips']:>+7.1f}")

    # By symbol
    print(f"\n  === BY SYMBOL ===")
    sym_results = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pips': 0})
    for t in all_results:
        if t['result'] in ('WIN', 'LOSS'):
            sym_results[t['symbol']]['wins' if t['result'] == 'WIN' else 'losses'] += 1
            sym_results[t['symbol']]['pips'] += t['pips']

    for sym in sorted(sym_results.keys()):
        s = sym_results[sym]
        total_s = s['wins'] + s['losses']
        wr_s = s['wins'] / total_s * 100 if total_s > 0 else 0
        print(f"  {sym:<15} W:{s['wins']:>2} L:{s['losses']:>2} WR:{wr_s:>5.1f}% Pips:{s['pips']:>+7.1f}")

    # By direction
    print(f"\n  === BY DIRECTION ===")
    dir_results = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pips': 0})
    for t in all_results:
        if t['result'] in ('WIN', 'LOSS'):
            dir_results[t['direction']]['wins' if t['result'] == 'WIN' else 'losses'] += 1
            dir_results[t['direction']]['pips'] += t['pips']

    for d in sorted(dir_results.keys()):
        s = dir_results[d]
        total_d = s['wins'] + s['losses']
        wr_d = s['wins'] / total_d * 100 if total_d > 0 else 0
        print(f"  {d:<10} W:{s['wins']:>2} L:{s['losses']:>2} WR:{wr_d:>5.1f}% Pips:{s['pips']:>+7.1f}")

    # By hour
    print(f"\n  === BY HOUR (UTC) ===")
    hour_results = defaultdict(lambda: {'wins': 0, 'losses': 0})
    for t in all_results:
        if t['result'] in ('WIN', 'LOSS'):
            hour = t['time'].split(' ')[1].split(':')[0]
            hour_results[hour]['wins' if t['result'] == 'WIN' else 'losses'] += 1

    for h in sorted(hour_results.keys()):
        s = hour_results[h]
        total_h = s['wins'] + s['losses']
        wr_h = s['wins'] / total_h * 100 if total_h > 0 else 0
        print(f"  {h}:00 UTC  W:{s['wins']:>2} L:{s['losses']:>2} WR:{wr_h:>5.1f}%")

    # SL analysis
    print(f"\n  === SL ANALYSIS ===")
    sl_pips_wins = [t['sl_pips'] for t in wins]
    sl_pips_losses = [t['sl_pips'] for t in losses]
    if sl_pips_wins:
        print(f"  Avg SL on wins:   {sum(sl_pips_wins)/len(sl_pips_wins):.1f} pips")
    if sl_pips_losses:
        print(f"  Avg SL on losses: {sum(sl_pips_losses)/len(sl_pips_losses):.1f} pips")

    # Confidence analysis
    print(f"\n  === BY CONFIDENCE ===")
    conf_buckets = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pips': 0})
    for t in all_results:
        if t['result'] in ('WIN', 'LOSS'):
            bucket = f"{t['confidence']:.2f}" if t['confidence'] else '0.00'
            conf_buckets[bucket]['wins' if t['result'] == 'WIN' else 'losses'] += 1
            conf_buckets[bucket]['pips'] += t['pips']
    for c in sorted(conf_buckets.keys()):
        s = conf_buckets[c]
        total_c = s['wins'] + s['losses']
        wr_c = s['wins'] / total_c * 100 if total_c else 0
        print(f"  Conf {c}  W:{s['wins']:>2} L:{s['losses']:>2} WR:{wr_c:>5.1f}% Pips:{s['pips']:>+7.1f}")

    # Confirmation count analysis
    print(f"\n  === BY CONFIRMATION COUNT ===")
    cc_buckets = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pips': 0})
    for t in all_results:
        if t['result'] in ('WIN', 'LOSS'):
            cc = t.get('confirmation_count', 0)
            cc_buckets[cc]['wins' if t['result'] == 'WIN' else 'losses'] += 1
            cc_buckets[cc]['pips'] += t['pips']
    for cc in sorted(cc_buckets.keys()):
        s = cc_buckets[cc]
        total_cc = s['wins'] + s['losses']
        wr_cc = s['wins'] / total_cc * 100 if total_cc else 0
        print(f"  {cc} confirms  W:{s['wins']:>2} L:{s['losses']:>2} WR:{wr_cc:>5.1f}% Pips:{s['pips']:>+7.1f}")

    # HTF trend analysis
    print(f"\n  === BY HTF TREND ===")
    htf_buckets = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pips': 0})
    for t in all_results:
        if t['result'] in ('WIN', 'LOSS'):
            htf_buckets[t['htf_trend']]['wins' if t['result'] == 'WIN' else 'losses'] += 1
            htf_buckets[t['htf_trend']]['pips'] += t['pips']
    for h in sorted(htf_buckets.keys()):
        s = htf_buckets[h]
        total_h = s['wins'] + s['losses']
        wr_h = s['wins'] / total_h * 100 if total_h else 0
        print(f"  {h:<12} W:{s['wins']:>2} L:{s['losses']:>2} WR:{wr_h:>5.1f}% Pips:{s['pips']:>+7.1f}")

    # ChoCH analysis
    print(f"\n  === BY CHOCH (Change of Character) ===")
    for val, label in [(True, 'has_choch'), (False, 'no_choch')]:
        group = [t for t in all_results if t['result'] in ('WIN', 'LOSS') and t.get('has_choch') == val]
        w = sum(1 for t in group if t['result'] == 'WIN')
        l = sum(1 for t in group if t['result'] == 'LOSS')
        p = sum(t['pips'] for t in group)
        total = w + l
        wr_v = w / total * 100 if total else 0
        print(f"  {label:<12} W:{w:>2} L:{l:>2} WR:{wr_v:>5.1f}% Pips:{p:>+7.1f}")

    # Fib confluence analysis
    print(f"\n  === BY FIB CONFLUENCE ===")
    for val, label in [(True, 'has_fib'), (False, 'no_fib')]:
        group = [t for t in all_results if t['result'] in ('WIN', 'LOSS') and t.get('has_fib_confluence') == val]
        w = sum(1 for t in group if t['result'] == 'WIN')
        l = sum(1 for t in group if t['result'] == 'LOSS')
        p = sum(t['pips'] for t in group)
        total = w + l
        wr_v = w / total * 100 if total else 0
        print(f"  {label:<12} W:{w:>2} L:{l:>2} WR:{wr_v:>5.1f}% Pips:{p:>+7.1f}")

    # Cross-tab: setup x symbol
    print(f"\n  === SETUP x SYMBOL ===")
    for setup in sorted(set(t['setup'] for t in all_results)):
        for sym in symbols:
            group = [t for t in all_results if t['result'] in ('WIN', 'LOSS') and t['setup'] == setup and t['symbol'] == sym]
            if not group:
                continue
            w = sum(1 for t in group if t['result'] == 'WIN')
            l = sum(1 for t in group if t['result'] == 'LOSS')
            p = sum(t['pips'] for t in group)
            total = w + l
            wr_v = w / total * 100 if total else 0
            print(f"  {setup:<20} {sym:<10} W:{w:>2} L:{l:>2} WR:{wr_v:>5.1f}% Pips:{p:>+7.1f}")

    # Cross-tab: setup x hour
    print(f"\n  === SETUP x HOUR ===")
    for setup in sorted(set(t['setup'] for t in all_results)):
        for h in sorted(set(t['time'].split(' ')[1].split(':')[0] for t in all_results)):
            group = [t for t in all_results if t['result'] in ('WIN', 'LOSS') and t['setup'] == setup and t['time'].split(' ')[1].split(':')[0] == h]
            if not group:
                continue
            w = sum(1 for t in group if t['result'] == 'WIN')
            l = sum(1 for t in group if t['result'] == 'LOSS')
            total = w + l
            wr_v = w / total * 100 if total else 0
            p = sum(t['pips'] for t in group)
            print(f"  {setup:<20} {h}:xx  W:{w:>2} L:{l:>2} WR:{wr_v:>5.1f}% Pips:{p:>+7.1f}")

    # RR bucket analysis
    print(f"\n  === BY RR RATIO ===")
    rr_buckets = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pips': 0})
    for t in all_results:
        if t['result'] in ('WIN', 'LOSS'):
            rr_cat = f"1:{t['rr']:.0f}" if t['rr'] >= 2.5 else f"1:{t['rr']:.1f}"
            rr_buckets[rr_cat]['wins' if t['result'] == 'WIN' else 'losses'] += 1
            rr_buckets[rr_cat]['pips'] += t['pips']
    for rr in sorted(rr_buckets.keys()):
        s = rr_buckets[rr]
        total_rr = s['wins'] + s['losses']
        wr_rr = s['wins'] / total_rr * 100 if total_rr else 0
        print(f"  RR {rr:<6}  W:{s['wins']:>2} L:{s['losses']:>2} WR:{wr_rr:>5.1f}% Pips:{s['pips']:>+7.1f}")

    # Trade list with diagnostics
    print(f"\n  === TRADE LOG ===")
    print(f"  {'#':<3} {'Time':<17} {'Symbol':<9} {'Dir':<6} {'Setup':<20} {'RR':>5} {'SL':>6} {'Conf':>4} {'Cfdn':>5} {'HTF':<8} {'ChCh':>4} {'Result':>7} {'Pips':>8}")
    print(f"  {'─'*110}")
    for t in all_results:
        icon = '✅' if t['result'] == 'WIN' else ('❌' if t['result'] == 'LOSS' else '⏳')
        choch = 'Y' if t.get('has_choch') else 'N'
        htf = str(t.get('htf_trend', '?'))[:7]
        conf_count = t.get('confirmation_count', '?')
        confidence = t.get('confidence', 0)
        print(f"  {t['num']:<3} {t['time']:<17} {t['symbol']:<9} {t['direction']:<6} "
              f"{t['setup']:<20} 1:{t['rr']:<4.1f} {t['sl_pips']:>5.1f}p "
              f"{conf_count:>4} {confidence:>5.2f} {htf:<8} {choch:>4} "
              f"{icon}{t['result']:>5} {t['pips']:>+7.1f}")

    print(f"\n{'='*70}")


if __name__ == "__main__":
    run_backtest()
