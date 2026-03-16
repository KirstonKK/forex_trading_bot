#!/usr/bin/env python3
"""
US30 (Dow Jones) Long-Period Backtest — 1H Candle Based
Uses 1H candles as the base timeframe, giving ~2 years of data from yfinance
(730 days vs 60-day limit on 5M data).

Trade-offs vs 5M backtest:
  + 12x more data (730 days vs 60)
  + More statistically significant results
  - Entry at 1H close (less precise than 5M entry)
  - 15M lookback simulated from 1H data

Setups tested: LIQ_SWEEP_ENGULF (the only validated US30 setup)
Session: 13:00 UTC only (NYSE open kill zone)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import yfinance as yf
from datetime import datetime, timezone
from typing import List, Dict, Optional
from dataclasses import dataclass
from collections import defaultdict
from core.flexible_ict_strategy import FlexibleICTStrategy


@dataclass
class BacktestTrade:
    entry_time: datetime
    exit_time: Optional[datetime]
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: Optional[float]
    pnl_points: float
    result: str
    setup_type: str
    session_hour: int


class US30Backtest1H:
    """US30 backtest using 1H candles as base — longer data period."""

    YF_SYMBOL = 'YM=F'
    DISPLAY_SYMBOL = 'US30'

    def __init__(self):
        self.strategy = FlexibleICTStrategy()
        self._reset_state()
        self.trades: List[BacktestTrade] = []

    def _reset_state(self):
        """Reset all strategy state for clean backtest."""
        self.strategy._last_signal_time = {}
        self.strategy._recent_signals = {}
        self.strategy._recent_losses = {}
        self.strategy._consecutive_losses = 0
        self.strategy._circuit_breaker_until = 0
        self.strategy._daily_losses = 0
        self.strategy._daily_loss_date = None
        self.strategy.trades_today = {}
        self.strategy.current_date = None

    def fetch_data(self) -> Dict[str, List[dict]]:
        """Fetch 1H and 4H data from yfinance (730 days)."""
        ticker = yf.Ticker(self.YF_SYMBOL)

        print("  Fetching 1H data (2 years = 730 days)...")
        data_1h = ticker.history(period='730d', interval='1h')
        print(f"  Got {len(data_1h)} hourly candles")

        def to_candles(df) -> List[dict]:
            return [
                {
                    'timestamp': int(ts.timestamp()),
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': float(row.get('Volume', 0))
                }
                for ts, row in df.iterrows()
            ]

        def aggregate_to_4h(hourly: List[dict]) -> List[dict]:
            result = []
            for i in range(0, len(hourly), 4):
                chunk = hourly[i:i+4]
                if len(chunk) >= 4:
                    result.append({
                        'timestamp': chunk[0]['timestamp'],
                        'open': chunk[0]['open'],
                        'high': max(c['high'] for c in chunk),
                        'low': min(c['low'] for c in chunk),
                        'close': chunk[-1]['close'],
                        'volume': sum(c['volume'] for c in chunk)
                    })
            return result

        def simulate_15m_from_1h(hourly: List[dict]) -> List[dict]:
            """Simulate 15M candles from 1H data (4 segments per hour)."""
            result = []
            for c in hourly:
                o, h, l, cl = c['open'], c['high'], c['low'], c['close']
                price_range = h - l
                for seg in range(4):
                    seg_open = o + (cl - o) * (seg / 4)
                    seg_close = o + (cl - o) * ((seg + 1) / 4)
                    seg_high = min(max(seg_open, seg_close) + price_range * 0.15, h)
                    seg_low = max(min(seg_open, seg_close) - price_range * 0.15, l)
                    result.append({
                        'timestamp': c['timestamp'] + seg * 900,
                        'open': seg_open, 'high': seg_high,
                        'low': seg_low, 'close': seg_close,
                        'volume': c['volume'] / 4
                    })
            return result

        candles_1h = to_candles(data_1h)
        candles_4h = aggregate_to_4h(candles_1h)
        candles_15m = simulate_15m_from_1h(candles_1h)

        return {
            '4H': candles_4h,
            '1H': candles_1h,
            '15M': candles_15m,
            '5M': candles_15m,  # Use 15M as "5M" proxy (strategy uses base timeframe)
        }

    def run_backtest(self) -> List[BacktestTrade]:
        """Walk through 1H candles, signal at 13:00 UTC each day."""
        print(f"\n{'='*70}")
        print(f"US30 LONG-PERIOD BACKTEST — 1H Base (2 Years)")
        print(f"Ticker: {self.YF_SYMBOL} | Session: 13:00 UTC only")
        print(f"{'='*70}")

        mtf_data = self.fetch_data()
        candles_1h = mtf_data['1H']

        if len(candles_1h) < 100:
            print("❌ Insufficient data")
            return []

        print(f"Data: 1H={len(candles_1h)}, 4H={len(mtf_data['4H'])}, "
              f"15M={len(mtf_data['15M'])} candles (~{len(candles_1h)//24} days)")

        trades = []
        active_trade = None
        last_trade_exit_idx = -1

        for i in range(50, len(candles_1h)):
            current = candles_1h[i]
            current_time = datetime.fromtimestamp(current['timestamp'], tz=timezone.utc)
            hour = current_time.hour
            weekday = current_time.weekday()

            # Skip weekends
            if weekday >= 5:
                continue

            # Check active trade exit
            if active_trade:
                if active_trade.direction == 'long':
                    if current['low'] <= active_trade.stop_loss:
                        active_trade.pnl_points = active_trade.stop_loss - active_trade.entry_price
                        active_trade.exit_price = active_trade.stop_loss
                        active_trade.exit_time = current_time
                        active_trade.result = 'LOSS'
                        trades.append(active_trade)
                        active_trade = None
                        last_trade_exit_idx = i
                    elif current['high'] >= active_trade.take_profit:
                        active_trade.pnl_points = active_trade.take_profit - active_trade.entry_price
                        active_trade.exit_price = active_trade.take_profit
                        active_trade.exit_time = current_time
                        active_trade.result = 'WIN'
                        trades.append(active_trade)
                        active_trade = None
                        last_trade_exit_idx = i
                else:
                    if current['high'] >= active_trade.stop_loss:
                        active_trade.pnl_points = active_trade.entry_price - active_trade.stop_loss
                        active_trade.exit_price = active_trade.stop_loss
                        active_trade.exit_time = current_time
                        active_trade.result = 'LOSS'
                        trades.append(active_trade)
                        active_trade = None
                        last_trade_exit_idx = i
                    elif current['low'] <= active_trade.take_profit:
                        active_trade.pnl_points = active_trade.entry_price - active_trade.take_profit
                        active_trade.exit_price = active_trade.take_profit
                        active_trade.exit_time = current_time
                        active_trade.result = 'WIN'
                        trades.append(active_trade)
                        active_trade = None
                        last_trade_exit_idx = i

            if active_trade:
                continue

            # Only look for entries at 13:00 UTC (NYSE kill zone)
            if hour != 13:
                continue

            # Cooldown: at least 3 hours (3 candles) after last exit
            if last_trade_exit_idx > 0 and (i - last_trade_exit_idx) < 3:
                continue

            # Build MTF window
            window_mtf = {
                '4H': [c for c in mtf_data['4H'] if c['timestamp'] <= current['timestamp']][-20:],
                '1H': candles_1h[max(0, i-50):i+1],
                '15M': [c for c in mtf_data['15M'] if c['timestamp'] <= current['timestamp']][-60:],
                '5M': [c for c in mtf_data['15M'] if c['timestamp'] <= current['timestamp']][-60:],
            }

            if len(window_mtf['4H']) < 10 or len(window_mtf['1H']) < 20:
                continue

            # Reset state so daily limits don't block us
            self.strategy.trades_today = {}
            self.strategy.current_date = None

            signal = self.strategy.analyze(
                window_mtf['5M'], self.DISPLAY_SYMBOL, window_mtf, backtest_mode=True
            )

            if signal:
                active_trade = BacktestTrade(
                    entry_time=current_time,
                    exit_time=None,
                    direction=signal['direction'],
                    entry_price=signal['entry_price'],
                    stop_loss=signal['stop_loss'],
                    take_profit=signal['take_profit'],
                    exit_price=None,
                    pnl_points=0,
                    result='OPEN',
                    setup_type=signal['setup_type'],
                    session_hour=hour
                )
                print(f"  📈 {signal['direction'].upper()} @ {current_time.strftime('%Y-%m-%d %H:%M')} | "
                      f"Entry: {signal['entry_price']:.0f} | SL: {signal['stop_loss']:.0f} | "
                      f"TP: {signal['take_profit']:.0f} | {signal['setup_type']}")

        self.trades = trades
        return trades

    def print_results(self):
        trades = self.trades
        if not trades:
            print("\n❌ No trades generated.")
            return

        closed = [t for t in trades if t.result in ('WIN', 'LOSS')]
        wins = [t for t in closed if t.result == 'WIN']
        losses = [t for t in closed if t.result == 'LOSS']

        total = len(closed)
        win_rate = (len(wins) / total * 100) if total > 0 else 0
        total_pnl = sum(t.pnl_points for t in closed)
        avg_win = sum(t.pnl_points for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.pnl_points for t in losses) / len(losses) if losses else 0

        gross_profit = sum(t.pnl_points for t in wins) if wins else 0
        gross_loss = abs(sum(t.pnl_points for t in losses)) if losses else 1
        pf = gross_profit / gross_loss if gross_loss > 0 else 0

        # Max drawdown
        equity, peak, max_dd = 0, 0, 0
        for t in closed:
            equity += t.pnl_points
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)

        # By month
        by_month = defaultdict(lambda: {'w': 0, 'l': 0, 'pnl': 0.0})
        for t in closed:
            key = t.entry_time.strftime('%Y-%m')
            by_month[key]['pnl'] += t.pnl_points
            if t.result == 'WIN':
                by_month[key]['w'] += 1
            else:
                by_month[key]['l'] += 1

        print(f"\n{'='*70}")
        print(f"US30 LONG-PERIOD BACKTEST RESULTS (1H Base)")
        print(f"{'='*70}")
        print(f"Period: ~2 years | Ticker: YM=F | Session: 13:00 UTC only")
        print()
        print(f"{'─'*70}")
        print(f"  OVERALL: {total} trades | {len(wins)}W / {len(losses)}L | "
              f"WR: {win_rate:.1f}% | PF: {pf:.2f}")
        print(f"  Total P&L: {total_pnl:+.0f} pts | "
              f"Avg Win: +{avg_win:.0f} pts | Avg Loss: {avg_loss:.0f} pts")
        print(f"  Max Drawdown: {max_dd:.0f} pts")
        print(f"{'─'*70}")

        # Monthly breakdown
        print(f"\n  MONTHLY BREAKDOWN:")
        print(f"  {'Month':<10} {'W':>4} {'L':>4} {'WR%':>7} {'P&L':>9}")
        print(f"  {'─'*40}")
        for month in sorted(by_month.keys()):
            d = by_month[month]
            t_count = d['w'] + d['l']
            wr = (d['w'] / t_count * 100) if t_count > 0 else 0
            print(f"  {month:<10} {d['w']:>4} {d['l']:>4} {wr:>6.0f}% {d['pnl']:>+8.0f}")

        # Trade log (last 20)
        print(f"\n  TRADE LOG (most recent 20):")
        print(f"  {'Time':<18} {'Dir':<6} {'Entry':>8} {'Exit':>8} {'P&L':>8} {'Result'}")
        print(f"  {'─'*65}")
        for t in closed[-20:]:
            print(f"  {t.entry_time.strftime('%Y-%m-%d %H:%M'):<18} {t.direction:<6} "
                  f"{t.entry_price:>8.0f} {t.exit_price:>8.0f} {t.pnl_points:>+8.0f} {t.result}")

        print(f"\n{'='*70}")
        if win_rate >= 40 and pf >= 1.2:
            print(f"  ✅ VERDICT: PASS — WR {win_rate:.1f}% | PF {pf:.2f}")
        elif win_rate >= 35 and pf >= 1.0:
            print(f"  ⚠️  VERDICT: MARGINAL — WR {win_rate:.1f}% | PF {pf:.2f}")
        else:
            print(f"  ❌ VERDICT: FAIL — WR {win_rate:.1f}% | PF {pf:.2f}")
        print(f"{'='*70}")


if __name__ == '__main__':
    bt = US30Backtest1H()
    bt.run_backtest()
    bt.print_results()
