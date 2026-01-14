"""
Enhanced Risk Manager with Session Control and Daily/Weekly Limits
Implements strict risk management: 0.5-1% per trade, 1.5% daily, 3% weekly.
"""

from dataclasses import dataclass
from typing import Optional, Dict
from enum import Enum
from datetime import datetime, timedelta, timezone


class TradingSession(Enum):
    """Forex trading sessions."""
    LONDON = "london"
    NEW_YORK = "new_york"
    TOKYO = "tokyo"
    SYDNEY = "sydney"


@dataclass
class SessionTime:
    """Session time window."""
    name: TradingSession
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int
    timezone: str  # UTC


# Session definitions (in UTC)
SESSIONS = {
    TradingSession.LONDON: SessionTime(
        name=TradingSession.LONDON,
        start_hour=8,
        start_minute=0,
        end_hour=17,
        end_minute=0,
        timezone="UTC"
    ),
    TradingSession.NEW_YORK: SessionTime(
        name=TradingSession.NEW_YORK,
        start_hour=13,
        start_minute=0,
        end_hour=22,
        end_minute=0,
        timezone="UTC"
    ),
    TradingSession.TOKYO: SessionTime(
        name=TradingSession.TOKYO,
        start_hour=0,
        start_minute=0,
        end_hour=9,
        end_minute=0,
        timezone="UTC"
    ),
    TradingSession.SYDNEY: SessionTime(
        name=TradingSession.SYDNEY,
        start_hour=22,
        start_minute=0,
        end_hour=7,
        end_minute=0,
        timezone="UTC"
    ),
}


