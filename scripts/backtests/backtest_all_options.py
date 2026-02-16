#!/usr/bin/env python3
"""
HEAD-TO-HEAD Backtest: Option 1 vs Option 4 vs Option 5 per pair.

Each option is tested independently (no priority ordering).
Each gets its own walk-forward so we can compare apples to apples.

Usage:
    python3 scripts/backtests/backtest_all_options.py
    python3 scripts/backtests/backtest_all_options.py --days 45
"""

import sys, os, argparse
from datetime import datetime, timedelta, timezone
from collections import defaultdict

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

import yfinance as yf
from core.flexible_ict_strategy import FlexibleICTStrategy, SetupType

# ── Config ────────────────────────────────────────────────────────────────────

TICKER_MAP = {
    'EUR_USD': '6E=F',
    'GBP_USD': '6B=F',
}
DISPLAY_MAP = {
    'EUR_USD': 'EUR/USD',
    'GBP_USD': 'GBP/USD',
}
TF_INTERVALS = {'5M': '5m', '15M': '15m', '1H': '1h'}

OPTION_NAMES = {
    1: 'HTF_LIQUIDITY_BOS',
    4: 'LIQ_SWEEP_ENGULF',
    5: 'ICT_SWEEP_CONFIRM',
}


# ── Data Download (reuse from backtest_option5) ──────────────────────────────

def download_mtf_data(symbol: str, days: int = 30) -> dict:
    ticker = TICKER_MAP[symbol]
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=min(days, 59))

    print(f"  📊 {DISPLAY_MAP[symbol]} ({ticker}): {start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')}")

    data = {}
    for tf_name, interval in TF_INTERVALS.items():
        try:
            df = yf.download(ticker, start=start.strftime('%Y-%m-%d'),
                             end=(end + timedelta(days=1)).strftime('%Y-%m-%d'),
                             interval=interval, progress=False)
            if df is None or df.empty:
                print(f"    ❌ {tf_name}: no data")
                return {}
            candles = []
            for ts, row in df.iterrows():
                try:
                    o = float(row['Open'].iloc[0]) if hasattr(row['Open'], 'iloc') else float(row['Open'])
                    h = float(row['High'].iloc[0]) if hasattr(row['High'], 'iloc') else float(row['High'])
                    l = float(row['Low'].iloc[0]) if hasattr(row['Low'], 'iloc') else float(row['Low'])
                    c = float(row['Close'].iloc[0]) if hasattr(row['Close'], 'iloc') else float(row['Close'])
                    v = float(row['Volume'].iloc[0]) if hasattr(row['Volume'], 'iloc') else float(row.get('Volume', 0))
                except (KeyError, IndexError):
                    continue
                candles.append({'timestamp': int(ts.timestamp()), 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v})
            data[tf_name] = candles
            print(f"    ✅ {tf_name}: {len(candles)} candles")
        except Exception as e:
            print(f"    ❌ {tf_name}: {e}")
            return {}

    # Synthesise 4H from 1H
    if '1H' in data and data['1H']:
        candles_1h = data['1H']
        candles_4h = []
        for i in range(0, len(candles_1h) - 3, 4):
            chunk = candles_1h[i:i+4]
            candles_4h.append({
                'timestamp': chunk[0]['timestamp'],
                'open': chunk[0]['open'],
                'high': max(c['high'] for c in chunk),
                'low': min(c['low'] for c in chunk),
                'close': chunk[-1]['close'],
                'volume': sum(c.get('volume', 0) for c in chunk),
            })
        data['4H'] = candles_4h
        print(f"    ✅ 4H: {len(candles_4h)} candles (synthesised)")

    return data


def simulate_outcome(signal: dict, future_candles: list, symbol: str) -> dict:
    direction = signal['direction']
    entry = signal['entry_price']
    sl = signal['stop_loss']
    tp = signal['take_profit']
    pip_value = 0.10 if 'XAU' in symbol else 0.0001

    for c in future_candles:
        if direction == 'long':
            tp_hit = c['high'] >= tp
            sl_hit = c['low'] <= sl
        else:
            tp_hit = c['low'] <= tp
            sl_hit = c['high'] >= sl

        if tp_hit and sl_hit:
            pips = -abs(entry - sl) / pip_value
            return {'outcome': 'SL', 'pips': round(pips, 1)}
        if sl_hit:
            pips = -abs(entry - sl) / pip_value
            return {'outcome': 'SL', 'pips': round(pips, 1)}
        if tp_hit:
            pips = abs(tp - entry) / pip_value
            return {'outcome': 'TP', 'pips': round(pips, 1)}

    return {'outcome': 'EXPIRED', 'pips': 0}


