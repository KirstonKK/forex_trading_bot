"""
Trade Executor Module
Manages trade entry, exit, and order management.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum
from datetime import datetime


class OrderStatus(Enum):
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


@dataclass
class Order:
    """Represents a single order."""
    order_id: str
    symbol: str
    order_type: OrderType
    quantity: float
    price: float
    status: OrderStatus = OrderStatus.PENDING
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    pnl: float = 0.0
    pnl_percent: float = 0.0


@dataclass
class ActiveTrade:
    """Represents an active trade with entry and exit orders."""
    trade_id: str
    symbol: str
    entry_order: Order
    stop_loss_order: Optional[Order] = None
    take_profit_order: Optional[Order] = None
    status: OrderStatus = OrderStatus.OPEN
    entry_time: datetime = field(default_factory=datetime.now)
    exit_time: Optional[datetime] = None
    pnl: float = 0.0
    pnl_percent: float = 0.0


class TradeExecutor:
    """Executes trades and manages active positions."""

    def __init__(self):
        self.active_trades: Dict[str, ActiveTrade] = {}
        self.closed_trades: List[ActiveTrade] = []
        self.order_counter = 0

    def open_trade(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        target_price: float,
        quantity: float
    ) -> ActiveTrade:
        """
        Open a new trade with entry, stop loss, and take profit.
        """
        self.order_counter += 1
        
        # Create entry order
        entry_order = Order(
            order_id=f"ENTRY_{self.order_counter}",
            symbol=symbol,
            order_type=OrderType.MARKET,
            quantity=quantity,
            price=entry_price,
            status=OrderStatus.OPEN,
            opened_at=datetime.now()
        )
        
        # Create stop loss order
        sl_order = Order(
            order_id=f"SL_{self.order_counter}",
            symbol=symbol,
            order_type=OrderType.STOP,
            quantity=quantity,
            price=stop_loss,
            status=OrderStatus.PENDING
        )
        
        # Create take profit order
        tp_order = Order(
            order_id=f"TP_{self.order_counter}",
            symbol=symbol,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=target_price,
            status=OrderStatus.PENDING
        )
        
        # Create active trade
        trade = ActiveTrade(
            trade_id=f"TRADE_{self.order_counter}",
            symbol=symbol,
            entry_order=entry_order,
            stop_loss_order=sl_order,
            take_profit_order=tp_order
        )
        
        self.active_trades[trade.trade_id] = trade
        return trade

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        reason: str = "manual"
    ) -> Optional[ActiveTrade]:
        """
        Close an active trade at specified price.
        """
        if trade_id not in self.active_trades:
            return None
        
        trade = self.active_trades[trade_id]
        quantity = trade.entry_order.quantity
        
        # Calculate P&L
        pnl = (exit_price - trade.entry_order.price) * quantity
        pnl_percent = ((exit_price - trade.entry_order.price) / 
                       trade.entry_order.price * 100)
        
        # Update trade
        trade.status = OrderStatus.CLOSED
        trade.exit_reason = reason
        trade.exit_time = datetime.now()
        trade.pnl = pnl
        trade.pnl_percent = pnl_percent
        
        # Move to closed trades
        del self.active_trades[trade_id]
        self.closed_trades.append(trade)
        
        return trade

    def hit_stop_loss(self, trade_id: str) -> Optional[ActiveTrade]:
        """Mark trade as closed due to stop loss."""
        if trade_id not in self.active_trades:
            return None
        
        trade = self.active_trades[trade_id]
        return self.close_trade(
            trade_id,
            trade.stop_loss_order.price,
            reason="stop_loss"
        )

    def hit_take_profit(self, trade_id: str) -> Optional[ActiveTrade]:
        """Mark trade as closed due to take profit."""
        if trade_id not in self.active_trades:
            return None
        
        trade = self.active_trades[trade_id]
        return self.close_trade(
            trade_id,
            trade.take_profit_order.price,
            reason="take_profit"
        )

    def get_active_trades(self) -> List[ActiveTrade]:
        """Get all active trades."""
        return list(self.active_trades.values())

    def get_trade_stats(self) -> Dict:
        """Get trading statistics."""
        if not self.closed_trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "total_pnl": 0.0
            }
        
        total = len(self.closed_trades)
        winners = [t for t in self.closed_trades if t.pnl > 0]
        losers = [t for t in self.closed_trades if t.pnl < 0]
        
        avg_win = sum(t.pnl for t in winners) / len(winners) if winners else 0
        avg_loss = sum(t.pnl for t in losers) / len(losers) if losers else 0
        total_pnl = sum(t.pnl for t in self.closed_trades)
        
        return {
            "total_trades": total,
            "winning_trades": len(winners),
            "losing_trades": len(losers),
            "win_rate": len(winners) / total * 100,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "total_pnl": total_pnl
        }
