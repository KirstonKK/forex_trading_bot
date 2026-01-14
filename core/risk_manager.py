"""
Risk Management Module
Implements 1% risk rule and position sizing.
"""

from dataclasses import dataclass
from enum import Enum


class PositionType(Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class Position:
    """Represents a trading position."""
    symbol: str
    position_type: PositionType
    entry_price: float
    stop_loss: float
    target_price: float
    position_size: float
    risk_amount: float
    reward_amount: float
    risk_reward_ratio: float


class RiskManager:
    """Manages position sizing and risk."""

    def __init__(self, account_balance: float, risk_percent: float = 1.0):
        """
        Initialize risk manager.
        
        Args:
            account_balance: Total trading capital
            risk_percent: Risk per trade as percentage (default 1%)
        """
        self.account_balance = account_balance
        self.risk_percent = risk_percent
        self.risk_per_trade = (account_balance * risk_percent) / 100

    def calculate_position_size(
        self,
        symbol: str,
        position_type: PositionType,
        entry_price: float,
        stop_loss: float,
        target_price: float
    ) -> Position:
        """
        Calculate position size based on 1% risk rule.
        
        Args:
            symbol: Trading pair (e.g., "EURUSD")
            position_type: LONG or SHORT
            entry_price: Entry price level
            stop_loss: Stop loss price
            target_price: Target price
            
        Returns:
            Position object with calculated size
        """
        # Calculate risk and reward amounts
        if position_type == PositionType.LONG:
            risk_pips = abs(entry_price - stop_loss)
            reward_pips = abs(target_price - entry_price)
        else:  # SHORT
            risk_pips = abs(stop_loss - entry_price)
            reward_pips = abs(entry_price - target_price)
        
        # Validate risk:reward ratio
        if risk_pips == 0:
            raise ValueError("Stop loss equals entry price")
        
        risk_reward_ratio = reward_pips / risk_pips
        
        # Calculate position size (assuming 1 pip = 10 units for standard pairs)
        pip_value = 10  # Standard for most forex pairs
        pip_cost = risk_pips * pip_value
        
        if pip_cost > 0:
            position_size = int(self.risk_per_trade / pip_cost)
        else:
            position_size = 0
        
        # Ensure minimum position size
        position_size = max(position_size, 1000)  # At least 0.01 lots
        
        risk_amount = position_size * risk_pips * pip_value / 100000
        reward_amount = position_size * reward_pips * pip_value / 100000
        
        return Position(
            symbol=symbol,
            position_type=position_type,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target_price,
            position_size=position_size,
            risk_amount=risk_amount,
            reward_amount=reward_amount,
            risk_reward_ratio=risk_reward_ratio
        )

    def validate_position(self, position: Position) -> bool:
        """
        Validate position meets minimum requirements.
        """
        # Minimum 1:1 risk:reward ratio
        if position.risk_reward_ratio < 1.0:
            return False
        
        # Risk cannot exceed risk per trade by more than 10%
        if position.risk_amount > self.risk_per_trade * 1.1:
            return False
        
        # Minimum position size
        if position.position_size < 1000:
            return False
        
        return True

    def update_balance(self, pnl: float):
        """Update account balance based on P&L."""
        self.account_balance += pnl
        self.risk_per_trade = (self.account_balance * self.risk_percent) / 100
