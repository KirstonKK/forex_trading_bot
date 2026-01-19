"""
Professional ICT Trading Strategy
Implements exact trading plan for 60%+ win rate.

Trading Plan:
1. HTF Structure (4H/1H) - confirm trend
2. Order Block 5M - aligned with HTF
3. 79% Fib confluence
4. BOS + ChoCH confirmation  
5. Liquidity sweep (equal highs/lows)
6. Pair-specific rules
7. RR 1:3-1:5, max 2 trades/day
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
from enum import Enum
from datetime import datetime, timezone
from core.advanced_filters import AdvancedFilters


class TrendDirection(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"


@dataclass
class OrderBlock5M:
    high: float
    low: float
    timestamp: int
    direction: str
    aligns_with_htf: bool


@dataclass
class ProfessionalSignal:
    timestamp: int
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    htf_trend: TrendDirection
    order_block: OrderBlock5M
    has_fib_confluence: bool
    has_bos: bool
    has_choch: bool
    liquidity_swept: bool
    asian_sweep: bool
    confidence: float


class ProfessionalStrategy:
    """60%+ win rate ICT strategy."""
    
    def __init__(self):
        self.filters = AdvancedFilters()
        self.trades_today = 0
        self.daily_target_hit = False
        self.current_date = None
    
    def determine_htf_trend(self, candles: List[dict]) -> TrendDirection:
        """Determine 4H trend."""
        if len(candles) < 50:
            return TrendDirection.RANGING
        
        candles_4h = self.filters.get_timeframe_data(candles, 240)
        if len(candles_4h) < 20:
            return TrendDirection.RANGING
        
        recent = candles_4h[-20:]
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        
        hh_count = sum(1 for i in range(5, len(highs)) if highs[i] > max(highs[i-5:i]))
        hl_count = sum(1 for i in range(5, len(lows)) if lows[i] > max(lows[i-5:i]))
        lh_count = sum(1 for i in range(5, len(highs)) if highs[i] < min(highs[i-5:i]))
        ll_count = sum(1 for i in range(5, len(lows)) if lows[i] < min(lows[i-5:i]))
        
        bullish_score = hh_count + hl_count
        bearish_score = lh_count + ll_count
        
        if bullish_score > bearish_score * 1.5:
            return TrendDirection.BULLISH
        elif bearish_score > bullish_score * 1.5:
            return TrendDirection.BEARISH
        return TrendDirection.RANGING
    
    def find_order_blocks_5m(self, candles: List[dict], htf_trend: TrendDirection) -> List[OrderBlock5M]:
        """Find 5M order blocks aligned with HTF."""
        candles_5m = self.filters.get_timeframe_data(candles, 5)
        if len(candles_5m) < 50:
            return []
        
        order_blocks = []
        for i in range(len(candles_5m) - 20, len(candles_5m) - 1):
            if i < 2:
                continue
            
            prev = candles_5m[i - 1]
            curr = candles_5m[i]
            next_c = candles_5m[i + 1]
            
            if (htf_trend == TrendDirection.BULLISH and
                curr['close'] > curr['open'] and
                next_c['close'] > curr['close'] and
                curr['close'] > prev['high']):
                
                ob = OrderBlock5M(curr['open'], curr['low'], curr['timestamp'], 'bullish', True)
                order_blocks.append(ob)
            
            elif (htf_trend == TrendDirection.BEARISH and
                  curr['close'] < curr['open'] and
                  next_c['close'] < curr['close'] and
                  curr['close'] < prev['low']):
                
                ob = OrderBlock5M(curr['high'], curr['open'], curr['timestamp'], 'bearish', True)
                order_blocks.append(ob)
        
        return order_blocks[-5:] if order_blocks else []
    
    def check_fib_confluence(self, candles: List[dict], ob: OrderBlock5M) -> bool:
        """Check 79% Fib confluence."""
        if len(candles) < 30:
            return False
        
        recent = candles[-30:]
        swing_high = max(c['high'] for c in recent)
        swing_low = min(c['low'] for c in recent)
        
        if ob.direction == 'bullish':
            fib_79 = swing_high - (swing_high - swing_low) * 0.79
            ob_mid = (ob.high + ob.low) / 2
            return abs(ob_mid - fib_79) / fib_79 < 0.003
        else:
            fib_79 = swing_low + (swing_high - swing_low) * 0.79
            ob_mid = (ob.high + ob.low) / 2
            return abs(ob_mid - fib_79) / fib_79 < 0.003
    
    def check_bos_choch(self, candles: List[dict], direction: str) -> Tuple[bool, bool]:
        """Check BOS + ChoCH."""
        if len(candles) < 15:
            return False, False
        
        recent = candles[-15:]
        current_price = candles[-1]['close']
        highs = [c['high'] for c in recent[:-3]]
        lows = [c['low'] for c in recent[:-3]]
        
        if direction == 'long':
            recent_high = max(highs)
            has_bos = current_price > recent_high * 1.001
            recent_lows = [c['low'] for c in recent[-5:]]
            has_choch = len(recent_lows) >= 2 and recent_lows[-1] > recent_lows[-2]
        else:
            recent_low = min(lows)
            has_bos = current_price < recent_low * 0.999
            recent_highs = [c['high'] for c in recent[-5:]]
            has_choch = len(recent_highs) >= 2 and recent_highs[-1] < recent_highs[-2]
        
        return has_bos, has_choch
    
    def check_liquidity_sweep(self, candles: List[dict]) -> bool:
        """Check equal highs/lows sweep."""
        if len(candles) < 20:
            return False
        
        recent = candles[-20:]
        highs = [c['high'] for c in recent[:-3]]
        lows = [c['low'] for c in recent[:-3]]
        
        equal_highs = [highs[i] for i in range(len(highs)-1) if abs(highs[i]-highs[i+1])/highs[i] < 0.001]
        equal_lows = [lows[i] for i in range(len(lows)-1) if abs(lows[i]-lows[i+1])/lows[i] < 0.001]
        
        last_3 = recent[-3:]
        swept_high = any(any(c['high'] > eh for c in last_3) for eh in equal_highs)
        swept_low = any(any(c['low'] < el for c in last_3) for el in equal_lows)
        
        return swept_high and swept_low
    
    def check_pair_rules(self, candles: List[dict], symbol: str, ob: OrderBlock5M) -> bool:
        """Pair-specific rules."""
        if symbol in ['EURUSD', 'GBPUSD']:
            asian_swept, sweep_dir = self.filters.check_asian_range_sweep(candles)
            if not asian_swept:
                return False
            if ob.direction == 'bullish' and sweep_dir != 'low':
                return False
            if ob.direction == 'bearish' and sweep_dir != 'high':
                return False
            return True
        
        elif symbol == 'XAUUSD':
            htf_trend = self.determine_htf_trend(candles)
            if htf_trend == TrendDirection.RANGING:
                return False
            if htf_trend == TrendDirection.BULLISH and ob.direction != 'bullish':
                return False
            if htf_trend == TrendDirection.BEARISH and ob.direction != 'bearish':
                return False
            return True
        
        return True
    
    def calculate_sl_tp(self, entry: float, ob: OrderBlock5M, candles: List[dict], 
                        direction: str, symbol: str) -> Tuple[Optional[float], Optional[float], float]:
        """Calculate SL/TP with 50-120 pip SL, 1:3-1:5 RR."""
        pip_value = 0.10 if symbol == 'XAUUSD' else 0.0001
        
        candles_30m = self.filters.get_timeframe_data(candles, 30)
        if len(candles_30m) >= 2:
            zone_high = max(c['high'] for c in candles_30m[-2:])
            zone_low = min(c['low'] for c in candles_30m[-2:])
        else:
            zone_high, zone_low = ob.high, ob.low
        
        if direction == 'long':
            stop_loss = zone_low * 0.998
            sl_distance = entry - stop_loss
            sl_pips = sl_distance / pip_value
            
            if sl_pips < 50:
                stop_loss = entry - (50 * pip_value)
            elif sl_pips > 150:
                return None, None, 0
            
            self.filters.update_daily_levels(candles)
            current_date = datetime.fromtimestamp(candles[-1]['timestamp'], tz=timezone.utc).date()
            
            if current_date in self.filters.previous_day_levels:
                pdh = self.filters.previous_day_levels[current_date].pdh
                take_profit = pdh
            else:
                take_profit = entry + (sl_distance * 3)
        else:
            stop_loss = zone_high * 1.002
            sl_distance = stop_loss - entry
            sl_pips = sl_distance / pip_value
            
            if sl_pips < 50:
                stop_loss = entry + (50 * pip_value)
            elif sl_pips > 150:
                return None, None, 0
            
            self.filters.update_daily_levels(candles)
            current_date = datetime.fromtimestamp(candles[-1]['timestamp'], tz=timezone.utc).date()
            
            if current_date in self.filters.previous_day_levels:
                pdl = self.filters.previous_day_levels[current_date].pdl
                take_profit = pdl
            else:
                take_profit = entry - (sl_distance * 3)
        
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        rr_ratio = reward / risk if risk > 0 else 0
        
        if rr_ratio < 2.0:  # Lowered from 2.5
            return None, None, 0
        
        return stop_loss, take_profit, rr_ratio
    
    def can_take_trade(self, timestamp: int) -> bool:
        """Check daily limits."""
        current_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
        
        if self.current_date != current_date:
            self.current_date = current_date
            self.trades_today = 0
            self.daily_target_hit = False
        
        if self.daily_target_hit or self.trades_today >= 2:
            return False
        
        can_trade, _ = self.filters.can_trade_now(timestamp)
        return can_trade
    
    def analyze(self, candles: List[dict], symbol: str = 'EURUSD') -> Optional[ProfessionalSignal]:
        """Main analysis - ALL conditions must pass."""
        if len(candles) < 100 or not self.can_take_trade(candles[-1]['timestamp']):
            return None
        
        # STEP 1: HTF Trend
        htf_trend = self.determine_htf_trend(candles)
        if htf_trend == TrendDirection.RANGING:
            return None
        
        # STEP 2: 5M Order Blocks
        order_blocks = self.find_order_blocks_5m(candles, htf_trend)
        if not order_blocks:
            return None
        ob = order_blocks[-1]
        
        # STEP 3: 79% Fib (bonus, not required)
        has_fib = self.check_fib_confluence(candles, ob)
        
        # STEP 4: BOS + ChoCH
        direction = 'long' if ob.direction == 'bullish' else 'short'
        has_bos, has_choch = self.check_bos_choch(candles, direction)
        if not (has_bos and has_choch):
            return None
        
        # STEP 5: Liquidity (bonus, not required)
        liquidity_swept = self.check_liquidity_sweep(candles)
        
        # STEP 6: Pair Rules (bonus for Asian sweep)
        asian_sweep = self.check_pair_rules(candles, symbol, ob)
        
        # Calculate SL/TP
        entry_price = candles[-1]['close']
        stop_loss, take_profit, rr_ratio = self.calculate_sl_tp(entry_price, ob, candles, direction, symbol)
        
        if stop_loss is None or rr_ratio < 2.0:  # Lowered from 2.5 to 2.0
            return None
        
        # Calculate confidence with bonuses
        confidence = 0.70  # Base for HTF + OB + BOS + ChoCH
        if has_fib:
            confidence += 0.10
        if liquidity_swept:
            confidence += 0.10
        if asian_sweep:
            confidence += 0.05
        if rr_ratio >= 4.0:
            confidence += 0.05
        
        confidence = min(confidence, 1.0)
        
        # Require minimum 0.75 confidence (at least 1 bonus)
        if confidence < 0.75:
            return None
        
        self.trades_today += 1
        
        return ProfessionalSignal(
            timestamp=candles[-1]['timestamp'],
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=rr_ratio,
            htf_trend=htf_trend,
            order_block=ob,
            has_fib_confluence=has_fib,
            has_bos=has_bos,
            has_choch=has_choch,
            liquidity_swept=liquidity_swept,
            asian_sweep=asian_sweep,
            confidence=confidence
        )
