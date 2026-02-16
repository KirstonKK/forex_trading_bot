#!/usr/bin/env python3
"""
Backtest for Option 6: ZONE_OB_FIB_SWEEP
Corrected consolidation of Options 2 & 3 (HTF Zone + Quality OB/FVG + 79% Fib + Sweep + BOS/ChoCH)

Tests on EUR/USD and GBP/USD using yfinance CME futures data.
Walk-forward on 5M candles with multi-timeframe context (5M, 15M, 1H, 4H).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import yfinance as yf
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from core.flexible_ict_strategy import FlexibleICTStrategy, SetupType, TrendDirection


# ── Config ──────────────────────────────────────────────────────────────────
WINDOW_5M       = 100      # 5M candles lookback for strategy
STEP_CANDLES    = 6        # 6 × 5min = 30 min step
COOLDOWN_CANDLES = 48      # 48 × 5min = 4 hours between trades
FUTURE_CANDLES  = 576      # 576 × 5min = 48 hours to check SL/TP hit
STARTING_BALANCE = 10_000
RISK_PER_TRADE  = 1.0      # % of account
MAX_TRADES_DAY  = 1        # per symbol per day

SYMBOLS = [
    ('EURUSD', '6E=F',  'EUR_USD'),
    ('GBPUSD', '6B=F',  'GBP_USD'),
]


# ── Data Classes ────────────────────────────────────────────────────────────
@dataclass
class BacktestTrade:
    entry_time: datetime
    exit_time: Optional[datetime]
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: Optional[float]
    pnl_pips: float
    result: str          # WIN, LOSS, EXPIRED
    setup_type: str
    confirmations: List[str]
    rr_ratio: float = 0.0
    risk_pct: float = 0.0
    pnl_dollar: float = 0.0


# ── Data Fetching ───────────────────────────────────────────────────────────
def fetch_mtf_data(yf_symbol: str) -> Dict[str, List[dict]]:
    """Download multi-timeframe candle data from yfinance."""
    ticker = yf.Ticker(yf_symbol)
    
    def to_candles(df) -> List[dict]:
        candles = []
        for ts, row in df.iterrows():
            candles.append({
                'timestamp': int(ts.timestamp()),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': float(row.get('Volume', 0)),
            })
        return candles
    
    def aggregate_to_4h(hourly: List[dict]) -> List[dict]:
        out = []
        for i in range(0, len(hourly), 4):
            chunk = hourly[i:i+4]
            if len(chunk) >= 4:
                out.append({
                    'timestamp': chunk[0]['timestamp'],
                    'open': chunk[0]['open'],
                    'high': max(c['high'] for c in chunk),
                    'low': min(c['low'] for c in chunk),
                    'close': chunk[-1]['close'],
                    'volume': sum(c['volume'] for c in chunk),
                })
        return out
    
    print("    5M  ...", end=" ", flush=True)
    data_5m = to_candles(ticker.history(period='60d', interval='5m'))
    print(f"{len(data_5m)} candles")
    
    print("    15M ...", end=" ", flush=True)
    data_15m = to_candles(ticker.history(period='60d', interval='15m'))
    print(f"{len(data_15m)} candles")
    
    print("    1H  ...", end=" ", flush=True)
    data_1h = to_candles(ticker.history(period='730d', interval='1h'))
    print(f"{len(data_1h)} candles")
    
    data_4h = aggregate_to_4h(data_1h)
    print(f"    4H  ... {len(data_4h)} candles (aggregated)")
    
    return {'5M': data_5m, '15M': data_15m, '1H': data_1h, '4H': data_4h}


# ── Outcome Simulation ──────────────────────────────────────────────────────
def simulate_outcome(candles_5m: List[dict], entry_idx: int,
                     direction: str, stop_loss: float, take_profit: float,
                     max_future: int = FUTURE_CANDLES) -> Tuple[str, Optional[int], float]:
    """
    Walk forward from entry_idx checking if SL or TP is hit first.
    Conservative: if both touched on same candle → count as LOSS.
    
    Returns: (result, exit_idx, exit_price)
    """
    for j in range(entry_idx + 1, min(entry_idx + max_future, len(candles_5m))):
        c = candles_5m[j]
        
        if direction == 'long':
            hit_sl = c['low'] <= stop_loss
            hit_tp = c['high'] >= take_profit
        else:
            hit_sl = c['high'] >= stop_loss
            hit_tp = c['low'] <= take_profit
        
        if hit_sl and hit_tp:
            # Both hit same candle — conservative = LOSS
            return 'LOSS', j, stop_loss
        elif hit_sl:
            return 'LOSS', j, stop_loss
        elif hit_tp:
            return 'WIN', j, take_profit
    
    # Never hit either — expired
    return 'EXPIRED', None, candles_5m[min(entry_idx + max_future - 1, len(candles_5m) - 1)]['close']


# ── Backtest Runner ─────────────────────────────────────────────────────────
def run_option6_backtest(symbol: str, yf_symbol: str, internal_symbol: str,
                         all_mtf: Dict[str, Dict]) -> List[BacktestTrade]:
    """Run walk-forward backtest for Option 6 on a single pair."""
    
    mtf_data = all_mtf[internal_symbol]
    candles_5m = mtf_data['5M']
    
    if len(candles_5m) < WINDOW_5M + FUTURE_CANDLES:
        print(f"  ⚠️  Insufficient 5M data for {symbol} ({len(candles_5m)} candles)")
        return []
    
    strategy = FlexibleICTStrategy()
    trades: List[BacktestTrade] = []
    last_signal_idx = -COOLDOWN_CANDLES  # Allow first signal immediately
    last_trade_date = None
    pip_value = 0.0001 if 'JPY' not in symbol else 0.01
    
    total_steps = (len(candles_5m) - WINDOW_5M - FUTURE_CANDLES) // STEP_CANDLES
    signals_found = 0
    
    print(f"\n  Walking {total_steps} steps ({len(candles_5m)} 5M candles)...")
    
    for step, i in enumerate(range(WINDOW_5M, len(candles_5m) - FUTURE_CANDLES, STEP_CANDLES)):
        # Progress
        if step % 200 == 0 and step > 0:
            print(f"    Step {step}/{total_steps} — {signals_found} signals so far...")
        
        # Cooldown check
        if (i - last_signal_idx) < COOLDOWN_CANDLES:
            continue
        
        # 1-trade-per-day limit
        current_ts = candles_5m[i]['timestamp']
        current_dt = datetime.fromtimestamp(current_ts, tz=timezone.utc)
        current_date = current_dt.date()
        if last_trade_date == current_date:
            continue
        
        # Build MTF snapshot (no future data leak)
        snapshot_5m = candles_5m[max(0, i - WINDOW_5M):i + 1]
        snapshot_15m = [c for c in mtf_data['15M'] if c['timestamp'] <= current_ts][-100:]
        snapshot_1h  = [c for c in mtf_data['1H']  if c['timestamp'] <= current_ts][-50:]
        snapshot_4h  = [c for c in mtf_data['4H']  if c['timestamp'] <= current_ts][-20:]
        
        if len(snapshot_4h) < 10 or len(snapshot_1h) < 20:
            continue
        
        window_mtf = {
            '5M':  snapshot_5m,
            '15M': snapshot_15m,
            '1H':  snapshot_1h,
            '4H':  snapshot_4h,
        }
        
        # Reset strategy state for clean evaluation
        strategy._last_signal_time = {}
        strategy.trades_today = {}
        strategy._last_rejection_reasons = []
        strategy._last_sweep_found = False
        strategy._last_bos_found = False
        strategy.current_symbol = symbol
        
        # Set MTF data on strategy
        strategy.set_mtf_data(window_mtf)
        
        # ── Call try_option_6 directly ──
        setup_data = strategy.try_option_6(snapshot_5m, symbol)
        
        if not setup_data:
            continue
        
        # Calculate SL/TP
        entry_price = snapshot_5m[-1]['close']
        sl, tp, rr = strategy.calculate_sl_tp(entry_price, setup_data, snapshot_5m, symbol)
        
        if sl is None or tp is None or rr < 1.5:
            continue
        
        direction = setup_data['direction']
        signals_found += 1
        
        # Simulate outcome
        result, exit_idx, exit_price = simulate_outcome(
            candles_5m, i, direction, sl, tp
        )
        
        exit_time = None
        if exit_idx is not None:
            exit_time = datetime.fromtimestamp(candles_5m[exit_idx]['timestamp'], tz=timezone.utc)
        
        # Calculate P&L
        if direction == 'long':
            pnl_pips = (exit_price - entry_price) / pip_value
        else:
            pnl_pips = (entry_price - exit_price) / pip_value
        
        risk_pct = RISK_PER_TRADE if len(setup_data['confirmations']) >= 3 else RISK_PER_TRADE * 0.5
        pnl_dollar = (pnl_pips / abs((entry_price - sl) / pip_value)) * (STARTING_BALANCE * risk_pct / 100)
        
        trade = BacktestTrade(
            entry_time=current_dt,
            exit_time=exit_time,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=sl,
            take_profit=tp,
            exit_price=exit_price,
            pnl_pips=pnl_pips,
            result=result,
            setup_type=setup_data['setup_type'].value,
            confirmations=setup_data['confirmations'],
            rr_ratio=rr,
            risk_pct=risk_pct,
            pnl_dollar=pnl_dollar,
        )
        trades.append(trade)
        
        last_signal_idx = i
        last_trade_date = current_date
        
        status = "✅" if result == "WIN" else ("❌" if result == "LOSS" else "⏳")
        print(f"    {status} {current_dt.strftime('%Y-%m-%d %H:%M')} {symbol} {direction:5s} "
              f"@ {entry_price:.5f}  SL={sl:.5f}  TP={tp:.5f}  RR={rr:.1f}  "
              f"→ {result} ({pnl_pips:+.1f} pips)  [{', '.join(setup_data['confirmations'])}]")
    
    return trades


# ── Reporting ───────────────────────────────────────────────────────────────
def print_report(trades: List[BacktestTrade], title: str = "OPTION 6 BACKTEST"):
    """Print comprehensive backtest report."""
    
    closed = [t for t in trades if t.result in ('WIN', 'LOSS')]
    expired = [t for t in trades if t.result == 'EXPIRED']
    wins = [t for t in closed if t.result == 'WIN']
    losses = [t for t in closed if t.result == 'LOSS']
    
    total = len(closed)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total * 100) if total > 0 else 0
    
    total_pips = sum(t.pnl_pips for t in closed)
    avg_win_pips = sum(t.pnl_pips for t in wins) / win_count if wins else 0
    avg_loss_pips = sum(t.pnl_pips for t in losses) / loss_count if losses else 0
    
    gross_profit = sum(t.pnl_pips for t in wins) if wins else 0
    gross_loss = abs(sum(t.pnl_pips for t in losses)) if losses else 0.01
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    
    # Simulated equity curve
    equity = STARTING_BALANCE
    peak = equity
    max_dd = 0
    max_dd_pct = 0
    for t in closed:
        equity += t.pnl_dollar
        peak = max(peak, equity)
        dd = peak - equity
        dd_pct = (dd / peak * 100) if peak > 0 else 0
        max_dd = max(max_dd, dd)
        max_dd_pct = max(max_dd_pct, dd_pct)
    final_balance = equity
    
    # Confirmation frequency
    conf_counts = defaultdict(int)
    for t in trades:
        for c in t.confirmations:
            conf_counts[c] += 1
    
    # Per-pair breakdown
    by_pair = defaultdict(list)
    for t in closed:
        by_pair[t.symbol].append(t)
    
    # Direction breakdown
    longs = [t for t in closed if t.direction == 'long']
    shorts = [t for t in closed if t.direction == 'short']
    long_wr = (sum(1 for t in longs if t.result == 'WIN') / len(longs) * 100) if longs else 0
    short_wr = (sum(1 for t in shorts if t.result == 'WIN') / len(shorts) * 100) if shorts else 0
    
    # Rating
    if win_rate >= 60 and profit_factor >= 1.5:
        rating = "🏆 EXCELLENT"
    elif win_rate >= 50 and profit_factor >= 1.2:
        rating = "✅ GOOD"
    elif win_rate >= 40 and profit_factor >= 1.0:
        rating = "⚠️  MARGINAL"
    else:
        rating = "❌ NEEDS WORK"
    
    # Print
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"  Option 6: ZONE_OB_FIB_SWEEP (Corrected Consolidation of Opt 2+3)")
    print(f"{'='*80}")
    
    print(f"""
  📊 TRADE SUMMARY
  ─────────────────────────────────────────
  Total Signals:     {len(trades)}
  Closed Trades:     {total}
  Expired:           {len(expired)}
  Wins:              {win_count}
  Losses:            {loss_count}
  Win Rate:          {win_rate:.1f}%

  📈 P&L METRICS
  ─────────────────────────────────────────
  Total Pips:        {total_pips:+.1f}
  Avg Win:           {avg_win_pips:+.1f} pips
  Avg Loss:          {avg_loss_pips:+.1f} pips
  Profit Factor:     {profit_factor:.2f}

  💰 SIMULATED ACCOUNT ($10,000 start, {RISK_PER_TRADE}% risk)
  ─────────────────────────────────────────
  Final Balance:     ${final_balance:,.2f}
  Return:            {((final_balance - STARTING_BALANCE) / STARTING_BALANCE * 100):+.2f}%
  Max Drawdown:      ${max_dd:,.2f} ({max_dd_pct:.1f}%)

  📊 DIRECTION BREAKDOWN
  ─────────────────────────────────────────
  Longs:             {len(longs)} trades — {long_wr:.1f}% WR
  Shorts:            {len(shorts)} trades — {short_wr:.1f}% WR""")
    
    if by_pair:
        print(f"\n  📊 PER-PAIR BREAKDOWN")
        print(f"  ─────────────────────────────────────────")
        for pair, pair_trades in sorted(by_pair.items()):
            pw = sum(1 for t in pair_trades if t.result == 'WIN')
            pl = sum(1 for t in pair_trades if t.result == 'LOSS')
            pwr = (pw / len(pair_trades) * 100) if pair_trades else 0
            pp = sum(t.pnl_pips for t in pair_trades)
            print(f"  {pair:8s}  {len(pair_trades):3d} trades  |  W={pw} L={pl}  |  WR={pwr:.0f}%  |  {pp:+.1f} pips")
    
    if conf_counts:
        print(f"\n  🔍 CONFIRMATION FREQUENCY (across all {len(trades)} signals)")
        print(f"  ─────────────────────────────────────────")
        for conf, count in sorted(conf_counts.items(), key=lambda x: x[1], reverse=True):
            bar = "█" * min(count, 40)
            print(f"  {conf:25s}  {count:3d}  {bar}")
    
    print(f"\n  {'='*50}")
    print(f"  RATING: {rating}")
    print(f"  {'='*50}")
    
    # Comparison with original Options 2 & 3
    print(f"""
  📋 COMPARISON WITH ORIGINAL OPTIONS 2 & 3
  ─────────────────────────────────────────
  Option 2 (HTF_ZONE_OB_CHOCH):   0% WR  (no sweep, loose zones)
  Option 3 (OB_FVG_FIB):         20% WR  (no sweep, bad OBs, wrong Fib)
  Option 6 (ZONE_OB_FIB_SWEEP):  {win_rate:.1f}% WR  ← THIS BACKTEST
  
  Key fixes applied:
    ✓ Liquidity sweep is now MANDATORY
    ✓ HTF zones require min body size + mitigation check  
    ✓ OBs require 2x displacement + max 1 retest (freshness)
    ✓ FVGs require ≥2 pip gap + must still be unfilled
    ✓ 79% Fib uses proper swing point detection
    ✓ BOS or ChoCH structural confirmation required