# ── Walk-Forward for a Single Option ─────────────────────────────────────────

def walk_option(option_num: int, symbol: str, all_data: dict, strategy: FlexibleICTStrategy):
    """Run walk-forward for a single option on a single pair. Returns list of trades."""
    candles_5m = all_data[symbol]['5M']
    candles_15m = all_data[symbol].get('15M', [])
    candles_1h = all_data[symbol].get('1H', [])
    candles_4h = all_data[symbol].get('4H', [])

    WINDOW_5M = 100
    STEP = 6
    COOLDOWN_CANDLES = 48
    FUTURE_CANDLES = 576

    trades = []
    last_signal_idx = -COOLDOWN_CANDLES

    # Pick the right method
    if option_num == 1:
        call_fn = lambda candles, sym: strategy.try_option_1(candles, sym)
    elif option_num == 4:
        call_fn = lambda candles, sym: strategy.try_option_4(candles, sym)
    elif option_num == 5:
        call_fn = lambda candles, sym: strategy.try_option_5(candles, sym)
    else:
        return []

    for i in range(WINDOW_5M, len(candles_5m) - FUTURE_CANDLES, STEP):
        if i - last_signal_idx < COOLDOWN_CANDLES:
            continue

        ts_now = candles_5m[i]['timestamp']
        snapshot_5m = candles_5m[i - WINDOW_5M:i + 1]
        snapshot_15m = [c for c in candles_15m if c['timestamp'] <= ts_now][-60:]
        snapshot_1h = [c for c in candles_1h if c['timestamp'] <= ts_now][-60:]
        snapshot_4h = [c for c in candles_4h if c['timestamp'] <= ts_now][-30:]

        if len(snapshot_1h) < 24 or len(snapshot_4h) < 10:
            continue

        mtf_data = {'5M': snapshot_5m, '15M': snapshot_15m, '1H': snapshot_1h, '4H': snapshot_4h}

        # Reset strategy state
        strategy._last_signal_time = {}
        strategy.trades_today = {}
        strategy._last_rejection_reasons = []
        strategy._last_sweep_found = False
        strategy._last_bos_found = False
        strategy.current_symbol = symbol
        strategy.set_mtf_data(mtf_data)

        # SMT data for Option 5
        if option_num == 5:
            all_market = {}
            for sym, mtf in all_data.items():
                c5 = mtf['5M'][:i+1] if sym == symbol else mtf['5M']
                c1 = mtf.get('1H', [])
                if len(c5) >= 20 and len(c1) >= 20:
                    all_market[sym] = {'5M': c5[-100:], '1H': c1[-48:]}
            strategy.set_all_market_data(all_market)

        setup_data = call_fn(snapshot_5m, symbol)
        if not setup_data:
            continue

        entry_price = snapshot_5m[-1]['close']
        stop_loss, take_profit, rr_ratio = strategy.calculate_sl_tp(
            entry_price, setup_data, snapshot_5m, symbol
        )
        if stop_loss is None:
            continue

        signal = {
            'timestamp': ts_now,
            'symbol': symbol,
            'option': option_num,
            'setup_type': setup_data['setup_type'].value,
            'direction': setup_data['direction'],
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'risk_reward': rr_ratio,
            'confirmations': setup_data.get('confirmations', []),
        }

        future = candles_5m[i + 1: i + 1 + FUTURE_CANDLES]
        outcome = simulate_outcome(signal, future, symbol)
        trade = {**signal, **outcome}
        trades.append(trade)
        last_signal_idx = i

    return trades


# ── Main ──────────────────────────────────────────────────────────────────────

