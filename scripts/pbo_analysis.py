#!/usr/bin/env python3
"""
Probability of Backtest Overfitting (PBO) Analysis
====================================================
Implements Combinatorially Symmetric Cross-Validation (CSCV) from
Marcos López de Prado's "The Probability of Backtest Overfitting" (2015).

Method:
  1. Download real price data and replay the strategy to generate trades
  2. Split the trade timeline into S equal sub-periods (partitions)
  3. For each of C(S, S/2) combinations, use half as in-sample (IS)
     and the other half as out-of-sample (OOS)
  4. Rank strategy performance IS, check if OOS rank degrades
  5. PBO = fraction of combinations where OOS Sharpe <= median

Interpretation:
  PBO < 30%  → Strategy likely captures real edge
  30-50%     → Borderline; more data or fewer parameters needed
  PBO > 50%  → Likely overfitting / noise

Usage:
    python scripts/pbo_analysis.py
"""

import sys
import os
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple
from collections import defaultdict
from itertools import combinations
from copy import deepcopy

import numpy as np
from scipy import stats

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger('pbo')


# ── DATA DOWNLOAD (reused from backtest_changes.py) ─────────────────

def download_mtf_data(yf_symbol: str, start: str, end: str) -> Dict[str, List[dict]]:
    """Download multi-timeframe candles from yfinance."""
    import yfinance as yf

    mtf = {}
    intervals = {'5M': '5m', '15M': '15m', '1H': '1h'}

    for tf, yf_interval in intervals.items():
        try:
            data = yf.download(
                yf_symbol, start=start, end=end,
                interval=yf_interval, progress=False,
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
            print(f"    {tf}: {len(candles)} candles")
        except Exception as e:
            print(f"    {tf}: FAILED ({e})")
            mtf[tf] = []

    # Build 4H from 1H
    if mtf.get('1H'):
        buf = []
        candles_4h = []
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
        print(f"    4H (from 1H): {len(candles_4h)} candles")

    return mtf


# ── TRADE SIMULATION ────────────────────────────────────────────────

def simulate_trade(signal: dict, candles_5m: List[dict], start_idx: int,
                   max_candles: int = 576) -> dict:
    """Walk 5M candles to see if TP or SL hit first."""
    entry = signal['entry_price']
    sl = signal['stop_loss']
    tp = signal['take_profit']
    direction = signal['direction']
    sl_dist = abs(entry - sl)
    tp_dist = abs(tp - entry)
    is_gold = sl_dist > 1

    end_idx = min(start_idx + max_candles, len(candles_5m))

    for i in range(start_idx, end_idx):
        c = candles_5m[i]
        if direction == 'long':
            if c['low'] <= sl:
                pips = -round(sl_dist * 10000, 1) if not is_gold else -round(sl_dist, 1)
                return {'result': 'LOSS', 'pips': pips,
                        'rr': round(tp_dist / sl_dist, 1) if sl_dist else 0,
                        'exit_time': c['time'], 'exit_idx': i, 'timestamp': c['timestamp']}
            if c['high'] >= tp:
                pips = round(tp_dist * 10000, 1) if not is_gold else round(tp_dist, 1)
                return {'result': 'WIN', 'pips': pips,
                        'rr': round(tp_dist / sl_dist, 1) if sl_dist else 0,
                        'exit_time': c['time'], 'exit_idx': i, 'timestamp': c['timestamp']}
        else:
            if c['high'] >= sl:
                pips = -round(sl_dist * 10000, 1) if not is_gold else -round(sl_dist, 1)
                return {'result': 'LOSS', 'pips': pips,
                        'rr': round(tp_dist / sl_dist, 1) if sl_dist else 0,
                        'exit_time': c['time'], 'exit_idx': i, 'timestamp': c['timestamp']}
            if c['low'] <= tp:
                pips = round(tp_dist * 10000, 1) if not is_gold else round(tp_dist, 1)
                return {'result': 'WIN', 'pips': pips,
                        'rr': round(tp_dist / sl_dist, 1) if sl_dist else 0,
                        'exit_time': c['time'], 'exit_idx': i, 'timestamp': c['timestamp']}

    return {'result': 'EXPIRED', 'pips': 0, 'rr': 0, 'exit_time': 'expired',
            'exit_idx': end_idx, 'timestamp': candles_5m[min(end_idx - 1, len(candles_5m) - 1)]['timestamp']}


# ── GENERATE ALL TRADES VIA STRATEGY REPLAY ─────────────────────────

def generate_trades(trade_start: datetime, trade_end: datetime) -> List[Dict]:
    """Replay strategy across the full data period and return all trades."""
    from core.flexible_ict_strategy import FlexibleICTStrategy

    yf_map = {
        'EUR_USD': 'EURUSD=X',
        'GBP_USD': 'GBPUSD=X',
        'XAU_USD': 'GC=F',
    }
    symbols = ['EUR_USD', 'GBP_USD', 'XAU_USD']

    lookback_start = (trade_start - timedelta(days=7)).strftime('%Y-%m-%d')
    end_date = trade_end.strftime('%Y-%m-%d')

    print("📥 Downloading price data...")
    all_mtf = {}
    for symbol in symbols:
        print(f"  {symbol} ({yf_map[symbol]}):")
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
    strategy._daily_loss_date = None

    all_trades = []
    window = 150

    day_start_ts = int(trade_start.timestamp())
    day_end_ts = int(trade_end.timestamp())

    # Build chronological events
    timed_events = []
    for symbol in symbols:
        candles_5m = all_mtf[symbol].get('5M', [])
        for idx, c in enumerate(candles_5m):
            if day_start_ts <= c['timestamp'] < day_end_ts:
                timed_events.append((c['timestamp'], symbol, idx))
    timed_events.sort(key=lambda x: x[0])

    print(f"\n⏳ Replaying {len(timed_events)} price events...")

    for ts, symbol, idx in timed_events:
        candles_5m = all_mtf[symbol].get('5M', [])

        # Skip weekends
        dow = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%A')
        if dow in ('Saturday', 'Sunday'):
            continue

        if idx < window:
            continue

        slice_5m = candles_5m[max(0, idx - window):idx + 1]
        slice_1h = [c for c in all_mtf[symbol].get('1H', []) if c['timestamp'] <= ts][-100:]
        slice_4h = [c for c in all_mtf[symbol].get('4H', []) if c['timestamp'] <= ts][-50:]
        slice_15m = [c for c in all_mtf[symbol].get('15M', []) if c['timestamp'] <= ts][-100:]

        local_mtf = {'5M': slice_5m, '1H': slice_1h, '4H': slice_4h, '15M': slice_15m}

        cap_ok = strategy.can_take_trade(ts, symbol)
        cooldown_ok = strategy.check_signal_cooldown(symbol, ts)
        if not cap_ok or not cooldown_ok:
            continue
        if strategy.check_circuit_breaker(ts):
            continue

        strategy._last_rejection_reasons = []
        signal = strategy.analyze(slice_5m, symbol=symbol, mtf_data=local_mtf, backtest_mode=True)

        if signal:
            result = simulate_trade(signal, candles_5m, idx + 1)

            if result['result'] == 'LOSS':
                strategy.record_loss(symbol, signal['entry_price'], signal['direction'], ts)
            elif result['result'] == 'WIN':
                strategy.record_win(symbol)

            if result['result'] != 'EXPIRED':
                trade = {
                    'timestamp': ts,
                    'symbol': symbol,
                    'direction': signal['direction'],
                    'setup': signal['setup_type'],
                    'entry': signal['entry_price'],
                    'sl': signal['stop_loss'],
                    'tp': signal['take_profit'],
                    'rr': signal['risk_reward'],
                    'result': result['result'],
                    'pips': result['pips'],
                    'exit_time': result.get('exit_time'),
                    'exit_timestamp': result.get('timestamp', ts),
                }
                all_trades.append(trade)

    all_trades.sort(key=lambda t: t['timestamp'])
    return all_trades


# ── PBO CORE: CSCV IMPLEMENTATION ───────────────────────────────────

def compute_sharpe(returns: np.ndarray) -> float:
    """Annualized Sharpe ratio from a trade return series."""
    if len(returns) < 2 or np.std(returns) == 0:
        return 0.0
    # Assume ~5 trades/day, 252 trading days
    daily_factor = np.sqrt(252 * 5) if len(returns) > 5 else 1.0
    return float(np.mean(returns) / np.std(returns) * daily_factor)


def compute_profit_factor(returns: np.ndarray) -> float:
    """Profit factor = gross wins / abs(gross losses)."""
    wins = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())
    if losses == 0:
        return 10.0 if wins > 0 else 1.0
    return float(wins / losses)


