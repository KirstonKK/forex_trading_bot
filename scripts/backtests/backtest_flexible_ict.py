#!/usr/bin/env python3
"""
Backtest for Flexible ICT Strategy with Improved Entry Logic
Tests the strategy on historical data and validates win rate >= 60%
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from core.flexible_ict_strategy import FlexibleICTStrategy, TrendDirection

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


class FlexibleICTBacktest:
    """Backtest engine for Flexible ICT Strategy."""
    
    def __init__(self):
        self.strategy = FlexibleICTStrategy()
        self.trades: List[BacktestTrade] = []
        
    def fetch_data(self, symbol: str) -> Dict[str, List[dict]]:
        """
        Fetch multi-timeframe data from yfinance.
        
        Returns:
            {'4H': [...], '1H': [...], '15M': [...], '5M': [...]}
        """
        ticker = yf.Ticker(symbol)
        
        # Fetch different timeframes - use '60d' for 5m/15m (yfinance limit)
        try:
            print("  Fetching 5M data...")
            data_5m = ticker.history(period='60d', interval='5m')
            print("  Fetching 15M data...")
            data_15m = ticker.history(period='60d', interval='15m')
            print("  Fetching 1H data...")
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
            """Aggregate 1H candles to 4H."""
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
    
    def run_backtest(self, symbol: str, yf_symbol: str, min_candles: int = 100) -> List[BacktestTrade]:
        """
        Run backtest on a single symbol.
        
        Args:
            symbol: Display name (e.g., 'EURUSD')
            yf_symbol: yfinance symbol (e.g., '6E=F')
            min_candles: Minimum candles before starting analysis
        """
        print(f"\n{'='*60}")
        print(f"BACKTESTING: {symbol} ({yf_symbol})")
        print(f"{'='*60}")
        
        mtf_data = self.fetch_data(yf_symbol)
        
        if not mtf_data or len(mtf_data.get('5M', [])) < min_candles:
            print(f"Insufficient data for {symbol}")
            return []
        
        print(f"Data loaded: 5M={len(mtf_data['5M'])}, 15M={len(mtf_data['15M'])}, 1H={len(mtf_data['1H'])}, 4H={len(mtf_data['4H'])} candles")
        
        # Point value for P&L calculation - Gold vs Forex
        is_gold = symbol in ['XAUUSD', 'XAU_USD', 'GOLD']
        point_value = 0.01 if is_gold else 0.00001
        
        candles_5m = mtf_data['5M']
        trades = []
        active_trade = None
        last_trade_exit_idx = -1  # Track when last trade exited
        last_trade_date = None    # Track date for 1-trade-per-day limit
        
        # Walk through 5M candles
        for i in range(min_candles, len(candles_5m)):
            current = candles_5m[i]
            current_time = datetime.fromtimestamp(current['timestamp'])
            
            # Check if active trade hit SL or TP
            if active_trade:
                if active_trade.direction == 'long':
                    if current['low'] <= active_trade.stop_loss:
                        # Hit SL
                        active_trade.exit_price = active_trade.stop_loss
                        active_trade.exit_time = current_time
                        active_trade.pnl_points = (active_trade.stop_loss - active_trade.entry_price) / point_value
                        active_trade.result = 'LOSS'
                        trades.append(active_trade)
                        active_trade = None
                        last_trade_exit_idx = i  # Set cooldown
                    elif current['high'] >= active_trade.take_profit:
                        # Hit TP
                        active_trade.exit_price = active_trade.take_profit
                        active_trade.exit_time = current_time
                        active_trade.pnl_points = (active_trade.take_profit - active_trade.entry_price) / point_value
                        active_trade.result = 'WIN'
                        trades.append(active_trade)
                        active_trade = None
                        last_trade_exit_idx = i  # Set cooldown
                else:  # short
                    if current['high'] >= active_trade.stop_loss:
                        # Hit SL
                        active_trade.exit_price = active_trade.stop_loss
                        active_trade.exit_time = current_time
                        active_trade.pnl_points = (active_trade.entry_price - active_trade.stop_loss) / point_value
                        active_trade.result = 'LOSS'
                        trades.append(active_trade)
                        active_trade = None
                        last_trade_exit_idx = i  # Set cooldown
                    elif current['low'] <= active_trade.take_profit:
                        # Hit TP
                        active_trade.exit_price = active_trade.take_profit
                        active_trade.exit_time = current_time
                        active_trade.pnl_points = (active_trade.entry_price - active_trade.take_profit) / point_value
                        active_trade.result = 'WIN'
                        trades.append(active_trade)
                        active_trade = None
                        last_trade_exit_idx = i  # Set cooldown
            
            # Only look for new trades if no active trade
            if active_trade:
                continue
            
            # Cooldown: Wait at least 12 candles (1 hour on 5M) after a trade exit
            # This prevents re-entering the same setup immediately
            if last_trade_exit_idx > 0 and (i - last_trade_exit_idx) < 12:
                continue
            
            # Max 1 trade per day limit - only take the first setup each day
            trade_date = current_time.date()
            if last_trade_date == trade_date:
                continue  # Already traded today, skip
            
            # Build MTF data window for current point
            window_mtf = {
                '5M': candles_5m[max(0, i-100):i+1],
                '15M': [c for c in mtf_data['15M'] if c['timestamp'] <= current['timestamp']][-100:],
                '1H': [c for c in mtf_data['1H'] if c['timestamp'] <= current['timestamp']][-50:],
                '4H': [c for c in mtf_data['4H'] if c['timestamp'] <= current['timestamp']][-20:]
            }
            
            # Check if we have enough data
            if len(window_mtf['4H']) < 10 or len(window_mtf['1H']) < 20:
                continue
            
            # Analyze for signal (backtest_mode=True to use candle timestamps)
            signal = self.strategy.analyze(window_mtf['5M'], symbol, window_mtf, backtest_mode=True)
            
            if signal:
                active_trade = BacktestTrade(
                    entry_time=current_time,
                    exit_time=None,
                    symbol=symbol,
                    direction=signal['direction'],
                    entry_price=signal['entry_price'],
                    stop_loss=signal['stop_loss'],
                    take_profit=signal['take_profit'],
                    exit_price=None,
                    pnl_points=0,
                    result='OPEN',
                    setup_type=signal['setup_type'],
                    confirmations=signal['confirmations']
                )
                
                # Mark this date as traded (1 trade per day limit)
                last_trade_date = current_time.date()
        
        return trades
    
    def calculate_statistics(self, trades: List[BacktestTrade]) -> Dict:
        """Calculate backtest statistics."""
        if not trades:
            return {'error': 'No trades'}
        
        closed_trades = [t for t in trades if t.result in ['WIN', 'LOSS']]
        
        if not closed_trades:
            return {'error': 'No closed trades'}
        
        wins = [t for t in closed_trades if t.result == 'WIN']
        losses = [t for t in closed_trades if t.result == 'LOSS']
        
        total = len(closed_trades)
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total) * 100 if total > 0 else 0
        
        total_pnl = sum(t.pnl_points for t in closed_trades)
        avg_win = sum(t.pnl_points for t in wins) / win_count if wins else 0
        avg_loss = sum(t.pnl_points for t in losses) / loss_count if losses else 0
        
        # Profit factor
        gross_profit = sum(t.pnl_points for t in wins) if wins else 0
        gross_loss = abs(sum(t.pnl_points for t in losses)) if losses else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Max drawdown (simplified)
        equity = 0
        peak = 0
        max_dd = 0
        for t in closed_trades:
            equity += t.pnl_points
            peak = max(peak, equity)
            dd = peak - equity
            max_dd = max(max_dd, dd)
        
        return {
            'total_trades': total,
            'wins': win_count,
            'losses': loss_count,
            'win_rate': win_rate,
            'total_pnl_points': total_pnl,
            'avg_win_points': avg_win,
            'avg_loss_points': avg_loss,
            'profit_factor': profit_factor,
            'max_drawdown_points': max_dd,
            'passed': win_rate >= 60
        }


def main():
    print("\n" + "="*70)
    print("FLEXIBLE ICT STRATEGY BACKTEST")
    print("Testing improved entry logic: Sweep → BoS → FVG/OB Tap")
    print("Pass criteria: Win Rate >= 60%")
    print("="*70)
    
    backtest = FlexibleICTBacktest()
    
    # Symbols to test (yfinance CME futures)
    symbols = [
        ('EURUSD', '6E=F'),
        ('GBPUSD', '6B=F'),
    ]
    
    all_trades = []
    
    for symbol, yf_symbol in symbols:
        trades = backtest.run_backtest(symbol, yf_symbol)
        all_trades.extend(trades)
        
        # Print individual symbol stats
        stats = backtest.calculate_statistics(trades)
        print(f"\n{symbol} Results:")
        print(f"  Total Trades: {stats.get('total_trades', 0)}")
        print(f"  Wins: {stats.get('wins', 0)}")
        print(f"  Losses: {stats.get('losses', 0)}")
        print(f"  Win Rate: {stats.get('win_rate', 0):.1f}%")
        print(f"  Profit Factor: {stats.get('profit_factor', 0):.2f}")
    
    # Overall statistics
    print("\n" + "="*70)
    print("OVERALL RESULTS")
    print("="*70)
    
    overall_stats = backtest.calculate_statistics(all_trades)
    
    if 'error' in overall_stats:
        print(f"Error: {overall_stats['error']}")
        return
    
    print(f"""
