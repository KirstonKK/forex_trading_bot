"""
Backtesting Engine
Test SMC strategy on historical data for minimum 100 trades.
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np

from core.smc_strategy import SMCAnalyzer, SMCEntrySignal
from core.enhanced_risk_manager import EnhancedRiskManager, TradingSession
from database.journal import TradeJournal


class BacktestResult:
    """Results from a backtest run."""

    def __init__(self):
        self.trades = []
        self.statistics = {}
        self.equity_curve = []
        self.drawdown_curve = []


class BacktestEngine:
    """Backtesting engine for SMC strategy."""

    def __init__(
        self,
        account_balance: float = 10000.0,
        risk_per_trade: float = 1.0,
        symbols: List[str] = None
    ):
        self.account_balance = account_balance
        self.initial_balance = account_balance
        self.risk_per_trade = risk_per_trade
        self.symbols = symbols or ["EURUSD", "GBPUSD", "XAUUSD"]
        
        self.analyzer = SMCAnalyzer()
        self.risk_manager = EnhancedRiskManager(
            account_balance=account_balance,
            risk_per_trade=risk_per_trade,
            allowed_sessions=[]  # Disable session filtering for backtest (synthetic data has no real timestamps)
        )
        self.journal = TradeJournal("data/backtest_journal.db")
        
        self.current_balance = account_balance
        self.trades = []
        self.active_trade = None

    def backtest_symbol(
        self,
        symbol: str,
        candles: List[Dict],
        start_index: int = 100
    ) -> List[Dict]:
        """
        Backtest SMC strategy on a single symbol's candle data.
        
        Args:
            symbol: Trading pair
            candles: Historical OHLCV candles
            start_index: Start testing from this index (allow warmup)
            
        Returns:
            List of executed trades
        """
        executed_trades = []
        lookback_candles = []
        
        for i in range(start_index, len(candles)):
            current_candle = candles[i]
            
            # Maintain lookback window
            lookback_candles = candles[max(0, i-50):i+1]
            
            # Check if trade should be closed
            if self.active_trade:
                self._check_trade_exit(current_candle, symbol)
            
            # Only open trades during allowed sessions (simplified for backtest)
            # In real backtest, use the timestamp from candle
            
            if not self.active_trade:
                # Analyze for entry signal
                signal = self.analyzer.analyze(lookback_candles)
                
                if signal and signal.risk_reward_ratio >= 1.5:
                    # Attempt to open trade
                    trade = self._open_trade(
                        symbol=symbol,
                        signal=signal,
                        candle=current_candle,
                        index=i
                    )
                    
                    if trade:
                        self.active_trade = trade
                        executed_trades.append(trade)
        
        return executed_trades

    def _open_trade(
        self,
        symbol: str,
        signal: SMCEntrySignal,
        candle: Dict,
        index: int
    ) -> Optional[Dict]:
        """Open a trade from entry signal."""
        
        # Validate trade
        validation = self.risk_manager.validate_trade(
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            target_price=signal.target_price
        )
        
        if not all(validation.values()):
            return None
        
        # Calculate position size
        position_size = self.risk_manager.calculate_position_size(
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            symbol=symbol
        )
        
        if position_size <= 0:
            return None
        
        # Calculate risk/reward amounts
        risk = abs(signal.entry_price - signal.stop_loss)
        reward = abs(signal.target_price - signal.entry_price)
        
        trade = {
            'id': f"BT_{symbol}_{index}",
            'symbol': symbol,
            'index': index,
            'entry_time': candle.get('timestamp'),
            'entry_price': signal.entry_price,
            'stop_loss': signal.stop_loss,
            'take_profit': signal.target_price,
            'quantity': position_size,
            'risk_reward_ratio': signal.risk_reward_ratio,
            'entry_zone_type': signal.entry_zone_type.value,
            'bos_strength': signal.bos.strength,
            'pullback_confidence': signal.pullback_zone.confidence,
            'signal_strength': signal.strength,
            'risk_amount': risk * position_size,
            'reward_amount': reward * position_size,
            'status': 'open',
            'account_balance_at_entry': self.current_balance
        }
        
        return trade

    def _check_trade_exit(self, current_candle: Dict, symbol: str):  # noqa: ARG002
        """Check if active trade should be closed."""
        if not self.active_trade:
            return
        
        low = current_candle['low']
        high = current_candle['high']
        
        # Hit stop loss
        if low <= self.active_trade['stop_loss']:
            self._close_trade(
                exit_price=self.active_trade['stop_loss'],
                exit_reason='stop_loss'
            )
        
        # Hit take profit
        elif high >= self.active_trade['take_profit']:
            self._close_trade(
                exit_price=self.active_trade['take_profit'],
                exit_reason='take_profit'
            )

    def _close_trade(self, exit_price: float, exit_reason: str):
        """Close active trade and update balance."""
        if not self.active_trade:
            return
        
        risk_dollars = self.active_trade['quantity']  # This is dollars at risk
        
        # Simple P&L: 
        # - Stop hit = -risk_dollars
        # - TP hit = +risk_dollars * RR_ratio
        
        if exit_reason == 'stop_loss':
            pnl = -risk_dollars
        elif exit_reason == 'take_profit':
            # Use the RR ratio from the signal
            rr_ratio = self.active_trade['risk_reward_ratio']
            pnl = risk_dollars * (rr_ratio - 1)  # -1 because 2:1 RR means 1x profit on risk
        else:
            pnl = 0
        
        pnl_percent = (pnl / self.initial_balance) * 100 if self.initial_balance else 0
        
        # Update trade
        self.active_trade['exit_price'] = exit_price
        self.active_trade['exit_reason'] = exit_reason
        self.active_trade['pnl'] = pnl
        self.active_trade['pnl_percent'] = pnl_percent
        self.active_trade['status'] = 'closed'
        
        # Update balance
        self.current_balance += pnl
        self.risk_manager.record_trade_outcome(pnl)
        
        # Log to journal
        self.journal.log_trade(self.active_trade)
        
        self.trades.append(self.active_trade)
        self.active_trade = None

    def backtest(
        self,
        historical_data: Dict[str, List[Dict]]
    ) -> BacktestResult:
        """
        Run complete backtest on multiple symbols.
        
        Args:
            historical_data: Dict of {symbol: [candles]}
            
        Returns:
            BacktestResult with statistics
        """
        all_trades = []
        
        # Backtest each symbol
        for symbol in self.symbols:
            if symbol not in historical_data:
                continue
            
            candles = historical_data[symbol]
            trades = self.backtest_symbol(symbol, candles)
            all_trades.extend(trades)
        
        # Generate results
        result = BacktestResult()
        result.trades = all_trades
        result.statistics = self._calculate_statistics(all_trades)
        result.equity_curve = self._calculate_equity_curve()
        result.drawdown_curve = self._calculate_drawdown()
        
        return result

    def _calculate_statistics(self, trades: List[Dict]) -> Dict:
        """Calculate trading statistics."""
        if not trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "total_pnl": 0.0,
                "final_balance": self.current_balance
            }
        
        closed_trades = [t for t in trades if t['status'] == 'closed']
        winners = [t for t in closed_trades if t['pnl'] > 0]
        losers = [t for t in closed_trades if t['pnl'] < 0]
        
        total_wins = sum(t['pnl'] for t in winners)
        total_losses = sum(t['pnl'] for t in losers)
        
        return {
            "total_trades": len(closed_trades),
            "winning_trades": len(winners),
            "losing_trades": len(losers),
            "win_rate": (len(winners) / len(closed_trades) * 100) if closed_trades else 0,
            "avg_win": total_wins / len(winners) if winners else 0,
            "avg_loss": total_losses / len(losers) if losers else 0,
            "profit_factor": total_wins / abs(total_losses) if total_losses != 0 else 0,
            "total_pnl": total_wins + total_losses,
            "final_balance": self.current_balance
        }

    def _calculate_equity_curve(self) -> List[float]:
        """Calculate equity curve over time."""
        equity = [self.account_balance]
        balance = self.account_balance
        
        for trade in sorted(self.trades, key=lambda t: t.get('entry_time', 0)):
            if trade['status'] == 'closed':
                balance += trade.get('pnl', 0)
                equity.append(balance)
        
        return equity

    def _calculate_drawdown(self) -> List[float]:
        """Calculate drawdown curve."""
        equity = self._calculate_equity_curve()
        drawdown = []
        peak = equity[0]
        
        for e in equity:
            if e > peak:
                peak = e
            dd = ((peak - e) / peak) * 100 if peak > 0 else 0
            drawdown.append(dd)
        
        return drawdown

    def get_results_summary(self, result: BacktestResult) -> str:
        """Generate summary of backtest results."""
        stats = result.statistics
        
        summary = f"""
        ===== BACKTEST RESULTS =====
        Total Trades: {stats['total_trades']}
        Winning Trades: {stats['winning_trades']}
        Losing Trades: {stats['losing_trades']}
        Win Rate: {stats['win_rate']:.2f}%
        
        Average Win: ${stats['avg_win']:.2f}
        Average Loss: ${stats['avg_loss']:.2f}
        Profit Factor: {stats['profit_factor']:.2f}
        
        Total P&L: ${stats['total_pnl']:.2f}
        Initial Balance: ${self.account_balance:.2f}
        Final Balance: ${stats['final_balance']:.2f}
        Return: {((stats['final_balance'] - self.account_balance) / self.account_balance * 100):.2f}%
        
        Max Drawdown: {max(result.drawdown_curve):.2f}%
        ============================
        """
        
        return summary