def run_head_to_head(days: int = 30):
    pairs = ['EUR_USD', 'GBP_USD']
    options = [1, 4, 5]

    print("\n" + "=" * 80)
    print("  HEAD-TO-HEAD BACKTEST — Option 1 vs Option 4 vs Option 5")
    print("=" * 80)
    print(f"  Pairs:   {', '.join(DISPLAY_MAP[p] for p in pairs)}")
    print(f"  Period:  last {days} days")
    print(f"  Options: {', '.join(f'Opt {o} ({OPTION_NAMES[o]})' for o in options)}")
    print()

    # Download data
    print("📥 Downloading data...\n")
    all_data = {}
    for symbol in pairs:
        mtf = download_mtf_data(symbol, days)
        if mtf and '5M' in mtf:
            all_data[symbol] = mtf
        print()

    if not all_data:
        print("❌ No data. Exiting.")
        return

    strategy = FlexibleICTStrategy()

    # Run each option independently for each pair
    results = {}  # {(pair, option): [trades]}

    for symbol in pairs:
        if symbol not in all_data:
            continue
        for opt in options:
            key = (symbol, opt)
            print(f"  🏃 {DISPLAY_MAP[symbol]} × Option {opt} ({OPTION_NAMES[opt]})...", end=" ", flush=True)

            # Reset sweep dedup between runs
            strategy._last_sweep_signal = {}
            strategy._session_levels = {}

            trades = walk_option(opt, symbol, all_data, strategy)
            results[key] = trades

            wins = [t for t in trades if t['outcome'] == 'TP']
            losses = [t for t in trades if t['outcome'] == 'SL']
            wr = len(wins) / (len(wins) + len(losses)) * 100 if (wins or losses) else 0
            pips = sum(t['pips'] for t in trades)
            print(f"{len(trades)} signals, {len(wins)}W/{len(losses)}L, {wr:.0f}% WR, {pips:+.0f} pips")

    # ── Print Results Matrix ──
    print("\n" + "=" * 80)
    print("  📊 RESULTS MATRIX — Per Option Per Pair")
    print("=" * 80)

    header = f"  {'':20s} | {'Signals':>8} | {'Wins':>5} | {'Losses':>6} | {'WR%':>6} | {'Pips':>8} | {'Avg W':>7} | {'Avg L':>7} | {'PF':>6} | {'RR':>5}"
    print(header)
    print("  " + "─" * (len(header) - 2))

    # Per pair per option
    for symbol in pairs:
        for opt in options:
            trades = results.get((symbol, opt), [])
            if not trades:
                label = f"{DISPLAY_MAP[symbol]} Opt{opt}"
                print(f"  {label:20s} | {'—':>8} | {'—':>5} | {'—':>6} | {'—':>6} | {'—':>8} | {'—':>7} | {'—':>7} | {'—':>6} | {'—':>5}")
                continue
            wins = [t for t in trades if t['outcome'] == 'TP']
            losses = [t for t in trades if t['outcome'] == 'SL']
            wr = len(wins) / (len(wins) + len(losses)) * 100 if (wins or losses) else 0
            pips = sum(t['pips'] for t in trades)
            avg_w = sum(t['pips'] for t in wins) / len(wins) if wins else 0
            avg_l = sum(t['pips'] for t in losses) / len(losses) if losses else 0
            pf = abs(sum(t['pips'] for t in wins) / sum(t['pips'] for t in losses)) if losses and sum(t['pips'] for t in losses) != 0 else float('inf')
            avg_rr = (avg_w / abs(avg_l)) if avg_l != 0 else 0
            label = f"{DISPLAY_MAP[symbol]} Opt{opt}"
            print(f"  {label:20s} | {len(trades):>8} | {len(wins):>5} | {len(losses):>6} | {wr:>5.1f}% | {pips:>+7.0f}p | {avg_w:>+6.1f}p | {avg_l:>+6.1f}p | {pf:>6.2f} | {avg_rr:>5.2f}")
        print("  " + "─" * (len(header) - 2))

    # Per option totals
    print(f"\n  📋 TOTALS BY OPTION (both pairs combined):")
    print(f"  {'Option':20s} | {'Signals':>8} | {'WR%':>6} | {'Pips':>8} | {'PF':>6}")
    print("  " + "─" * 55)
    for opt in options:
        all_trades = []
        for symbol in pairs:
            all_trades.extend(results.get((symbol, opt), []))
        if not all_trades:
            continue
        wins = [t for t in all_trades if t['outcome'] == 'TP']
        losses = [t for t in all_trades if t['outcome'] == 'SL']
        wr = len(wins) / (len(wins) + len(losses)) * 100 if (wins or losses) else 0
        pips = sum(t['pips'] for t in all_trades)
        pf = abs(sum(t['pips'] for t in wins) / sum(t['pips'] for t in losses)) if losses and sum(t['pips'] for t in losses) != 0 else float('inf')
        label = f"Opt {opt} ({OPTION_NAMES[opt][:18]})"
        print(f"  {label:20s} | {len(all_trades):>8} | {wr:>5.1f}% | {pips:>+7.0f}p | {pf:>6.2f}")

    # Per pair totals
    print(f"\n  📋 TOTALS BY PAIR (all options combined):")
    print(f"  {'Pair':20s} | {'Signals':>8} | {'WR%':>6} | {'Pips':>8} | {'PF':>6}")
    print("  " + "─" * 55)
    for symbol in pairs:
        all_trades = []
        for opt in options:
            all_trades.extend(results.get((symbol, opt), []))
        if not all_trades:
            continue
        wins = [t for t in all_trades if t['outcome'] == 'TP']
        losses = [t for t in all_trades if t['outcome'] == 'SL']
        wr = len(wins) / (len(wins) + len(losses)) * 100 if (wins or losses) else 0
        pips = sum(t['pips'] for t in all_trades)
        pf = abs(sum(t['pips'] for t in wins) / sum(t['pips'] for t in losses)) if losses and sum(t['pips'] for t in losses) != 0 else float('inf')
        print(f"  {DISPLAY_MAP[symbol]:20s} | {len(all_trades):>8} | {wr:>5.1f}% | {pips:>+7.0f}p | {pf:>6.2f}")

    # ── Recommendation ──
    print(f"\n  {'=' * 60}")
    print(f"  🎯 RECOMMENDED CONFIG PER PAIR:")
    print(f"  {'=' * 60}")
    for symbol in pairs:
        best_opt = None
        best_pf = 0
        for opt in options:
            trades = results.get((symbol, opt), [])
            wins = [t for t in trades if t['outcome'] == 'TP']
            losses = [t for t in trades if t['outcome'] == 'SL']
            pf = abs(sum(t['pips'] for t in wins) / sum(t['pips'] for t in losses)) if losses and sum(t['pips'] for t in losses) != 0 else 0
            wr = len(wins) / (len(wins) + len(losses)) * 100 if (wins or losses) else 0
            if pf > best_pf and len(trades) >= 3 and wr >= 30:
                best_pf = pf
                best_opt = opt
        if best_opt:
            t = results[(symbol, best_opt)]
            w = len([x for x in t if x['outcome'] == 'TP'])
            l = len([x for x in t if x['outcome'] == 'SL'])
            wr = w / (w + l) * 100 if (w + l) else 0
            p = sum(x['pips'] for x in t)
            print(f"  {DISPLAY_MAP[symbol]:10s} → Option {best_opt} ({OPTION_NAMES[best_opt]}) — {wr:.0f}% WR, {p:+.0f}p, PF {best_pf:.2f}")
        else:
            print(f"  {DISPLAY_MAP[symbol]:10s} → ⚠️ No option met minimum criteria (3+ signals, 30%+ WR)")

    # Show individual signals for inspection
    print(f"\n  {'=' * 60}")
    print(f"  📜 ALL SIGNALS (chronological per option)")
    print(f"  {'=' * 60}")
    for opt in options:
        print(f"\n  Option {opt} ({OPTION_NAMES[opt]}):")
        for symbol in pairs:
            trades = results.get((symbol, opt), [])
            if not trades:
                print(f"    {DISPLAY_MAP[symbol]}: no signals")
                continue
            for t in trades:
                dt = datetime.fromtimestamp(t['timestamp'], tz=timezone.utc)
                icon = '✅' if t['outcome'] == 'TP' else '❌' if t['outcome'] == 'SL' else '⏰'
                confs = ', '.join(t.get('confirmations', []))[:50]
                print(f"    {icon} {dt.strftime('%m/%d %H:%M')} {DISPLAY_MAP[symbol]:7s} {t['direction']:5s} "
                      f"→ {t['outcome']:4s} ({t['pips']:+.1f}p)  RR={t.get('risk_reward',0):.1f}  [{confs}]")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Head-to-head backtest: Opt 1 vs 4 vs 5")
    parser.add_argument("--days", type=int, default=30, help="Days of history (max 59)")
    args = parser.parse_args()

    try:
        run_head_to_head(days=args.days)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