Total Trades:        {overall_stats['total_trades']}
Wins:                {overall_stats['wins']}
Losses:              {overall_stats['losses']}
Win Rate:            {overall_stats['win_rate']:.1f}%
Avg Win (points):    {overall_stats['avg_win_points']:.1f}
Avg Loss (points):   {overall_stats['avg_loss_points']:.1f}
Profit Factor:       {overall_stats['profit_factor']:.2f}
Total P&L (points):  {overall_stats['total_pnl_points']:.1f}
Max Drawdown (pts):  {overall_stats['max_drawdown_points']:.1f}
""")
    
    # Pass/Fail
    print("="*70)
    if overall_stats['passed']:
        print(f"✅ PASSED - Win Rate {overall_stats['win_rate']:.1f}% >= 60%")
    else:
        print(f"❌ FAILED - Win Rate {overall_stats['win_rate']:.1f}% < 60%")
    print("="*70)
    
    # Print trade details
    if all_trades:
        print("\nTrade Details:")
        print("-"*100)
        print(f"{'Time':<20} {'Symbol':<8} {'Dir':<6} {'Entry':<10} {'Exit':<10} {'P&L':<10} {'Result':<6} {'Setup':<20}")
        print("-"*100)
        
        for t in all_trades[:50]:  # First 50 trades
            if t.result != 'OPEN':
                print(f"{t.entry_time.strftime('%Y-%m-%d %H:%M'):<20} {t.symbol:<8} {t.direction:<6} "
                      f"{t.entry_price:<10.5f} {t.exit_price:<10.5f} {t.pnl_points:>+10.1f} "
                      f"{t.result:<6} {t.setup_type:<20}")
        
        if len(all_trades) > 50:
            print(f"... and {len(all_trades) - 50} more trades")


if __name__ == '__main__':
    main()
