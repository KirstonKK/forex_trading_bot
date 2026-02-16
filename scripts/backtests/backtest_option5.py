#!/usr/bin/env python3
"""
Backtest Option 5: Full ICT Model (ICT_SWEEP_CONFIRM)
    Sweep → BOS + iFVG + SMT + 79% → Continue → Micro BOS → Enter → DOL TP

Downloads real yfinance data (5M, 15M, 1H, 4H) for EUR_USD and GBP_USD,
walks through candles in a sliding window, and checks TP/SL outcomes.

Usage:
    python3 scripts/backtests/backtest_option5.py
    python3 scripts/backtests/backtest_option5.py --days 30
    python3 scripts/backtests/backtest_option5.py --pair EUR_USD
"""

import sys
import os
import argparse
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# Project root
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

import yfinance as yf
from core.flexible_ict_strategy import FlexibleICTStrategy, SetupType


# ── Config ────────────────────────────────────────────────────────────────────

TICKER_MAP = {
    'EUR_USD': '6E=F',   # Euro FX futures
    'GBP_USD': '6B=F',   # British Pound futures
    'XAU_USD': 'GC=F',   # Gold futures
}

DISPLAY_MAP = {
    'EUR_USD': 'EUR/USD',
    'GBP_USD': 'GBP/USD',
    'XAU_USD': 'XAU/USD',
}

# Timeframe intervals for yfinance download
TF_INTERVALS = {
    '5M':  '5m',
    '15M': '15m',
    '1H':  '1h',
}


# ── Data Download ─────────────────────────────────────────────────────────────

def download_mtf_data(symbol: str, days: int = 30) -> dict:
    """
    Download multi-timeframe candle data from yfinance.
    
    yfinance limits:
        5m  → max 60 days
        15m → max 60 days
        1h  → max 730 days
    
    We synthesise 4H from 1H candles (yfinance doesn't serve 4H directly).
    """
    ticker = TICKER_MAP[symbol]
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=min(days, 59))  # Stay within yfinance 5m limit

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
                candles.append({
                    'timestamp': int(ts.timestamp()),
                    'open': o, 'high': h, 'low': l, 'close': c, 'volume': v
                })
            data[tf_name] = candles
            print(f"    ✅ {tf_name}: {len(candles)} candles")
        except Exception as e:
            print(f"    ❌ {tf_name}: {e}")
            return {}

    # Synthesise 4H from 1H (group every 4 consecutive 1H candles)
    if '1H' in data and data['1H']:
        candles_1h = data['1H']
        candles_4h = []
        for i in range(0, len(candles_1h) - 3, 4):
            chunk = candles_1h[i:i+4]
            candles_4h.append({
                'timestamp': chunk[0]['timestamp'],
                'open':  chunk[0]['open'],
                'high':  max(c['high'] for c in chunk),
                'low':   min(c['low'] for c in chunk),
                'close': chunk[-1]['close'],
                'volume': sum(c.get('volume', 0) for c in chunk),
            })
        data['4H'] = candles_4h
        print(f"    ✅ 4H: {len(candles_4h)} candles (synthesised from 1H)")

    return data


# ── Walk-Forward Simulation ───────────────────────────────────────────────────

