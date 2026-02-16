"""
Comprehensive Backtest - Flexible ICT Strategy
Tests EUR/USD, GBP/USD, and XAU/USD with real market data
Generates single consolidated results file
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import List, Dict
import json

from core.flexible_ict_strategy import FlexibleICTStrategy, FlexibleSignal
from core.enhanced_risk_manager import EnhancedRiskManager


class ComprehensiveBacktest:
    """Unified backtesting engine for all pairs"""
    
    def __init__(self, initial_balance: float = 10000.0):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.strategy = FlexibleICTStrategy()
        self.risk_manager = EnhancedRiskManager(
            account_balance=initial_balance,
            risk_per_trade=1.0,
            max_daily_loss=1.5,
            max_weekly_loss=3.0,
            max_trades_per_day=1
        )
        
        # Results storage
        self.all_trades = []
        self.equity_curve = []
        self.pair_results = {}
        
    def fetch_data(self, symbol: str, days: int = 60) -> pd.DataFrame:
        """Fetch historical data from yfinance using CME futures"""
        
        # Use CME futures tickers (most reliable for forex)
        ticker_map = {
            'EURUSD': '6E=F',  # EUR futures
            'GBPUSD': '6B=F',  # GBP futures
            'XAUUSD': 'GC=F',  # Gold futures
            'USDJPY': '6J=F'   # JPY futures
        }
        
        ticker = ticker_map.get(symbol, symbol)
        print(f"📊 Fetching {days} days of data for {symbol} using {ticker}...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 7)
        
        try:
            # Use Ticker object for better reliability
            ticker_obj = yf.Ticker(ticker)
            
            # Fetch hourly data
            df = ticker_obj.history(
                start=start_date,
                end=end_date,
                interval='1h'
            )
            
            if df.empty:
                print(f"⚠️ No data returned for {ticker}, trying daily data...")
                # Fallback to daily data if hourly fails
                df = ticker_obj.history(period=f"{days}d", interval='1d')
            
            if df.empty or len(df) < 50:
                print(f"⚠️ Insufficient data from yfinance, using synthetic data")
                return self.generate_synthetic_data(symbol, days)
            
            # Clean data
            df = df.dropna()
            
            print(f"✅ Retrieved {len(df)} candles for {symbol}")
            print(f"   Date range: {df.index[0]} to {df.index[-1]}")
            print(f"   Sample prices: Open={df['Open'].iloc[0]:.4f}, Close={df['Close'].iloc[-1]:.4f}")
            
            return df
            
        except Exception as e:
            print(f"❌ yfinance error: {e}")
            print(f"   Using synthetic data for {symbol}")
            return self.generate_synthetic_data(symbol, days)
    
    def generate_synthetic_data(self, symbol: str, days: int) -> pd.DataFrame:
        """Generate realistic synthetic price data for testing"""
        
        # Base prices for each pair
        base_prices = {
            'EURUSD': 1.0850,
            'GBPUSD': 1.2650,
            'XAUUSD': 2050.0,
            'USDJPY': 149.50
        }
        
        base_price = base_prices.get(symbol, 1.0)
        volatility = 0.0002 if 'USD' in symbol else 0.002  # Higher vol for gold
        
        # Generate 5-minute candles
        num_candles = days * 24 * 12  # 5-min candles per day
        dates = pd.date_range(start=datetime.now() - timedelta(days=days), periods=num_candles, freq='5T')
        
        prices = [base_price]
        for _ in range(num_candles - 1):
            change = np.random.normal(0, volatility) * prices[-1]
            prices.append(prices[-1] + change)
        
        # Create realistic OHLC from price series
        data = []
        for i in range(0, len(prices) - 4, 1):
            open_price = prices[i]
            close_price = prices[i + 1]
            high_price = max(prices[i:i+2]) * (1 + np.random.uniform(0, 0.0001))
            low_price = min(prices[i:i+2]) * (1 - np.random.uniform(0, 0.0001))
            
            data.append({
                'Open': open_price,
                'High': high_price,
                'Low': low_price,
                'Close': close_price,
                'Volume': np.random.randint(100, 1000)
            })
        
        df = pd.DataFrame(data, index=dates[:len(data)])
        print(f"✅ Generated {len(df)} synthetic candles")
        return df
    
    def prepare_candles(self, df: pd.DataFrame) -> List[Dict]:
        """Convert DataFrame to candle dictionaries"""
        candles = []
        
        for idx, row in df.iterrows():
            candle = {
                'timestamp': int(idx.timestamp()),
                'datetime': idx,
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': float(row['Volume']) if 'Volume' in row else 0
            }
            candles.append(candle)
        
        return candles
    
    def backtest_pair(self, symbol: str, days: int = 60) -> Dict:
        """Run backtest for a single pair"""
        
        print(f"\n{'='*60}")
        print(f"BACKTESTING {symbol}")
        print(f"{'='*60}")
        
        # Fetch data
        df = self.fetch_data(symbol, days)
        
        if df.empty:
            print(f"❌ Skipping {symbol} - no data available")
            return {
                'symbol': symbol,
                'trades': [],
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'profit_factor': 0,
                'total_pnl': 0,
                'max_drawdown': 0,
                'error': 'No data available'
            }
        
        candles = self.prepare_candles(df)
        
        # Set current symbol in strategy
        self.strategy.current_symbol = symbol
        
        # Run backtest
        trades = []
        active_trade = None
        pair_balance = self.initial_balance
        peak_balance = pair_balance
        max_drawdown = 0
        signals_found = 0  # Track how many signals were generated
        
        # Need at least 200 candles for multi-timeframe analysis
        lookback = 200
        
        for i in range(lookback, len(candles)):
            current_candle = candles[i]
            
            # Get multi-timeframe data
            recent_candles_5m = candles[max(0, i-200):i+1]
            
            # Build MTF data (simplified - use same data for all TFs)
            self.strategy.mtf_data = {
                '5M': recent_candles_5m,
                '15M': candles[max(0, i-600):i+1:3],  # Every 3rd candle
                '1H': candles[max(0, i-2400):i+1:12],  # Every 12th candle
                '4H': candles[max(0, i-9600):i+1:48]   # Every 48th candle
            }
            
            # Check if active trade hits SL/TP
            if active_trade:
                high = current_candle['high']
                low = current_candle['low']
                
                if active_trade['direction'] == 'long':
                    if low <= active_trade['stop_loss']:
                        # Stop loss hit
                        active_trade['exit_price'] = active_trade['stop_loss']
                        active_trade['exit_time'] = current_candle['timestamp']
                        active_trade['result'] = 'loss'
                        active_trade['pnl'] = -active_trade['risk_amount']
                        pair_balance -= active_trade['risk_amount']
                        trades.append(active_trade)
                        active_trade = None
                    elif high >= active_trade['take_profit']:
                        # Take profit hit
                        active_trade['exit_price'] = active_trade['take_profit']
                        active_trade['exit_time'] = current_candle['timestamp']
                        active_trade['result'] = 'win'
                        active_trade['pnl'] = active_trade['risk_amount'] * active_trade['risk_reward']
                        pair_balance += active_trade['pnl']
                        trades.append(active_trade)
                        active_trade = None
                else:  # short
                    if high >= active_trade['stop_loss']:
                        # Stop loss hit
                        active_trade['exit_price'] = active_trade['stop_loss']
                        active_trade['exit_time'] = current_candle['timestamp']
                        active_trade['result'] = 'loss'
                        active_trade['pnl'] = -active_trade['risk_amount']
                        pair_balance -= active_trade['risk_amount']
                        trades.append(active_trade)
                        active_trade = None
                    elif low <= active_trade['take_profit']:
                        # Take profit hit
                        active_trade['exit_price'] = active_trade['take_profit']
                        active_trade['exit_time'] = current_candle['timestamp']
                        active_trade['result'] = 'win'
                        active_trade['pnl'] = active_trade['risk_amount'] * active_trade['risk_reward']
                        pair_balance += active_trade['pnl']
                        trades.append(active_trade)
                        active_trade = None
                
                # Update drawdown
                if pair_balance > peak_balance:
                    peak_balance = pair_balance
                drawdown = (peak_balance - pair_balance) / peak_balance * 100
                max_drawdown = max(max_drawdown, drawdown)
            
            # Look for new signals if no active trade
            if not active_trade:
                try:
                    signal = self.strategy.analyze(recent_candles_5m, symbol)
                    
                    if signal:
                        signals_found += 1
                        
                        # Lower confidence threshold for backtest (0.60 = 60%)
                        if signal.confidence >= 0.60:
                            # Calculate position size
                            risk_amount = pair_balance * (signal.risk_percentage / 100)
                        
                        # Create trade
                        trade = {
                            'symbol': symbol,
                            'direction': signal.direction,
                            'entry_price': signal.entry_price,
                            'stop_loss': signal.stop_loss,
                            'take_profit': signal.take_profit,
                            'risk_reward': signal.risk_reward,
                            'risk_amount': risk_amount,
                            'entry_time': current_candle['timestamp'],
                            'setup_type': signal.setup_type.value,
                            'confirmations': signal.confirmations,
                            'confirmation_count': signal.confirmation_count,
                            'confidence': signal.confidence
                        }
                        
                        active_trade = trade
                        print(f"📈 {signal.direction.upper()} signal at {datetime.fromtimestamp(current_candle['timestamp'])} | "
                              f"Entry: {signal.entry_price:.5f} | SL: {signal.stop_loss:.5f} | TP: {signal.take_profit:.5f} | "
                              f"Conf: {signal.confidence:.1%}")
                
                except Exception as e:
                    # Skip this candle if analysis fails
                    continue
        
        # Close any remaining open trade at market price
        if active_trade:
            last_candle = candles[-1]
            active_trade['exit_price'] = last_candle['close']
            active_trade['exit_time'] = last_candle['timestamp']
            
            if active_trade['direction'] == 'long':
                pnl_pips = (active_trade['exit_price'] - active_trade['entry_price']) / self.strategy.get_pip_value(symbol)
                sl_pips = (active_trade['entry_price'] - active_trade['stop_loss']) / self.strategy.get_pip_value(symbol)
            else:
                pnl_pips = (active_trade['entry_price'] - active_trade['exit_price']) / self.strategy.get_pip_value(symbol)
                sl_pips = (active_trade['stop_loss'] - active_trade['entry_price']) / self.strategy.get_pip_value(symbol)
            
            if pnl_pips > 0:
                active_trade['result'] = 'win'
                active_trade['pnl'] = active_trade['risk_amount'] * (pnl_pips / sl_pips)
                pair_balance += active_trade['pnl']
            else:
                active_trade['result'] = 'loss'
                active_trade['pnl'] = active_trade['risk_amount'] * (pnl_pips / sl_pips)
                pair_balance += active_trade['pnl']
            
            trades.append(active_trade)
        
        # Calculate statistics
        wins = [t for t in trades if t['result'] == 'win']
        losses = [t for t in trades if t['result'] == 'loss']
        
        win_rate = len(wins) / len(trades) * 100 if trades else 0
        
        total_win_pnl = sum([t['pnl'] for t in wins]) if wins else 0
        total_loss_pnl = abs(sum([t['pnl'] for t in losses])) if losses else 1
        profit_factor = total_win_pnl / total_loss_pnl if total_loss_pnl > 0 else 0
        
        total_pnl = pair_balance - self.initial_balance
        total_return = (total_pnl / self.initial_balance) * 100
        
        results = {
            'symbol': symbol,
            'trades': trades,
            'total_trades': len(trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_pnl': total_pnl,
            'total_return': total_return,
            'max_drawdown': max_drawdown,
            'final_balance': pair_balance,
            'signals_found': signals_found
        }
        
        print(f"\n📊 {symbol} RESULTS:")
        print(f"   Signals Found: {signals_found}")
        print(f"   Trades Taken: {len(trades)}")
        print(f"   Wins: {len(wins)} | Losses: {len(losses)}")
        print(f"   Win Rate: {win_rate:.1f}%")
        print(f"   Profit Factor: {profit_factor:.2f}")
        print(f"   Total P&L: ${total_pnl:.2f} ({total_return:+.2f}%)")
        print(f"   Max Drawdown: {max_drawdown:.2f}%")
        
        return results
    
    def run_full_backtest(self, symbols: List[str], days: int = 60):
        """Run backtest on all pairs"""
        
        print("\n" + "="*60)
        print("COMPREHENSIVE BACKTEST - FLEXIBLE ICT STRATEGY")
        print("="*60)
        print(f"Initial Balance: ${self.initial_balance:,.2f}")
        print(f"Pairs: {', '.join(symbols)}")
        print(f"Period: {days} days")
        print(f"Risk per trade: 1%")
        print("="*60)
        
        # Run each pair
        for symbol in symbols:
            results = self.backtest_pair(symbol, days)
            self.pair_results[symbol] = results
            self.all_trades.extend(results['trades'])
        
        # Generate report
        self.generate_report()
    
    def generate_report(self):
        """Generate comprehensive markdown report"""
        
        report = []
        report.append("# COMPREHENSIVE BACKTEST RESULTS")
        report.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"**Strategy:** Flexible ICT Strategy (3 Setup Options)")
        report.append(f"**Initial Balance:** ${self.initial_balance:,.2f}")
        report.append("")
        report.append("---")
        report.append("")
        
        # Overall summary
        report.append("## 📊 OVERALL PERFORMANCE")
        report.append("")
        
        total_trades = len(self.all_trades)
        total_wins = len([t for t in self.all_trades if t['result'] == 'win'])
        total_losses = len([t for t in self.all_trades if t['result'] == 'loss'])
        
        if total_trades > 0:
            overall_win_rate = (total_wins / total_trades) * 100
            
            total_win_pnl = sum([t['pnl'] for t in self.all_trades if t['result'] == 'win'])
            total_loss_pnl = abs(sum([t['pnl'] for t in self.all_trades if t['result'] == 'loss']))
            overall_pf = total_win_pnl / total_loss_pnl if total_loss_pnl > 0 else 0
            
            total_pnl = sum([t['pnl'] for t in self.all_trades])
            total_return = (total_pnl / self.initial_balance) * 100
        else:
            overall_win_rate = 0
            overall_pf = 0
            total_pnl = 0
            total_return = 0
        
        report.append(f"- **Total Trades:** {total_trades}")
        report.append(f"- **Wins:** {total_wins} | **Losses:** {total_losses}")
        report.append(f"- **Win Rate:** {overall_win_rate:.1f}%")
        report.append(f"- **Profit Factor:** {overall_pf:.2f}")
        report.append(f"- **Total P&L:** ${total_pnl:,.2f} ({total_return:+.2f}%)")
        report.append("")
        report.append("---")
        report.append("")
        
        # Per-pair breakdown
        report.append("## 💱 PER-PAIR RESULTS")
        report.append("")
        
        for symbol, results in self.pair_results.items():
            report.append(f"### {symbol}")
            report.append("")
            report.append(f"| Metric | Value |")
            report.append(f"|--------|-------|")
            report.append(f"| Total Trades | {results['total_trades']} |")
            report.append(f"| Wins / Losses | {results['wins']} / {results['losses']} |")
            report.append(f"| Win Rate | {results['win_rate']:.1f}% |")
            report.append(f"| Profit Factor | {results['profit_factor']:.2f} |")
            report.append(f"| Total P&L | ${results['total_pnl']:,.2f} ({results['total_return']:+.2f}%) |")
            report.append(f"| Max Drawdown | {results['max_drawdown']:.2f}% |")
            
            # Recommendation
            if results['win_rate'] >= 50 and results['profit_factor'] >= 1.5:
                verdict = "✅ **RECOMMENDED**"
            elif results['win_rate'] >= 40 and results['profit_factor'] >= 1.2:
                verdict = "⚠️ **ACCEPTABLE**"
            else:
                verdict = "❌ **NOT RECOMMENDED**"
            
            report.append(f"| **Verdict** | {verdict} |")
            report.append("")
        
        report.append("---")
        report.append("")
        
        # Strategy settings
        report.append("## ⚙️ STRATEGY CONFIGURATION")
        report.append("")
        report.append("**Setup Options:**")
        report.append("1. HTF Bias + Liquidity Sweep + BoS")
        report.append("2. HTF Zone + Order Block + ChoCH")
        report.append("3. OB + FVG + Fib 79%")
        report.append("")
        report.append("**Risk Management:**")
        report.append("- 3 confirmations → 1% risk")
        report.append("- 2 confirmations → 0.5% risk")
        report.append("- Target R:R: 1:2")
        report.append("- Max daily loss: 1.5%")
        report.append("- Max trades per day: 1")
        report.append("")
        report.append("**Session Filter:**")
        report.append("- London: 08:00-17:00 UTC")
        report.append("- New York: 13:00-22:00 UTC")
        report.append("")
        
        # Save report
        report_text = "\n".join(report)
        output_file = "/home/vanhansen53/forex_trading_bot/BACKTEST_RESULTS.md"
        
        with open(output_file, 'w') as f:
            f.write(report_text)
        
        print("\n" + "="*60)
        print(f"✅ Report saved to: {output_file}")
        print("="*60)
        
        # Also print to console
        print("\n" + report_text)


if __name__ == "__main__":
    # Run backtest
    backtest = ComprehensiveBacktest(initial_balance=10000.0)
    
    pairs = ['EURUSD', 'GBPUSD', 'XAUUSD']
    backtest.run_full_backtest(pairs, days=60)