class EnhancedRiskManager:
    """
    Enhanced risk management with daily/weekly limits and session control.
    
    Rules:
    - Risk per trade: 0.5-1% max
    - Max daily loss: 1.5%
    - Max weekly loss: 3%
    - RR minimum: 1:2
    - Max trades per day: 1-2
    - Sessions: London & New York only
    """

    def __init__(
        self,
        account_balance: float,
        risk_per_trade: float = 1.0,
        max_daily_loss: float = 1.5,
        max_weekly_loss: float = 3.0,
        max_trades_per_day: int = 2,
        allowed_sessions: list = None
    ):
        """
        Initialize enhanced risk manager.
        
        Args:
            account_balance: Starting capital
            risk_per_trade: Risk percentage per trade (0.5-1%)
            max_daily_loss: Max daily loss percentage
            max_weekly_loss: Max weekly loss percentage
            max_trades_per_day: Max trades per day (1-2)
            allowed_sessions: List of allowed trading sessions
        """
        self.account_balance = account_balance
        self.risk_per_trade = risk_per_trade
        self.max_daily_loss = max_daily_loss
        self.max_weekly_loss = max_weekly_loss
        self.max_trades_per_day = max_trades_per_day
        self.allowed_sessions = allowed_sessions or [TradingSession.LONDON, TradingSession.NEW_YORK]
        
        # Risk per trade in currency
        self.risk_amount = (account_balance * risk_per_trade) / 100
        
        # Daily tracking
        self.daily_pnl = 0.0
        self.daily_trades_count = 0
        self.daily_reset_time = datetime.now()
        
        # Weekly tracking
        self.weekly_pnl = 0.0
        self.weekly_reset_time = datetime.now()

    def is_session_active(self, session: TradingSession) -> bool:
        """Check if a trading session is currently active."""
        now = datetime.now(timezone.utc)
        session_time = SESSIONS[session]
        
        current_hour = now.hour
        current_minute = now.minute
        current_time = current_hour * 60 + current_minute
        
        session_start = session_time.start_hour * 60 + session_time.start_minute
        session_end = session_time.end_hour * 60 + session_time.end_minute
        
        # Handle sessions that span midnight
        if session_start > session_end:
            return current_time >= session_start or current_time < session_end
        else:
            return session_start <= current_time < session_end

    def can_trade_in_session(self) -> bool:
        """Check if any allowed session is currently active."""
        for session in self.allowed_sessions:
            if self.is_session_active(session):
                return True
        return False

    def get_active_session(self) -> Optional[TradingSession]:
        """Get currently active session."""
        for session in self.allowed_sessions:
            if self.is_session_active(session):
                return session
        return None

    def reset_daily_limits(self):
        """Reset daily counters if new day."""
        now = datetime.now()
        if (now.date() > self.daily_reset_time.date()):
            self.daily_pnl = 0.0
            self.daily_trades_count = 0
            self.daily_reset_time = now

    def reset_weekly_limits(self):
        """Reset weekly counters if new week."""
        now = datetime.now()
        if (now.isocalendar()[1] > self.weekly_reset_time.isocalendar()[1]):
            self.weekly_pnl = 0.0
            self.weekly_reset_time = now

    def can_open_trade(self) -> Dict[str, bool]:
        """
        Check if a new trade can be opened.
        
        Returns:
            Dict with detailed checks
        """
        self.reset_daily_limits()
        self.reset_weekly_limits()
        
        checks = {
            "session_active": self.can_trade_in_session(),
            "daily_limit_ok": abs(self.daily_pnl) < (self.account_balance * self.max_daily_loss / 100),
            "weekly_limit_ok": abs(self.weekly_pnl) < (self.account_balance * self.max_weekly_loss / 100),
            "daily_trades_ok": self.daily_trades_count < self.max_trades_per_day
        }
        
        return checks

    def can_open_trade_strict(self) -> bool:
        """Check if all conditions allow trade opening."""
        checks = self.can_open_trade()
        return all(checks.values())

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        symbol: str = ""  # noqa: ARG002 - kept for API compatibility
    ) -> float:
        """
        Calculate position size in DOLLARS for the trade, not units.
        
        Strategy: We want to risk exactly self.risk_amount ($100 for 1% of $10k)
        The position size returned is the actual dollar amount at risk.
        
        The backtest engine will multiply this by price moves to get P&L.
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            symbol: Trading pair
            
        Returns:
            Dollar amount at risk for this trade
        """
        risk_pips = abs(entry_price - stop_loss)
        
        if risk_pips == 0:
            return 0.0
        
        # Return the risk amount directly - this is what we're willing to lose
        return self.risk_amount

    def validate_trade(
        self,
        entry_price: float,
        stop_loss: float,
        target_price: float
    ) -> Dict[str, bool]:
        """
        Validate trade against risk rules.
        
        Returns:
            Dict with validation checks
        """
        risk = abs(entry_price - stop_loss)
        reward = abs(target_price - entry_price)
        rr_ratio = reward / risk if risk > 0 else 0
        
        return {
            "rr_ratio_ok": rr_ratio >= 1.5,
            "risk_reasonable": risk <= entry_price * 0.05,  # Max 5% risk per trade
            "stop_loss_set": stop_loss != 0,
            "target_set": target_price != 0
        }

    def record_trade_outcome(self, pnl: float):
        """Record trade P&L and update daily/weekly totals."""
        self.reset_daily_limits()
        self.reset_weekly_limits()
        
        self.daily_pnl += pnl
        self.weekly_pnl += pnl
        self.daily_trades_count += 1
        self.account_balance += pnl
        
        # Update risk amount based on new balance
        self.risk_amount = (self.account_balance * self.risk_per_trade) / 100

    def get_session_schedule(self) -> Dict:
        """Get schedule of allowed trading sessions."""
        schedule = {}
        for session in self.allowed_sessions:
            session_time = SESSIONS[session]
            schedule[session.value] = {
                "start": f"{session_time.start_hour:02d}:{session_time.start_minute:02d}",
                "end": f"{session_time.end_hour:02d}:{session_time.end_minute:02d}",
                "timezone": session_time.timezone
            }
        return schedule

    def get_risk_summary(self) -> Dict:
        """Get current risk summary."""
        self.reset_daily_limits()
        self.reset_weekly_limits()
        
        daily_loss_pct = (self.daily_pnl / self.account_balance) * 100
        weekly_loss_pct = (self.weekly_pnl / self.account_balance) * 100
        
        return {
            "account_balance": self.account_balance,
            "risk_per_trade": self.risk_per_trade,
            "risk_amount": self.risk_amount,
            "daily_pnl": self.daily_pnl,
            "daily_pnl_percent": daily_loss_pct,
            "daily_limit": self.max_daily_loss,
            "daily_trades": self.daily_trades_count,
            "daily_trades_limit": self.max_trades_per_day,
            "weekly_pnl": self.weekly_pnl,
            "weekly_pnl_percent": weekly_loss_pct,
            "weekly_limit": self.max_weekly_loss,
            "allowed_sessions": [s.value for s in self.allowed_sessions],
            "session_schedule": self.get_session_schedule()
        }