def trades_to_returns(trades: List[Dict], risk_per_trade: float = 1.0) -> np.ndarray:
    """Convert trade list to R-multiple return series.
    
    Each trade's return is expressed as a multiple of risk:
    WIN  = +RR ratio (e.g., 1:2 trade = +2R)
    LOSS = -1R
    """
    returns = []
    for t in trades:
        if t['result'] == 'WIN':
            returns.append(t['rr'] * risk_per_trade)
        elif t['result'] == 'LOSS':
            returns.append(-risk_per_trade)
    return np.array(returns, dtype=float)


def run_cscv_pbo(trades: List[Dict], S: int = 10,
                 metric: str = 'sharpe') -> Dict:
    """
    Combinatorially Symmetric Cross-Validation for PBO.
    
    Args:
        trades: Chronological list of trade dicts with 'result', 'rr', 'timestamp'
        S: Number of sub-periods to partition trades into (must be even)
        metric: 'sharpe' or 'profit_factor'
    
    Returns:
        Dict with PBO score, logit distribution, and diagnostics
    """
    if S % 2 != 0:
        S += 1

    n_trades = len(trades)
    if n_trades < S * 2:
        return {
            'pbo': None,
            'error': f'Not enough trades ({n_trades}) for {S} partitions (need >= {S * 2})',
            'n_trades': n_trades,
        }

    # Step 1: Partition trades into S consecutive sub-periods
    partition_size = n_trades // S
    partitions = []
    for i in range(S):
        start = i * partition_size
        end = start + partition_size if i < S - 1 else n_trades
        partition_returns = trades_to_returns(trades[start:end])
        partitions.append(partition_returns)

    # Step 2: Compute performance metric for each partition
    if metric == 'sharpe':
        metric_fn = compute_sharpe
    else:
        metric_fn = compute_profit_factor

    partition_metrics = np.array([metric_fn(p) for p in partitions])

    # Step 3: Enumerate all C(S, S/2) combinations
    half = S // 2
    all_combos = list(combinations(range(S), half))
    n_combos = len(all_combos)

    print(f"  Partitions: {S} ({partition_size} trades each)")
    print(f"  Combinations: C({S},{half}) = {n_combos}")

    # Step 4: For each combination, compute IS and OOS performance
    logit_values = []
    oos_degraded_count = 0

    for combo_idx, is_indices in enumerate(all_combos):
        oos_indices = tuple(i for i in range(S) if i not in is_indices)

        # Combine sub-period returns
        is_returns = np.concatenate([partitions[i] for i in is_indices])
        oos_returns = np.concatenate([partitions[i] for i in oos_indices])

        is_metric = metric_fn(is_returns)
        oos_metric = metric_fn(oos_returns)

        # Rank-based: does the OOS metric rank below median?
        # Using relative performance: if IS is good but OOS is bad → overfit
        if is_metric > 0 and oos_metric <= 0:
            oos_degraded_count += 1
            # Logit: log(p / (1-p)) where p = rank(oos) / N
            # When OOS underperforms, logit is negative
            logit_values.append(-abs(is_metric - oos_metric))
        elif is_metric > 0 and oos_metric > 0:
            # Both positive — calculate relative degradation
            ratio = oos_metric / is_metric if is_metric != 0 else 1.0
            if ratio < 0.5:
                # OOS less than half of IS performance → significant degradation
                oos_degraded_count += 1
            logit_values.append(np.log(max(ratio, 0.001)))
        elif is_metric <= 0:
            # IS already negative — not a viable "strategy variant" to test
            logit_values.append(0)
        else:
            logit_values.append(0)

    # Step 5: PBO = proportion of combinations where OOS underperforms
    logit_array = np.array(logit_values)
    pbo = oos_degraded_count / n_combos if n_combos > 0 else 0

    # Also compute: what fraction of combos have OOS Sharpe <= 0?
    oos_negative_count = 0
    is_sharpes = []
    oos_sharpes = []
    for is_indices in all_combos:
        oos_indices = tuple(i for i in range(S) if i not in is_indices)
        is_returns = np.concatenate([partitions[i] for i in is_indices])
        oos_returns = np.concatenate([partitions[i] for i in oos_indices])
        is_s = metric_fn(is_returns)
        oos_s = metric_fn(oos_returns)
        is_sharpes.append(is_s)
        oos_sharpes.append(oos_s)
        if oos_s <= 0:
            oos_negative_count += 1

    pbo_strict = oos_negative_count / n_combos if n_combos > 0 else 0

    return {
        'pbo': pbo,
        'pbo_strict': pbo_strict,
        'n_trades': n_trades,
        'n_partitions': S,
        'partition_size': partition_size,
        'n_combinations': n_combos,
        'oos_degraded': oos_degraded_count,
        'oos_negative': oos_negative_count,
        'logit_mean': float(np.mean(logit_array)),
        'logit_std': float(np.std(logit_array)),
        'is_sharpe_mean': float(np.mean(is_sharpes)),
        'oos_sharpe_mean': float(np.mean(oos_sharpes)),
        'partition_metrics': partition_metrics.tolist(),
        'metric': metric,
    }


