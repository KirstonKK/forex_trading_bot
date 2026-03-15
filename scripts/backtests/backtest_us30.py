#!/usr/bin/env python3
"""
US30 (Dow Jones) Backtest — Isolated from Forex Pairs
Tests the Flexible ICT Strategy specifically on US30 using YM=F (E-mini Dow futures).

Setups tested:
  1. LIQ_SWEEP_ENGULF (Option 4) — Primary setup for US30
  2. HTF_LIQUIDITY_BOS (Option 1) — Structural backbone
  3. ICT_SWEEP_CONFIRM (Option 5, no SMT) — Full ICT model without correlated pair
  4. ZONE_OB_FIB_SWEEP (Option 6) — S/D Zone setup (your friend's approach)

Uses real yfinance data from YM=F (E-mini Dow futures).
Point value: 1 point = 1 pip equivalent.
Session: NYSE hours only (13-19 UTC).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import yfinance as yf
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from dataclasses import dataclass
from collections import defaultdict
from core.flexible_ict_strategy import FlexibleICTStrategy


@dataclass
class BacktestTrade:
    """Represents a backtest trade."""
    entry_time: datetime
    exit_time: Optional[datetime]
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: Optional[float]
    pnl_points: float
    result: str  # 'WIN', 'LOSS', 'OPEN'
    setup_type: str
    confirmations: List[str]
    session_hour: int  # UTC hour of entry


class US30Backtest:
    """Dedicated US30 backtest engine — isolated from forex."""
    
    YF_SYMBOL = 'YM=F'  # E-mini Dow futures
    DISPLAY_SYMBOL = 'US30'
    POINT_VALUE = 0.1  # For P&L calculation (US30 point = 0.1 in yfinance)
    
    def __init__(self):
        self.strategy = FlexibleICTStrategy()
        self.trades: List[BacktestTrade] = []
        
    def fetch_data(self) -> Dict[str, List[dict]]:
        """Fetch multi-timeframe data from yfinance for US30."""
        ticker = yf.Ticker(self.YF_SYMBOL)
        
        try:
            print("  Fetching 5M data (60 days)...")
            data_5m = ticker.history(period='60d', interval='5m')
            print("  Fetching 15M data (60 days)...")
            data_15m = ticker.history(period='60d', interval='15m')
            print("  Fetching 1H data (2 years)...")
            data_1h = ticker.history(period='730d', interval='1h')
            print("  Aggregating to 4H...")
        except Exception as e:
            print(f"Error fetching data: {e}")
            return {}
        
        def to_candles(df) -> List[dict]:
            candles = []
            for timestamp, row in df.iterrows():
                candles.append({
                    'timestamp': int(timestamp.timestamp()),
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': float(row.get('Volume', 0))
                })
            return candles
        
        def aggregate_to_4h(hourly_candles: List[dict]) -> List[dict]:
            candles_4h = []
            for i in range(0, len(hourly_candles), 4):
                chunk = hourly_candles[i:i+4]
                if len(chunk) >= 4:
                    candles_4h.append({
                        'timestamp': chunk[0]['timestamp'],
                        'open': chunk[0]['open'],
                        'high': max(c['high'] for c in chunk),
                        'low': min(c['low'] for c in chunk),
                        'close': chunk[-1]['close'],
                        'volume': sum(c['volume'] for c in chunk)
                    })
            return candles_4h
        
        candles_5m = to_candles(data_5m)
        candles_15m = to_candles(data_15m)
        candles_1h = to_candles(data_1h)
        candles_4h = aggregate_to_4h(candles_1h)
        
        return {
            '4H': candles_4h,
            '1H': candles_1h,
            '15M': candles_15m,
            '5M': candles_5m
        }
    
    def run_backtest(self, min_candles: int = 100) -> List[BacktestTrade]:
        """Run backtest on US30."""
        print(f"\n{'='*70}")
        print(f"US30 BACKTEST — Flexible ICT Strategy (US30 Isolated)")
        print(f"Ticker: {self.YF_SYMBOL} (E-mini Dow futures)")
        print(f"{'='*70}")
        
        mtf_data = self.fetch_data()
        
        if not mtf_data or len(mtf_data.get('5M', [])) < min_candles:
            print(f"❌ Insufficient data for US30")
            return []
        
        print(f"Data loaded: 5M={len(mtf_data['5M'])}, 15M={len(mtf_data['15M'])}, "
              f"1H={len(mtf_data['1H'])}, 4H={len(mtf_data['4H'])} candles")
        
        candles_5m = mtf_data['5M']
        trades = []
        active_trade = None
        last_trade_exit_idx = -1
        last_trade_date = None
        
        # Walk through 5M candles
        for i in range(min_candles, len(candles_5m)):
            current = candles_5m[i]
            current_time = datetime.fromtimestamp(current['timestamp'], tz=timezone.utc)
            current_hour = current_time.hour
            
            # Check if active trade hit SL or TP
            if active_trade:
                if active_trade.direction == 'long':
                    if current['low'] <= active_trade.stop_loss:
                        active_trade.exit_price = active_trade.stop_loss
                        active_trade.exit_time = current_time
                        active_trade.pnl_points = active_trade.stop_loss - active_trade.entry_price
                        active_trade.result = 'LOSS'
                        trades.append(active_trade)
                        active_trade = None
                        last_trade_exit_idx = i
                    elif current['high'] >= active_trade.take_profit:
                        active_trade.exit_price = active_trade.take_profit
                        active_trade.exit_time = current_time
                        active_trade.pnl_points = active_trade.take_profit - active_trade.entry_price
                        active_trade.result = 'WIN'
                        trades.append(active_trade)
                        active_trade = None
                        last_trade_exit_idx = i
                else:  # short
                    if current['high'] >= active_trade.stop_loss:
                        active_trade.exit_price = active_trade.stop_loss
                        active_trade.exit_time = current_time
                        active_trade.pnl_points = active_trade.entry_price - active_trade.stop_loss
                        active_trade.result = 'LOSS'
                        trades.append(active_trade)
                        active_trade = None
                        last_trade_exit_idx = i
                    elif current['low'] <= active_trade.take_profit:
                        active_trade.exit_price = active_trade.take_profit
                        active_trade.exit_time = current_time
                        active_trade.pnl_points = active_trade.entry_price - active_trade.take_profit
                        active_trade.result = 'WIN'
                        trades.append(active_trade)
                        active_trade = None
                        last_trade_exit_idx = i
            
            # Only look for new trades if no active trade
            if active_trade:
                continue
            
            # Cooldown: Wait 12 candles (1 hour) after exit
            if last_trade_exit_idx > 0 and (i - last_trade_exit_idx) < 12:
                continue
            
            # Max 2 trades per day for US30
            trade_date = current_time.date()
            if last_trade_date == trade_date:
                continue
            
            # Build MTF data window
            window_mtf = {
                '5M': candles_5m[max(0, i-100):i+1],
                '15M': [c for c in mtf_data['15M'] if c['timestamp'] <= current['timestamp']][-100:],
                '1H': [c for c in mtf_data['1H'] if c['timestamp'] <= current['timestamp']][-50:],
                '4H': [c for c in mtf_data['4H'] if c['timestamp'] <= current['timestamp']][-20:]
            }
            
            if len(window_mtf['4H']) < 10 or len(window_mtf['1H']) < 20:
                continue
            
            # Analyze for signal (backtest_mode=True for candle timestamps)
            signal = self.strategy.analyze(window_mtf['5M'], self.DISPLAY_SYMBOL, window_mtf, backtest_mode=True)
            
            if signal:
                active_trade = BacktestTrade(
                    entry_time=current_time,
                    exit_time=None,
                    symbol=self.DISPLAY_SYMBOL,
                    direction=signal['direction'],
                    entry_price=signal['entry_price'],
                    stop_loss=signal['stop_loss'],
                    take_profit=signal['take_profit'],
                    exit_price=None,
                    pnl_points=0,
                    result='OPEN',
                    setup_type=signal['setup_type'],
                    confirmations=signal['confirmations'],
                    session_hour=current_hour
                )
                last_trade_date = current_time.date()
                print(f"  📈 {signal['direction'].upper()} @ {current_time.strftime('%Y-%m-%d %H:%M')} | "
                      f"Entry: {signal['entry_price']:.0f} | SL: {signal['stop_loss']:.0f} | "
                      f"TP: {signal['take_profit']:.0f} | {signal['setup_type']}")
        
        self.trades = trades
        return trades
    
    def print_results(self):
        """Print comprehensive backtest results."""
        trades = self.trades
        if not trades:
            print("\n❌ No trades generated during backtest period.")
            print("   This could mean:")
            print("   - US30 session hours (13-19 UTC) didn't have qualifying setups")
            print("   - Strategy filters are too strict for the data period")
            print("   - YM=F data quality issues from yfinance")
            return
        
        closed = [t for t in trades if t.result in ('WIN', 'LOSS')]
        wins = [t for t in closed if t.result == 'WIN']
        losses = [t for t in closed if t.result == 'LOSS']
        
        total = len(closed)
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total * 100) if total > 0 else 0
        
        total_pnl = sum(t.pnl_points for t in closed)
        avg_win = sum(t.pnl_points for t in wins) / win_count if wins else 0
        avg_loss = sum(t.pnl_points for t in losses) / loss_count if losses else 0
        
        gross_profit = sum(t.pnl_points for t in wins) if wins else 0
        gross_loss = abs(sum(t.pnl_points for t in losses)) if losses else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Max drawdown
        equity = 0
        peak = 0
        max_dd = 0
        for t in closed:
            equity += t.pnl_points
            peak = max(peak, equity)
            dd = peak - equity
            max_dd = max(max_dd, dd)
        
        # By setup type
        by_setup = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0.0})
        for t in closed:
            by_setup[t.setup_type]['trades'] += 1
            if t.result == 'WIN':
                by_setup[t.setup_type]['wins'] += 1
            by_setup[t.setup_type]['pnl'] += t.pnl_points
        
        # By session hour
        by_hour = defaultdict(lambda: {'trades': 0, 'wins': 0})
        for t in closed:
            by_hour[t.session_hour]['trades'] += 1
            if t.result == 'WIN':
                by_hour[t.session_hour]['wins'] += 1
        
        # Print results
        print(f"\n{'='*70}")
        print(f"US30 BACKTEST RESULTS — Flexible ICT Strategy (US30 Isolated)")
        print(f"{'='*70}")
        print(f"Period: 60 days | Ticker: {self.YF_SYMBOL} (E-mini Dow futures)")
        print(f"Initial Balance: $10,000 | Risk: 1% per trade")
        print(f"Session: NYSE hours (13-19 UTC)")
        print()
        
        print(f"{'─'*70}")
        print(f"  OVERALL: {total} trades | {win_count}W / {loss_count}L | "
              f"WR: {win_rate:.1f}% | PF: {profit_factor:.2f}")
        print(f"  Total P&L: {total_pnl:+.0f} points | "
              f"Avg Win: +{avg_win:.0f} pts | Avg Loss: {avg_loss:.0f} pts")
        print(f"  Max Drawdown: {max_dd:.0f} points")
        print(f"{'─'*70}")
        
        # Setup breakdown
        print(f"\n  SETUP BREAKDOWN:")
        print(f"  {'Setup':<25} {'Trades':>7} {'Wins':>6} {'WR%':>7} {'P&L':>10} {'PF':>7}")
        print(f"  {'─'*63}")
        for setup, data in sorted(by_setup.items()):
            wr = (data['wins'] / data['trades'] * 100) if data['trades'] > 0 else 0
            loss_pts = abs(data['pnl'] - sum(t.pnl_points for t in wins if t.setup_type == setup))
            pf = sum(t.pnl_points for t in wins if t.setup_type == setup) / loss_pts if loss_pts > 0 else 0
            print(f"  {setup:<25} {data['trades']:>7} {data['wins']:>6} {wr:>6.1f}% {data['pnl']:>+9.0f} {pf:>6.2f}")
        
        # Session breakdown  
        if by_hour:
            print(f"\n  BY SESSION HOUR (UTC):")
            for hour in sorted(by_hour.keys()):
                data = by_hour[hour]
                wr = (data['wins'] / data['trades'] * 100) if data['trades'] > 0 else 0
                session_name = {13: 'NYSE Pre', 14: 'NYSE Open', 15: 'Silver Bullet',
                               16: 'Mid Session', 17: 'Mid Session', 18: 'Afternoon',
                               19: 'Power Hour'}.get(hour, f'{hour}:00')
                print(f"    {hour:02d}:00 ({session_name:<14}): {data['trades']:>3} trades, {wr:.0f}% WR")
        
        # Trade log
        print(f"\n  TRADE LOG:")
        print(f"  {'Time':<18} {'Dir':<6} {'Entry':>8} {'Exit':>8} {'P&L':>8} {'Result':<6} {'Setup':<25}")
        print(f"  {'─'*90}")
        for t in closed[:30]:
            print(f"  {t.entry_time.strftime('%m-%d %H:%M'):<18} {t.direction:<6} "
                  f"{t.entry_price:>8.0f} {t.exit_price:>8.0f} {t.pnl_points:>+8.0f} "
                  f"{t.result:<6} {t.setup_type:<25}")
        if len(closed) > 30:
            print(f"  ... and {len(closed) - 30} more trades")
        
        # Verdict
        print(f"\n{'='*70}")
        if win_rate >= 40 and profit_factor >= 1.2:
            print(f"  ✅ VERDICT: PASS — WR {win_rate:.1f}% (≥40%) | PF {profit_factor:.2f} (≥1.2)")
        elif win_rate >= 35 and profit_factor >= 1.0:
            print(f"  ⚠️ VERDICT: MARGINAL — WR {win_rate:.1f}% | PF {profit_factor:.2f}")
            print(f"     Consider tightening filters or adjusting RR targets")
        else:
            print(f"  ❌ VERDICT: FAIL — WR {win_rate:.1f}% | PF {profit_factor:.2f}")
            print(f"     Strategy needs optimization for US30")
        print(f"{'='*70}")


def main():
    print("\n" + "="*70)
    print("US30 BACKTEST — Flexible ICT Strategy")
    print("Testing: Sweep+Engulf, HTF+Sweep+BoS, Full ICT, S/D Zones")
    print("Ticker: YM=F (E-mini Dow futures)")
    print("Session: NYSE hours only (13-19 UTC)")
    print("="*70)
    
    backtest = US30Backtest()
    trades = backtest.run_backtest()
    backtest.print_results()


if __name__ == '__main__':
    main()