def simulate_outcome(signal: dict, future_candles: list, symbol: str) -> dict:
    """
    Walk future 5M candles after signal to determine TP/SL/EXPIRED.
    Conservative: if both TP and SL touched in same candle → SL.
    Expiry: 48 hours.
    """
    direction = signal['direction']
    entry = signal['entry_price']
    sl = signal['stop_loss']
    tp = signal['take_profit']
    pip_value = 0.10 if 'XAU' in symbol else 0.0001

    for c in future_candles:
        high = c['high']
        low = c['low']

        if direction == 'long':
            tp_hit = high >= tp
            sl_hit = low <= sl
        else:
            tp_hit = low <= tp
            sl_hit = high >= sl

        if tp_hit and sl_hit:
            # Both touched same candle → conservative = SL
            pips = -abs(entry - sl) / pip_value
            return {'outcome': 'SL', 'pips': round(pips, 1), 'exit_ts': c['timestamp']}
        if sl_hit:
            pips = -abs(entry - sl) / pip_value
            return {'outcome': 'SL', 'pips': round(pips, 1), 'exit_ts': c['timestamp']}
        if tp_hit:
            pips = abs(tp - entry) / pip_value
            return {'outcome': 'TP', 'pips': round(pips, 1), 'exit_ts': c['timestamp']}

    return {'outcome': 'EXPIRED', 'pips': 0, 'exit_ts': None}