""")
    
    # Print trade log
    if trades:
        print(f"  {'─'*110}")
        print(f"  {'Time':<20} {'Pair':<8} {'Dir':<6} {'Entry':<11} {'SL':<11} {'TP':<11} "
              f"{'RR':>4} {'P&L':>8} {'Result':<7} {'Confirmations'}")
        print(f"  {'─'*110}")
        for t in trades:
            ep = f"{t.exit_price:.5f}" if t.exit_price else "—"
            confs = ', '.join(t.confirmations[:4])
            if len(t.confirmations) > 4:
                confs += f" +{len(t.confirmations)-4}"
            print(f"  {t.entry_time.strftime('%Y-%m-%d %H:%M'):<20} {t.symbol:<8} {t.direction:<6} "
                  f"{t.entry_price:<11.5f} {t.stop_loss:<11.5f} {t.take_profit:<11.5f} "
                  f"{t.rr_ratio:>4.1f} {t.pnl_pips:>+8.1f} {t.result:<7} {confs}")
        print(f"  {'─'*110}")


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "="*80)
    print("  OPTION 6 BACKTEST: ZONE_OB_FIB_SWEEP")
    print("  Corrected Consolidation of Options 2 (0% WR) & 3 (20% WR)")
    print("  Walk-forward on 5M candles with MTF context")
    print("="*80)
    
    # Download data for all pairs
    all_mtf: Dict[str, Dict] = {}
    
    for display, yf_sym, internal in SYMBOLS:
        print(f"\n  📥 Downloading {display} ({yf_sym})...")
        try:
            data = fetch_mtf_data(yf_sym)
            if data and len(data['5M']) > 200:
                all_mtf[internal] = data
                print(f"  ✅ {display}: ready")
            else:
                print(f"  ⚠️  {display}: insufficient data")
        except Exception as e:
            print(f"  ❌ {display}: {e}")
    
    if not all_mtf:
        print("\n❌ No data available. Check your internet connection.")
        return
    
    # Run backtest per pair
    all_trades: List[BacktestTrade] = []
    
    for display, yf_sym, internal in SYMBOLS:
        if internal not in all_mtf:
            continue
        
        print(f"\n{'='*60}")
        print(f"  BACKTESTING Option 6 on {display}")
        print(f"{'='*60}")
        
        trades = run_option6_backtest(display, yf_sym, internal, all_mtf)
        all_trades.extend(trades)
        
        if trades:
            print_report(trades, title=f"OPTION 6 — {display} RESULTS")
    
    # Overall combined report
    if len(all_trades) > 0:
        print_report(all_trades, title="OPTION 6 — COMBINED RESULTS (ALL PAIRS)")
    else:
        print("\n" + "="*60)
        print("  ⚠️  NO SIGNALS GENERATED")
        print("="*60)
        print("""
  This is expected if Option 6's strict filters found no valid setups
  in the available ~60 days of 5M data from yfinance.
  
  Option 6 requires ALL of these simultaneously:
    1. Price at a validated HTF zone (unmitigated, strong candle)
    2. Quality OB or FVG overlapping the zone
    3. Price at 79% Fib (proper swing-based)
    4. Recent liquidity sweep in matching direction
    5. BOS or ChoCH structural confirmation
  
  Possible reasons for no signals:
    • The 60-day window may lack the HTF zone setups
    • CME futures prices differ slightly from spot forex
    • Market conditions may not have produced the pattern
  
  To increase signal count, consider:
    • Running on a longer dataset (CSV import)
    • Relaxing the Fib tolerance (currently 0.5%)
    • Testing on more pairs (add Gold, JPY)
""")


if __name__ == '__main__':
    main()
