"""
Trade Performance Tracker
Monitors actual signal performance and calculates real win rates.
Automatically resolves signals when price hits TP or SL.
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / 'data'
TRADES_FILE = DATA_DIR / 'active_trades.json'
HISTORY_FILE = DATA_DIR / 'trade_history.json'


def _calculate_pips(price_diff: float, symbol: str) -> float:
    """
    Calculate pips from a price difference.
    Forex pairs: 1 pip = 0.0001 (10,000 multiplier)
    Gold (XAU):  1 pip = 0.10   (10 multiplier)
    """
    if 'XAU' in symbol or 'GOLD' in symbol:
        return price_diff * 10  # Gold: $0.10 = 1 pip
    return price_diff * 10000   # Forex: 0.0001 = 1 pip


@dataclass
class Trade:
    """Active trade being monitored."""
    signal_id: str
    symbol: str
    direction: str  # 'long' or 'short'
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_time: str
    setup_type: str
    confidence: float
    
    # Performance tracking
    status: str = 'active'  # 'active', 'win', 'loss', 'breakeven'
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    pips_result: Optional[float] = None
    rr_achieved: Optional[float] = None


class TradeTracker:
    """Track and analyze trade performance."""
    
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.active_trades: Dict[str, Trade] = self._load_active_trades()
        self.history: List[Dict] = self._load_history()
    
    def _load_active_trades(self) -> Dict[str, Trade]:
        """Load active trades from file."""
        try:
            if TRADES_FILE.exists():
                with open(TRADES_FILE, 'r') as f:
                    data = json.load(f)
                    return {k: Trade(**v) for k, v in data.items()}
        except Exception as e:
            logger.error(f"Error loading active trades: {e}")
        return {}
    
    def _save_active_trades(self):
        """Save active trades to file."""
        try:
            with open(TRADES_FILE, 'w') as f:
                data = {k: asdict(v) for k, v in self.active_trades.items()}
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving active trades: {e}")
    
    def _load_history(self) -> List[Dict]:
        """Load trade history."""
        try:
            if HISTORY_FILE.exists():
                with open(HISTORY_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading history: {e}")
        return []
    
    def _save_history(self):
        """Save trade history."""
        try:
            with open(HISTORY_FILE, 'w') as f:
                json.dump(self.history, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving history: {e}")
    
    def add_trade(self, signal: Dict[str, Any], symbol: str, signal_id: str = None):
        """
        Add a new trade to track.
        
        Args:
            signal: Signal dict from strategy.analyze()
            symbol: e.g. 'EUR_USD'
            signal_id: Key from active_signals dict (used to sync resolution)
        """
        trade_id = signal_id or f"{symbol}_{signal.get('timestamp', int(datetime.now().timestamp()))}"
        
        # Don't double-register
        if trade_id in self.active_trades:
            logger.debug(f"Trade {trade_id} already tracked, skipping")
            return trade_id
        
        trade = Trade(
            signal_id=trade_id,
            symbol=symbol,
            direction=signal.get('direction', 'long'),
            entry_price=signal.get('entry_price', 0),
            stop_loss=signal.get('stop_loss', 0),
            take_profit=signal.get('take_profit', 0),
            entry_time=datetime.fromtimestamp(signal.get('timestamp', datetime.now().timestamp())).isoformat(),
            setup_type=signal.get('setup_type', 'UNKNOWN'),
            confidence=signal.get('confidence', 0.0)
        )
        
        self.active_trades[trade_id] = trade
        self._save_active_trades()
        logger.info(f"📊 Tracking new trade: {trade_id} | {trade.direction} {symbol} @ {trade.entry_price:.5f} | SL={trade.stop_loss:.5f} TP={trade.take_profit:.5f}")
        return trade_id
    
    def update_trades(self, symbol: str, current_price: float) -> List[Dict[str, Any]]:
        """
        Check if any active trades for this symbol hit TP or SL.
        
        Returns:
            List of resolved trade dicts (for notifications/status sync).
        """
        resolved = []
        to_remove = []
        
        for signal_id, trade in self.active_trades.items():
            if trade.symbol != symbol or trade.status != 'active':
                continue
            
            # Check if TP or SL hit
            hit_tp = False
            hit_sl = False
            
            if trade.direction in ('long', 'buy'):
                hit_tp = current_price >= trade.take_profit
                hit_sl = current_price <= trade.stop_loss
            else:  # short / sell
                hit_tp = current_price <= trade.take_profit
                hit_sl = current_price >= trade.stop_loss
            
            if hit_tp:
                trade.status = 'win'
                trade.exit_price = trade.take_profit
                trade.exit_time = datetime.now().isoformat()
                
                # Calculate pips using symbol-aware function
                if trade.direction in ('long', 'buy'):
                    trade.pips_result = _calculate_pips(trade.take_profit - trade.entry_price, symbol)
                else:
                    trade.pips_result = _calculate_pips(trade.entry_price - trade.take_profit, symbol)
                
                sl_distance = _calculate_pips(abs(trade.entry_price - trade.stop_loss), symbol)
                trade.rr_achieved = trade.pips_result / sl_distance if sl_distance > 0 else 0
                
                logger.info(f"✅ TP HIT — {signal_id} | +{trade.pips_result:.1f} pips | RR: {trade.rr_achieved:.2f}")
                to_remove.append(signal_id)
                resolved.append(asdict(trade))
                
            elif hit_sl:
                trade.status = 'loss'
                trade.exit_price = trade.stop_loss
                trade.exit_time = datetime.now().isoformat()
                
                # Calculate pips (negative for losses)
                if trade.direction in ('long', 'buy'):
                    trade.pips_result = _calculate_pips(trade.stop_loss - trade.entry_price, symbol)
                else:
                    trade.pips_result = -_calculate_pips(trade.stop_loss - trade.entry_price, symbol)
                
                trade.rr_achieved = -1.0  # Lost 1R
                
                logger.info(f"❌ SL HIT — {signal_id} | {trade.pips_result:.1f} pips")
                to_remove.append(signal_id)
                resolved.append(asdict(trade))
        
        # Move completed trades to history
        for signal_id in to_remove:
            trade = self.active_trades.pop(signal_id)
            self.history.append(asdict(trade))
        
        if to_remove:
            self._save_active_trades()
            self._save_history()
        
        return resolved
    
    def get_active_count(self) -> int:
        """Number of trades currently being monitored."""
        return sum(1 for t in self.active_trades.values() if t.status == 'active')
    
    def get_performance_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get performance statistics."""
        # Filter recent trades
        cutoff = datetime.now().timestamp() - (days * 86400)
        recent = [t for t in self.history if datetime.fromisoformat(t['entry_time']).timestamp() > cutoff]
        
        if not recent:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0.0,
                'total_pips': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'by_pair': {},
                'by_setup': {}
            }
        
        wins = [t for t in recent if t['status'] == 'win']
        losses = [t for t in recent if t['status'] == 'loss']
        
        total_pips = sum(t.get('pips_result', 0) for t in recent)
        win_pips = sum(t.get('pips_result', 0) for t in wins)
        loss_pips = abs(sum(t.get('pips_result', 0) for t in losses))
        
        # By pair
        by_pair = {}
        for symbol in set(t['symbol'] for t in recent):
            pair_trades = [t for t in recent if t['symbol'] == symbol]
            pair_wins = [t for t in pair_trades if t['status'] == 'win']
            by_pair[symbol] = {
                'trades': len(pair_trades),
                'wins': len(pair_wins),
                'win_rate': len(pair_wins) / len(pair_trades) * 100 if pair_trades else 0,
                'pips': sum(t.get('pips_result', 0) for t in pair_trades)
            }
        
        # By setup
        by_setup = {}
        for setup in set(t['setup_type'] for t in recent):
            setup_trades = [t for t in recent if t['setup_type'] == setup]
            setup_wins = [t for t in setup_trades if t['status'] == 'win']
            by_setup[setup] = {
                'trades': len(setup_trades),
                'wins': len(setup_wins),
                'win_rate': len(setup_wins) / len(setup_trades) * 100 if setup_trades else 0
            }
        
        return {
            'total_trades': len(recent),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / len(recent) * 100 if recent else 0,
            'total_pips': total_pips,
            'avg_win': win_pips / len(wins) if wins else 0,
            'avg_loss': loss_pips / len(losses) if losses else 0,
            'profit_factor': win_pips / loss_pips if loss_pips > 0 else 0,
            'by_pair': by_pair,
            'by_setup': by_setup
        }


# Singleton
_tracker: Optional[TradeTracker] = None

def get_trade_tracker() -> TradeTracker:
    """Get trade tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = TradeTracker()
    return _tracker