def run_backtest(pairs: list, days: int = 30, option5_only: bool = True):
    """
    Main backtest loop.
    
    1. Download MTF data for all requested pairs
    2. Walk a sliding window through 5M candles
    3. For each step, build MTF snapshot and call strategy.analyze()
    4. If signal fires, walk forward to determine outcome
    """
    print("\n" + "=" * 75)
    print("  OPTION 5 BACKTEST — Full ICT Model (ICT_SWEEP_CONFIRM)")
    print("=" * 75)
    print(f"  Pairs:  {', '.join(DISPLAY_MAP.get(p, p) for p in pairs)}")
    print(f"  Period: last {days} days")
    print(f"  Mode:   {'Option 5 ONLY' if option5_only else 'All active options'}")
    print()

    # ── Download data ──
    print("📥 Downloading data from yfinance...\n")
    all_data = {}
    for symbol in pairs:
        mtf = download_mtf_data(symbol, days)
        if not mtf or '5M' not in mtf:
            print(f"  ⚠️  Skipping {symbol} — insufficient data\n")
            continue
        all_data[symbol] = mtf
        print()

    if not all_data:
        print("❌ No data for any pair. Exiting.")
        return

    # ── Prepare strategy ──
    strategy = FlexibleICTStrategy()

    # Build correlated pair data for SMT
    def build_all_market(all_d, current_sym, window_end_idx):
        """Build {symbol: {'5M': [...], '1H': [...]}} for SMT."""
        result = {}
        for sym, mtf in all_d.items():
            c5 = mtf['5M'][:window_end_idx] if sym == current_sym else mtf['5M']
            c1 = mtf.get('1H', [])
            if len(c5) >= 20 and len(c1) >= 20:
                result[sym] = {'5M': c5[-100:], '1H': c1[-48:]}
        return result

    # ── Walk forward ──
    print("=" * 75)
    print("  🏃 Running walk-forward simulation...")
    print("=" * 75 + "\n")

    WINDOW_5M = 100       # Need 100 5M candles for strategy
    STEP = 6              # Step 6 candles = 30 min per step (balance speed vs granularity)
    COOLDOWN_CANDLES = 48  # 48 × 5min = 4 hours cooldown between signals
    FUTURE_CANDLES = 576   # 576 × 5min = 48 hours for outcome check

    all_trades = []  # Collect all signals + outcomes

    for symbol in all_data:
        candles_5m = all_data[symbol]['5M']
        candles_15m = all_data[symbol].get('15M', [])
        candles_1h = all_data[symbol].get('1H', [])
        candles_4h = all_data[symbol].get('4H', [])

        print(f"  📈 {DISPLAY_MAP.get(symbol, symbol)}: walking {len(candles_5m)} × 5M candles...")

        last_signal_idx = -COOLDOWN_CANDLES  # Allow first signal immediately

        for i in range(WINDOW_5M, len(candles_5m) - FUTURE_CANDLES, STEP):
            # Cooldown
            if i - last_signal_idx < COOLDOWN_CANDLES:
                continue

            # Build MTF snapshot (candles up to current point only — no future leak)
            ts_now = candles_5m[i]['timestamp']

            snapshot_5m = candles_5m[i - WINDOW_5M:i + 1]
            snapshot_15m = [c for c in candles_15m if c['timestamp'] <= ts_now][-60:]
            snapshot_1h = [c for c in candles_1h if c['timestamp'] <= ts_now][-60:]
            snapshot_4h = [c for c in candles_4h if c['timestamp'] <= ts_now][-30:]

            if len(snapshot_1h) < 24 or len(snapshot_4h) < 10:
                continue

            mtf_data = {
                '5M':  snapshot_5m,
                '15M': snapshot_15m,
                '1H':  snapshot_1h,
                '4H':  snapshot_4h,
            }

            # Reset strategy state for clean analysis
            strategy._last_signal_time = {}  # Bypass live cooldown
            strategy.trades_today = {}       # Bypass daily limit
            strategy.set_mtf_data(mtf_data)

            # Set correlated pair data for SMT
            all_market = build_all_market(all_data, symbol, i + 1)
            strategy.set_all_market_data(all_market)

            if option5_only:
                # Directly call try_option_5
                strategy._last_rejection_reasons = []
                strategy._last_sweep_found = False
                strategy._last_bos_found = False
                strategy.current_symbol = symbol

                setup_data = strategy.try_option_5(snapshot_5m, symbol)
                if not setup_data:
                    continue

                # Calculate SL/TP
                entry_price = snapshot_5m[-1]['close']
                stop_loss, take_profit, rr_ratio = strategy.calculate_sl_tp(
                    entry_price, setup_data, snapshot_5m, symbol
                )
                if stop_loss is None:
                    continue

                signal = {
                    'timestamp': ts_now,
                    'symbol': symbol,
                    'setup_type': setup_data['setup_type'].value,
                    'direction': setup_data['direction'],
                    'entry_price': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'risk_reward': rr_ratio,
                    'confirmations': setup_data['confirmations'],
                    'sweep_info': setup_data.get('sweep_info', {}),
                    'smt_info': setup_data.get('smt_info'),
                    'dol_tp': setup_data.get('dol_tp'),
                }
            else:
                # Use full analyze() with all active options
                signal = strategy.analyze(snapshot_5m, symbol=symbol,
                                          mtf_data=mtf_data, backtest_mode=True)
                if not signal:
                    continue

            # ── Determine outcome ──
            future = candles_5m[i + 1: i + 1 + FUTURE_CANDLES]
            outcome = simulate_outcome(signal, future, symbol)

            trade = {**signal, **outcome}
            all_trades.append(trade)
            last_signal_idx = i

            dt = datetime.fromtimestamp(ts_now, tz=timezone.utc)
            icon = '✅' if outcome['outcome'] == 'TP' else '❌' if outcome['outcome'] == 'SL' else '⏰'
            confs = ', '.join(signal.get('confirmations', []))
            print(
                f"    {icon} {dt.strftime('%m/%d %H:%M')} "
                f"{signal['direction'].upper():5s} "
                f"@ {signal['entry_price']:.5f}  "
                f"SL={signal['stop_loss']:.5f}  "
                f"TP={signal['take_profit']:.5f}  "
                f"RR={signal.get('risk_reward', 0):.1f}  "
                f"→ {outcome['outcome']:7s} ({outcome['pips']:+.1f}p)  "
                f"[{confs}]"
            )

        print()

    # ── Summary ──
    print_results(all_trades, pairs, days)
    return all_trades


# ── Results Printer ───────────────────────────────────────────────────────────