# ── STATIONARITY TEST (supplementary) ──────────────────────────────

def test_return_stationarity(trades: List[Dict]) -> Dict:
    """Test if trade returns are stationary (non-decaying) across time."""
    returns = trades_to_returns(trades)
    n = len(returns)
    if n < 10:
        return {'stationary': None, 'error': 'Not enough trades'}

    # Split into first half / second half
    mid = n // 2
    first_half = returns[:mid]
    second_half = returns[mid:]

    # Two-sample t-test
    t_stat, p_value = stats.ttest_ind(first_half, second_half)

    # Compare means
    mean_first = float(np.mean(first_half))
    mean_second = float(np.mean(second_half))

    # Rolling Sharpe (5-trade windows)
    window = max(5, n // 10)
    rolling_sharpes = []
    for i in range(0, n - window + 1, window):
        chunk = returns[i:i + window]
        if len(chunk) >= 2 and np.std(chunk) > 0:
            rolling_sharpes.append(float(np.mean(chunk) / np.std(chunk)))

    # Trend in rolling Sharpe (linear regression)
    if len(rolling_sharpes) >= 3:
        x = np.arange(len(rolling_sharpes))
        slope, intercept, r_value, p_slope, std_err = stats.linregress(x, rolling_sharpes)
    else:
        slope, r_value, p_slope = 0, 0, 1

    return {
        'mean_first_half': mean_first,
        'mean_second_half': mean_second,
        'ttest_p_value': float(p_value),
        'means_different': p_value < 0.05,
        'sharpe_trend_slope': float(slope),
        'sharpe_trend_r2': float(r_value ** 2),
        'sharpe_trend_p': float(p_slope),
        'rolling_sharpes': rolling_sharpes,
        'n_windows': len(rolling_sharpes),
    }


# ── PER-SETUP PBO ──────────────────────────────────────────────────

def run_per_setup_pbo(trades: List[Dict], S: int = 6) -> Dict[str, Dict]:
    """Run PBO separately for each setup type."""
    setup_groups = defaultdict(list)
    for t in trades:
        setup_groups[t['setup']].append(t)

    results = {}
    for setup, setup_trades in sorted(setup_groups.items()):
        n = len(setup_trades)
        min_needed = S * 2
        if n < min_needed:
            results[setup] = {
                'pbo': None,
                'n_trades': n,
                'error': f'Only {n} trades (need {min_needed}+)',
            }
        else:
            # Use fewer partitions for smaller sample
            actual_s = min(S, n // 3)
            if actual_s % 2 != 0:
                actual_s = max(actual_s - 1, 4)
            if actual_s < 4:
                results[setup] = {
                    'pbo': None,
                    'n_trades': n,
                    'error': f'Only {n} trades — too few for meaningful PBO',
                }
            else:
                results[setup] = run_cscv_pbo(setup_trades, S=actual_s)
    return results


# ── MAIN ────────────────────────────────────────────────────────────

def load_actual_trade_history() -> List[Dict]:
    """Load real resolved trades from active_signals.json + trade_history.json.
    
    These are ACTUAL trades — the best data for PBO since they include
    the full strategy lifecycle (signal → fill → outcome).
    """
    trades = []

    # Source 1: active_signals.json (has win/loss with full details)
    signals_file = os.path.join(project_root, 'data', 'active_signals.json')
    if os.path.exists(signals_file):
        with open(signals_file) as f:
            signals = json.load(f)
        for sid, sig in signals.items():
            if sig.get('status') not in ('win', 'loss'):
                continue
            detected = sig.get('detected_at', '')
            try:
                if isinstance(detected, str) and detected:
                    dt = datetime.fromisoformat(detected.replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    ts = int(dt.timestamp())
                else:
                    continue
            except Exception:
                continue

            entry = sig.get('entry_price', 0)
            sl = sig.get('stop_loss', 0)
            tp = sig.get('take_profit', 0)
            if not all([entry, sl, tp]):
                continue

            sl_dist = abs(entry - sl)
            tp_dist = abs(tp - entry)
            rr = tp_dist / sl_dist if sl_dist > 0 else 0

            trades.append({
                'timestamp': ts,
                'symbol': sig.get('symbol', ''),
                'direction': sig.get('direction', ''),
                'setup': sig.get('setup_type', 'UNKNOWN'),
                'entry': entry,
                'sl': sl,
                'tp': tp,
                'rr': round(rr, 1),
                'result': sig['status'].upper(),
                'pips': sig.get('pips_result', 0),
                'exit_time': sig.get('exit_time', ''),
                'exit_timestamp': ts,
                'source': 'active_signals',
            })

    # Source 2: trade_history.json (resolved by TradeTracker)
    history_file = os.path.join(project_root, 'data', 'trade_history.json')
    if os.path.exists(history_file):
        with open(history_file) as f:
            history = json.load(f)
        seen_signals = {t.get('symbol', '') + str(t.get('timestamp', '')) for t in trades}
        for t in history:
            if t.get('status') not in ('win', 'loss'):
                continue
            entry_time = t.get('entry_time', '')
            try:
                dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                ts = int(dt.timestamp())
            except Exception:
                continue

            key = t.get('symbol', '') + str(ts)
            if key in seen_signals:
                continue  # Avoid duplicates

            entry = t.get('entry_price', 0)
            sl = t.get('stop_loss', 0)
            tp = t.get('take_profit', 0)
            if not all([entry, sl, tp]):
                continue

            sl_dist = abs(entry - sl)
            tp_dist = abs(tp - entry)
            rr = tp_dist / sl_dist if sl_dist > 0 else 0

            trades.append({
                'timestamp': ts,
                'symbol': t.get('symbol', ''),
                'direction': t.get('direction', ''),
                'setup': t.get('setup_type', 'UNKNOWN'),
                'entry': entry,
                'sl': sl,
                'tp': tp,
                'rr': round(rr, 1),
                'result': t['status'].upper(),
                'pips': t.get('pips_result', 0),
                'exit_time': t.get('exit_time', ''),
                'exit_timestamp': ts,
                'source': 'trade_history',
            })

    trades.sort(key=lambda t: t['timestamp'])
    return trades


def main():
    print("=" * 72)
    print("  PROBABILITY OF BACKTEST OVERFITTING (PBO) ANALYSIS")
    print("  Method: Combinatorially Symmetric Cross-Validation (CSCV)")
    print("  Reference: López de Prado (2015)")
    print("=" * 72)

    # ── Step 1: Load actual trade history ──
    # Use REAL trades first — this is the gold standard for PBO.
    # Strategy replay is a secondary option if we don't have enough real trades.
    print(f"\n{'━' * 72}")
    print("  STEP 1: LOADING TRADE DATA")
    print("━" * 72)

    trades = load_actual_trade_history()
    source_label = "ACTUAL TRADES (active_signals + trade_history)"

    if len(trades) < 20:
        print(f"  Only {len(trades)} actual trades found — supplementing with strategy replay...")
        # Fall back to replay with safe 5M date range (last 55 days)
        trade_end = datetime(2026, 3, 12, tzinfo=timezone.utc)
        trade_start = trade_end - timedelta(days=50)
        replay_trades = generate_trades(trade_start, trade_end)
        if len(replay_trades) > len(trades):
            trades = replay_trades
            source_label = f"STRATEGY REPLAY ({trade_start.strftime('%b %d')} – {trade_end.strftime('%b %d')})"
        else:
            source_label = "ACTUAL TRADES (limited data)"

    if trades:
        first_dt = datetime.fromtimestamp(trades[0]['timestamp'], tz=timezone.utc)
        last_dt = datetime.fromtimestamp(trades[-1]['timestamp'], tz=timezone.utc)
        period_days = (last_dt - first_dt).days
    else:
        period_days = 0

    print(f"\n  Source: {source_label}")

    wins = [t for t in trades if t['result'] == 'WIN']
    losses = [t for t in trades if t['result'] == 'LOSS']
    total_pips = sum(t.get('pips', 0) for t in trades)
    wr = len(wins) / len(trades) * 100 if trades else 0

    if trades:
        print(f"  Period: {first_dt.strftime('%b %d')} to {last_dt.strftime('%b %d, %Y')} ({period_days} days)")
    print(f"  Trades: {len(trades)}")
    print(f"  Wins: {len(wins)} | Losses: {len(losses)} | WR: {wr:.1f}%")
    print(f"  Total pips: {total_pips:+.1f}")

    if len(trades) < 20:
        print(f"\n  ⚠️  Only {len(trades)} trades — PBO needs 20+ for reliability.")
        print("  Consider extending the data period or using 1H candles for more history.")
        if len(trades) < 8:
            print("  ❌ Too few trades to run PBO. Exiting.")
            return

    # ── Step 2: Overall PBO ──
    print(f"\n{'━' * 72}")
    print("  STEP 2: OVERALL PBO (Combinatorially Symmetric Cross-Validation)")
    print("━" * 72)

    # Choose S based on trade count
    n = len(trades)
    if n >= 60:
        S = 10
    elif n >= 30:
        S = 8
    elif n >= 16:
        S = 6
    else:
        S = 4

    pbo_result = run_cscv_pbo(trades, S=S, metric='sharpe')

    if pbo_result.get('error'):
        print(f"\n  ⚠️  {pbo_result['error']}")
    else:
        pbo = pbo_result['pbo']
        pbo_strict = pbo_result['pbo_strict']

        # Interpretation
        if pbo < 0.30:
            verdict = "✅ LIKELY REAL EDGE"
            color = "green"
        elif pbo < 0.50:
            verdict = "⚠️  BORDERLINE — needs more data or simpler model"
            color = "yellow"
        else:
            verdict = "❌ PROBABLY NOISE / OVERFITTING"
            color = "red"

        print(f"\n  ┌─────────────────────────────────────────────┐")
        print(f"  │  PBO (degradation) = {pbo:.1%}                   │")
        print(f"  │  PBO (strict: OOS≤0) = {pbo_strict:.1%}               │")
        print(f"  │  Verdict: {verdict:<33} │")
        print(f"  └─────────────────────────────────────────────┘")

        print(f"\n  Diagnostics:")
        print(f"    Partitions:        {pbo_result['n_partitions']} × {pbo_result['partition_size']} trades")
        print(f"    Combinations:      {pbo_result['n_combinations']}")
        print(f"    OOS degraded:      {pbo_result['oos_degraded']}/{pbo_result['n_combinations']}")
        print(f"    OOS negative:      {pbo_result['oos_negative']}/{pbo_result['n_combinations']}")
        print(f"    Avg IS Sharpe:     {pbo_result['is_sharpe_mean']:.2f}")
        print(f"    Avg OOS Sharpe:    {pbo_result['oos_sharpe_mean']:.2f}")
        print(f"    Logit mean:        {pbo_result['logit_mean']:.3f}")

        print(f"\n  Per-partition {pbo_result['metric']}:")
        metrics = pbo_result['partition_metrics']
        for i, m in enumerate(metrics):
            bar = '█' * max(1, int(abs(m) * 2))
            sign = '+' if m >= 0 else ''
            print(f"    Partition {i+1:>2}: {sign}{m:>7.2f}  {bar}")

    # ── Step 3: Stationarity ──
    print(f"\n{'━' * 72}")
    print("  STEP 3: RETURN STATIONARITY TEST")
    print("━" * 72)

    stat_result = test_return_stationarity(trades)

    if stat_result.get('error'):
        print(f"\n  ⚠️  {stat_result['error']}")
    else:
        print(f"\n  First half mean:     {stat_result['mean_first_half']:+.3f}R")
        print(f"  Second half mean:    {stat_result['mean_second_half']:+.3f}R")
        print(f"  T-test p-value:      {stat_result['ttest_p_value']:.3f}")
        if stat_result['means_different']:
            print(f"  ⚠️  Means significantly different (p<0.05) — performance may be decaying")
        else:
            print(f"  ✅ No significant difference — returns are stable across time")

        print(f"\n  Rolling Sharpe trend:")
        print(f"    Slope:   {stat_result['sharpe_trend_slope']:+.4f}")
        print(f"    R²:      {stat_result['sharpe_trend_r2']:.3f}")
        print(f"    p-value: {stat_result['sharpe_trend_p']:.3f}")

        if stat_result['rolling_sharpes']:
            for i, s in enumerate(stat_result['rolling_sharpes']):
                bar = '█' * max(1, int(abs(s) * 3))
                sign = '+' if s >= 0 else ''
                print(f"    Window {i+1:>2}: {sign}{s:>6.2f}  {'🟢' if s > 0 else '🔴'} {bar}")

        if stat_result['sharpe_trend_slope'] < -0.1 and stat_result['sharpe_trend_p'] < 0.1:
            print(f"\n  ⚠️  Sharpe is declining — possible overfitting or regime change")
        else:
            print(f"\n  ✅ No significant Sharpe decline")

    # ── Step 4: Per-Setup PBO ──
    print(f"\n{'━' * 72}")
    print("  STEP 4: PER-SETUP PBO BREAKDOWN")
    print("━" * 72)

    setup_results = run_per_setup_pbo(trades, S=6)

    print(f"\n  {'Setup':<25} {'Trades':>6} {'PBO':>8} {'PBO(strict)':>12} {'Verdict':<20}")
    print(f"  {'─' * 75}")

    for setup, res in sorted(setup_results.items()):
        n = res.get('n_trades', 0)
        if res.get('error'):
            print(f"  {setup:<25} {n:>6} {'—':>8} {'—':>12} {res['error']}")
        else:
            pbo = res['pbo']
            pbo_s = res['pbo_strict']
            if pbo < 0.30:
                v = "✅ Real"
            elif pbo < 0.50:
                v = "⚠️  Borderline"
            else:
                v = "❌ Noise"
            print(f"  {setup:<25} {n:>6} {pbo:>7.1%} {pbo_s:>11.1%} {v}")

    # ── Step 5: Summary ──
    print(f"\n{'━' * 72}")
    print("  SUMMARY & INTERPRETATION")
    print("━" * 72)

    print(f"""
  PBO measures the probability that your backtest results are due to
  overfitting rather than genuine alpha. It works by:

  1. Splitting trade history into {S} sub-periods
  2. Testing all {pbo_result.get('n_combinations', '?')} ways to split IS/OOS
  3. Checking if in-sample performance persists out-of-sample

  Your strategy has {len(trades)} trades across {period_days} days.
""")

    if pbo_result.get('pbo') is not None:
        pbo = pbo_result['pbo']
        if pbo < 0.30:
            print("  🟢 PBO < 30%: Your strategy parameters likely capture REAL market edge.")
            print("     The performance you see in backtests is consistent across time periods.")
        elif pbo < 0.50:
            print("  🟡 PBO 30-50%: Your strategy is BORDERLINE.")
            print("     Some of the performance may be noise. Consider:")
            print("       • Reducing the number of tunable parameters")
            print("       • Extending the test period when more data accumulates")
            print("       • Merging similar setups to reduce degrees of freedom")
        else:
            print("  🔴 PBO > 50%: Your strategy is likely OVERFITTED.")
            print("     The backtest performance does not hold out-of-sample.")
            print("     Consider:")
            print("       • Simplifying to fewer setup types")
            print("       • Using wider stop losses and TP targets")
            print("       • Removing recently-added filters that may be curve-fitted")

    # Note on limitations
    print(f"""
  ⚠️  CAVEATS:
  • PBO is most reliable with 50+ trades. You have {len(trades)}.
  • yfinance 5M data is limited to ~60 days. More history → better PBO.
  • This tests the FIXED strategy. If you re-optimized parameters after
    seeing these results, the new PBO would need to be recalculated.
  • PBO assumes strategy parameters are stable. If you change rules
    frequently (which you do — hardening Opt4, adding circuit breaker,
    etc.), each rule change creates a new "strategy" to test.
""")

    print("=" * 72)


if __name__ == '__main__':
    main()