def print_results(trades: list, pairs: list, days: int):
    """Print formatted backtest results."""
    print("=" * 75)
    print("  📊 BACKTEST RESULTS — Option 5 (ICT_SWEEP_CONFIRM)")
    print("=" * 75)

    if not trades:
        print("\n  ⚠️  No trades generated in this period.")
        print("  This is expected if the strategy is very selective.")
        print("  Try increasing --days or adding more pairs.\n")
        return

    # Overall stats
    total = len(trades)
    wins = [t for t in trades if t['outcome'] == 'TP']
    losses = [t for t in trades if t['outcome'] == 'SL']
    expired = [t for t in trades if t['outcome'] == 'EXPIRED']

    win_rate = len(wins) / (len(wins) + len(losses)) * 100 if (wins or losses) else 0
    total_pips = sum(t['pips'] for t in trades)
    avg_win_pips = sum(t['pips'] for t in wins) / len(wins) if wins else 0
    avg_loss_pips = sum(t['pips'] for t in losses) / len(losses) if losses else 0
    profit_factor = abs(sum(t['pips'] for t in wins) / sum(t['pips'] for t in losses)) if losses and sum(t['pips'] for t in losses) != 0 else float('inf')

    # Simulated account (starting $10k, 1% risk per trade)
    balance = 10000.0
    peak = balance
    max_dd = 0
    for t in trades:
        if t['outcome'] == 'TP':
            balance += balance * 0.01 * t.get('risk_reward', 2.0)
        elif t['outcome'] == 'SL':
            balance -= balance * 0.01
        peak = max(peak, balance)
        dd = (peak - balance) / peak * 100
        max_dd = max(max_dd, dd)

    print(f"\n  Period: last {days} days")
    print(f"  Pairs:  {', '.join(DISPLAY_MAP.get(p, p) for p in pairs)}")

    print(f"\n  ┌─────────────────────────────────────┐")
    print(f"  │  Total Signals:   {total:>4}              │")
    print(f"  │  Wins (TP):       {len(wins):>4}  ({win_rate:.1f}%)      │")
    print(f"  │  Losses (SL):     {len(losses):>4}              │")
    print(f"  │  Expired:         {len(expired):>4}              │")
    print(f"  │                                     │")
    print(f"  │  Total Pips:     {total_pips:>+8.1f}           │")
    print(f"  │  Avg Win:        {avg_win_pips:>+8.1f} pips      │")
    print(f"  │  Avg Loss:       {avg_loss_pips:>+8.1f} pips      │")
    print(f"  │  Profit Factor:  {profit_factor:>8.2f}           │")
    print(f"  │                                     │")
    print(f"  │  Sim Balance:    ${balance:>10,.2f}       │")
    print(f"  │  Sim Return:     {((balance - 10000) / 10000 * 100):>+7.2f}%          │")
    print(f"  │  Max Drawdown:   {max_dd:>7.2f}%          │")
    print(f"  └─────────────────────────────────────┘")

    # Per-pair breakdown
    print(f"\n  📋 Breakdown by Pair:")
    print(f"  {'Pair':<12} {'Signals':>8} {'Wins':>6} {'WR%':>7} {'Pips':>9} {'PF':>7}")
    print(f"  {'─'*51}")
    for symbol in sorted(set(t['symbol'] for t in trades)):
        pair_trades = [t for t in trades if t['symbol'] == symbol]
        pw = [t for t in pair_trades if t['outcome'] == 'TP']
        pl = [t for t in pair_trades if t['outcome'] == 'SL']
        pwr = len(pw) / (len(pw) + len(pl)) * 100 if (pw or pl) else 0
        pp = sum(t['pips'] for t in pair_trades)
        ppf = abs(sum(t['pips'] for t in pw) / sum(t['pips'] for t in pl)) if pl and sum(t['pips'] for t in pl) != 0 else float('inf')
        print(f"  {DISPLAY_MAP.get(symbol, symbol):<12} {len(pair_trades):>8} {len(pw):>6} {pwr:>6.1f}% {pp:>+8.1f} {ppf:>7.2f}")

    # Confirmation frequency
    print(f"\n  🔍 Confirmation Frequency:")
    conf_counts = defaultdict(int)
    for t in trades:
        for c in t.get('confirmations', []):
            conf_counts[c] += 1
    for conf, count in sorted(conf_counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        bar = '█' * int(pct / 2)
        print(f"    {conf:<25} {count:>3} ({pct:>5.1f}%) {bar}")

    # Win rate by confirmation combo
    print(f"\n  🎯 Win Rate by Key Confirmations:")
    for conf_name in ['SMT_DIVERGENCE', 'iFVG', 'FIB_79_EXT']:
        with_conf = [t for t in trades if conf_name in t.get('confirmations', [])]
        without_conf = [t for t in trades if conf_name not in t.get('confirmations', [])]
        if with_conf:
            w = len([t for t in with_conf if t['outcome'] == 'TP'])
            l = len([t for t in with_conf if t['outcome'] == 'SL'])
            wr = w / (w + l) * 100 if (w + l) > 0 else 0
            print(f"    With {conf_name:<20}: {wr:>5.1f}% WR ({w}W/{l}L from {len(with_conf)} signals)")
        if without_conf:
            w = len([t for t in without_conf if t['outcome'] == 'TP'])
            l = len([t for t in without_conf if t['outcome'] == 'SL'])
            wr = w / (w + l) * 100 if (w + l) > 0 else 0
            print(f"    Without {conf_name:<17}: {wr:>5.1f}% WR ({w}W/{l}L from {len(without_conf)} signals)")

    # DOL TP effectiveness
    dol_trades = [t for t in trades if t.get('dol_tp')]
    rr_trades = [t for t in trades if not t.get('dol_tp')]
    if dol_trades or rr_trades:
        print(f"\n  🎯 TP Method Comparison:")
        if dol_trades:
            dw = len([t for t in dol_trades if t['outcome'] == 'TP'])
            dl = len([t for t in dol_trades if t['outcome'] == 'SL'])
            dwr = dw / (dw + dl) * 100 if (dw + dl) > 0 else 0
            print(f"    DOL-based TP:  {dwr:.1f}% WR ({dw}W/{dl}L), avg pips: {sum(t['pips'] for t in dol_trades)/len(dol_trades):+.1f}")
        if rr_trades:
            rw = len([t for t in rr_trades if t['outcome'] == 'TP'])
            rl = len([t for t in rr_trades if t['outcome'] == 'SL'])
            rwr = rw / (rw + rl) * 100 if (rw + rl) > 0 else 0
            print(f"    Fixed R:R TP:   {rwr:.1f}% WR ({rw}W/{rl}L), avg pips: {sum(t['pips'] for t in rr_trades)/len(rr_trades):+.1f}")

    # Rating
    print(f"\n  {'=' * 50}")
    if win_rate >= 60 and profit_factor >= 1.5:
        print(f"  🌟 EXCELLENT — Ready for live trading")
    elif win_rate >= 50 and profit_factor >= 1.2:
        print(f"  ✅ GOOD — Promising, monitor live results")
    elif win_rate >= 40 and profit_factor >= 1.0:
        print(f"  ⚠️  MARGINAL — Needs more data or tuning")
    else:
        print(f"  ❌ NEEDS WORK — Review entry logic")
    print(f"  {'=' * 50}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest Option 5 — Full ICT Model")
    parser.add_argument("--days", type=int, default=30, help="Days of history (max 59 for 5M data)")
    parser.add_argument("--pair", type=str, default=None,
                        help="Single pair to test (EUR_USD, GBP_USD, XAU_USD)")
    parser.add_argument("--all-options", action="store_true",
                        help="Test all active options (1,4,5) not just Option 5")
    args = parser.parse_args()

    pairs = [args.pair] if args.pair else ['EUR_USD', 'GBP_USD']
    # Note: XAU_USD excluded by default — 0% WR historically, add with --pair XAU_USD

    try:
        run_backtest(pairs, days=args.days, option5_only=not args.all_options)
    except KeyboardInterrupt:
        print("\n\n⚠️  Backtest interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
