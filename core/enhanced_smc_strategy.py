"""
Enhanced SMC Strategy - Based on Specific Trading Plan
Implements ICT methodology with multi-timeframe analysis, order blocks, FVG, liquidity sweeps, and BoS/ChoCH confirmation.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from enum import Enum
import numpy as np
from datetime import datetime, time as dt_time


class MarketStructure(Enum):
    """Market structure states."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"


class SessionType(Enum):
    """Trading session types."""
    ASIAN = "asian"
    LONDON = "london"
    NY = "ny"
    OVERLAP = "overlap"


@dataclass
class OrderBlock:
    """Order Block zone."""
    high: float
    low: float
    timestamp: int
    timeframe: str
    strength: float  # 0-1


@dataclass
class FairValueGap:
    """Fair Value Gap."""
    high: float
    low: float
    timestamp: int
    filled: bool = False


@dataclass
class LiquidityPool:
    """Equal highs/lows liquidity pool."""
    level: float
    is_high: bool  # True for equal highs, False for equal lows
    swept: bool = False
    count: int = 2  # Number of touches


@dataclass
class TradingSignal:
    """Complete trading signal."""
    direction: str  # "BUY" or "SELL"
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    confidence: float  # 0-1
    order_block: OrderBlock
    htf_structure: MarketStructure
    session: SessionType
    conditions_met: List[str]  # List of conditions that passed
    timestamp: int


class EnhancedSMCStrategy:
    """
    Enhanced SMC Strategy implementing the specific trading plan:
    - HTF structure (4H/1H) for trend
    - 5M order blocks aligned with HTF zones
    - 79% Fibonacci confluence
    - FVG and breaker blocks
    - BoS + ChoCH confirmation
    - Liquidity sweeps (equal highs/lows)
    - Pair-specific rules (EU/GU vs XAUUSD)
    """
    
    def __init__(self, symbol: str = "EURUSD"):
        self.symbol = symbol
        self.is_gold = symbol == "XAUUSD"
        self.trades_today = 0
        self.target_reached = False
        self.max_trades_per_day = 2
        
    def determine_htf_structure(self, htf_candles: List[dict]) -> MarketStructure:
        """
        Determine higher timeframe structure (4H or 1H).
        Returns: BULLISH, BEARISH, or RANGING
        """
        if len(htf_candles) < 20:
            return MarketStructure.RANGING
        
        # Look at last 20 candles
        recent = htf_candles[-20:]
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        closes = [c['close'] for c in recent]
        
        # Calculate trend
        recent_high = max(highs[-10:])
        recent_low = min(lows[-10:])
        prev_high = max(highs[-20:-10])
        prev_low = min(lows[-20:-10])
        
        # Simple moving average trend
        sma_20 = sum(closes[-20:]) / 20
        current_price = closes[-1]
        
        # Bullish: Higher highs and higher lows
        if recent_high > prev_high and recent_low > prev_low and current_price > sma_20:
            return MarketStructure.BULLISH
        
        # Bearish: Lower highs and lower lows
        if recent_high < prev_high and recent_low < prev_low and current_price < sma_20:
            return MarketStructure.BEARISH
        
        return MarketStructure.RANGING
    
    def find_order_blocks_5m(self, candles_5m: List[dict], htf_structure: MarketStructure) -> List[OrderBlock]:
        """
        Find order blocks on 5-minute timeframe that align with HTF structure.
        Order block = last bearish candle before bullish move (or vice versa).
        """
        order_blocks = []
        
        if len(candles_5m) < 10:
            return order_blocks
        
        # Look for order blocks in last 50 candles
        for i in range(len(candles_5m) - 10, len(candles_5m) - 3):
            if i < 2:
                continue
            
            curr = candles_5m[i]
            next_candles = candles_5m[i+1:i+4]
            
            # Bullish order block (for long entries)
            if htf_structure == MarketStructure.BULLISH:
                # Last bearish candle before strong bullish move
                is_bearish = curr['close'] < curr['open']
                next_bullish = sum(1 for c in next_candles if c['close'] > c['open']) >= 2
                
                if is_bearish and next_bullish:
                    ob = OrderBlock(
                        high=curr['high'],
                        low=curr['low'],
                        timestamp=curr.get('time', curr.get('timestamp', 0)),
                        timeframe="5M",
                        strength=0.8
                    )
                    order_blocks.append(ob)
            
            # Bearish order block (for short entries)
            elif htf_structure == MarketStructure.BEARISH:
                # Last bullish candle before strong bearish move
                is_bullish = curr['close'] > curr['open']
                next_bearish = sum(1 for c in next_candles if c['close'] < c['open']) >= 2
                
                if is_bullish and next_bearish:
                    ob = OrderBlock(
                        high=curr['high'],
                        low=curr['low'],
                        timestamp=curr.get('time', curr.get('timestamp', 0)),
                        timeframe="5M",
                        strength=0.8
                    )
                    order_blocks.append(ob)
        
        return order_blocks
    
    def calculate_fib_retracement(self, swing_high: float, swing_low: float) -> Dict[str, float]:
        """Calculate Fibonacci retracement levels."""
        diff = swing_high - swing_low
        return {
            '0%': swing_high,
            '23.6%': swing_high - (diff * 0.236),
            '38.2%': swing_high - (diff * 0.382),
            '50%': swing_high - (diff * 0.5),
            '61.8%': swing_high - (diff * 0.618),
            '79%': swing_high - (diff * 0.79),  # Key level for confluence
            '100%': swing_low
        }
    
    def check_79_fib_confluence(self, order_block: OrderBlock, candles: List[dict]) -> bool:
        """
        Check if order block aligns with 79% Fibonacci retracement.
        """
        if len(candles) < 20:
            return False
        
        recent = candles[-20:]
        swing_high = max(c['high'] for c in recent)
        swing_low = min(c['low'] for c in recent)
        
        fib_levels = self.calculate_fib_retracement(swing_high, swing_low)
        fib_79 = fib_levels['79%']
        
        # Check if order block overlaps with 79% level (within 0.2%)
        ob_mid = (order_block.high + order_block.low) / 2
        tolerance = ob_mid * 0.002
        
        return abs(ob_mid - fib_79) < tolerance
    
    def detect_fair_value_gaps(self, candles: List[dict]) -> List[FairValueGap]:
        """Detect Fair Value Gaps (FVG) - 3-candle imbalances."""
        fvgs = []
        
        for i in range(len(candles) - 3, max(0, len(candles) - 20), -1):
            if i < 2:
                break
            
            candle_1 = candles[i]
            candle_2 = candles[i + 1]
            candle_3 = candles[i + 2]
            
            # Bullish FVG: gap between candle 1 high and candle 3 low
            if candle_1['high'] < candle_3['low']:
                fvg = FairValueGap(
                    high=candle_3['low'],
                    low=candle_1['high'],
                    timestamp=candle_2.get('time', candle_2.get('timestamp', 0))
                )
                fvgs.append(fvg)
            
            # Bearish FVG: gap between candle 3 high and candle 1 low
            elif candle_3['high'] < candle_1['low']:
                fvg = FairValueGap(
                    high=candle_1['low'],
                    low=candle_3['high'],
                    timestamp=candle_2.get('time', candle_2.get('timestamp', 0))
                )
                fvgs.append(fvg)
        
        return fvgs
    
    def detect_liquidity_pools(self, candles: List[dict]) -> List[LiquidityPool]:
        """
        Detect equal highs and equal lows (liquidity pools).
        """
        liquidity_pools = []
        
        if len(candles) < 10:
            return liquidity_pools
        
        # Look at last 20 candles
        recent = candles[-20:]
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        
        # Find equal highs (within 0.1% tolerance)
        for i in range(len(highs) - 1):
            for j in range(i + 1, min(i + 5, len(highs))):
                if abs(highs[i] - highs[j]) / highs[i] < 0.001:
                    pool = LiquidityPool(
                        level=highs[i],
                        is_high=True,
                        count=2
                    )
                    liquidity_pools.append(pool)
                    break
        
        # Find equal lows (within 0.1% tolerance)
        for i in range(len(lows) - 1):
            for j in range(i + 1, min(i + 5, len(lows))):
                if abs(lows[i] - lows[j]) / lows[i] < 0.001:
                    pool = LiquidityPool(
                        level=lows[i],
                        is_high=False,
                        count=2
                    )
                    liquidity_pools.append(pool)
                    break
        
        return liquidity_pools
    
    def check_bos_and_choch(self, candles: List[dict], htf_structure: MarketStructure) -> Tuple[bool, bool]:
        """
        Check for Break of Structure (BoS) and Change of Character (ChoCH).
        Returns: (has_bos, has_choch)
        """
        if len(candles) < 15:
            return False, False
        
        recent = candles[-15:]
        current_price = candles[-1]['close']
        
        # For bullish structure
        if htf_structure == MarketStructure.BULLISH:
            # BoS: break above previous high
            prev_highs = [c['high'] for c in recent[-10:-2]]
            prev_high = max(prev_highs) if prev_highs else 0
            has_bos = current_price > prev_high * 1.001
            
            # ChoCH: price creates higher low after pullback
            recent_lows = [c['low'] for c in recent[-5:]]
            prev_lows = [c['low'] for c in recent[-10:-5]]
            has_choch = min(recent_lows) > min(prev_lows) if prev_lows and recent_lows else False
            
            return has_bos, has_choch
        
        # For bearish structure
        elif htf_structure == MarketStructure.BEARISH:
            # BoS: break below previous low
            prev_lows = [c['low'] for c in recent[-10:-2]]
            prev_low = min(prev_lows) if prev_lows else float('inf')
            has_bos = current_price < prev_low * 0.999
            
            # ChoCH: price creates lower high after pullback
            recent_highs = [c['high'] for c in recent[-5:]]
            prev_highs = [c['high'] for c in recent[-10:-5]]
            has_choch = max(recent_highs) < max(prev_highs) if prev_highs and recent_highs else False
            
            return has_bos, has_choch
        
        return False, False
    
    def check_asian_session_sweep(self, candles: List[dict], htf_structure: MarketStructure) -> bool:
        """
        For EU/GU: Check if price swept Asian session high/low.
        Asian session: typically 00:00-08:00 UTC
        """
        if self.is_gold:
            return True  # Not required for gold
        
        # This would require session data - for now, we'll use a simplified check
        # Look for a recent sweep in last 10 candles
        if len(candles) < 10:
            return False
        
        recent = candles[-10:]
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        
        # Simple sweep detection: sharp move that reversed
        if htf_structure == MarketStructure.BULLISH:
            # Look for low sweep followed by rally
            min_low = min(lows[:-2])
            current = candles[-1]['close']
            return current > min_low * 1.002
        
        elif htf_structure == MarketStructure.BEARISH:
            # Look for high sweep followed by decline
            max_high = max(highs[:-2])
            current = candles[-1]['close']
            return current < max_high * 0.998
        
        return False
    
    def generate_signal(
        self,
        candles_5m: List[dict],
        candles_htf: List[dict]
    ) -> Optional[TradingSignal]:
        """
        Generate trading signal based on the complete trading plan.
        
        Steps:
        1. HTF structure (4H/1H)
        2. Find 5M order blocks aligned with HTF
        3. Check 79% Fib confluence
        4. Detect FVG and breaker blocks
        5. Confirm BoS + ChoCH
        6. Check liquidity sweeps
        7. Pair-specific rules
        8. If all conditions met → Generate signal
        """
        conditions_met = []
        
        # Check if we can trade today
        if self.trades_today >= self.max_trades_per_day or self.target_reached:
            return None
        
        # Step 1: HTF Structure
        htf_structure = self.determine_htf_structure(candles_htf)
        if htf_structure == MarketStructure.RANGING:
            return None  # No trade in ranging market
        conditions_met.append(f"HTF Structure: {htf_structure.value}")
        
        # Step 2: Find 5M Order Blocks
        order_blocks = self.find_order_blocks_5m(candles_5m, htf_structure)
        if not order_blocks:
            return None
        selected_ob = order_blocks[-1]  # Use most recent
        conditions_met.append("Order Block found on 5M")
        
        # Step 3: 79% Fib Confluence
        fib_confluence = self.check_79_fib_confluence(selected_ob, candles_5m)
        if not fib_confluence:
            return None
        conditions_met.append("79% Fib confluence confirmed")
        
        # Step 4: FVG Detection
        fvgs = self.detect_fair_value_gaps(candles_5m)
        if fvgs:
            conditions_met.append(f"FVG detected ({len(fvgs)} gaps)")
        
        # Step 5: BoS + ChoCH Confirmation
        has_bos, has_choch = self.check_bos_and_choch(candles_5m, htf_structure)
        if not has_bos:
            return None
        conditions_met.append("Break of Structure confirmed")
        if has_choch:
            conditions_met.append("Change of Character confirmed")
        
        # Step 6: Liquidity Check
        liquidity_pools = self.detect_liquidity_pools(candles_5m)
        if liquidity_pools:
            # Wait for sweep if liquidity exists
            current_price = candles_5m[-1]['close']
            swept = False
            for pool in liquidity_pools:
                if pool.is_high and current_price > pool.level:
                    swept = True
                elif not pool.is_high and current_price < pool.level:
                    swept = True
            
            if not swept:
                return None  # Wait for sweep
            conditions_met.append("Liquidity swept")
        
        # Step 7: Pair-Specific Rules
        if not self.is_gold:
            # EU/GU: Check Asian session sweep
            asian_sweep = self.check_asian_session_sweep(candles_5m, htf_structure)
            if not asian_sweep:
                return None
            conditions_met.append("Asian session sweep detected")
        else:
            # Gold: Use 30M zones (would need 30M data - simplified here)
            conditions_met.append("Gold: Following trend")
        
        # Step 8: Generate Signal
        current_price = candles_5m[-1]['close']
        
        if htf_structure == MarketStructure.BULLISH:
            direction = "BUY"
            entry_price = current_price
            stop_loss = selected_ob.low * 0.9995  # Below OB
            
            # Calculate SL distance in points (for forex, 1 point = 0.0001)
            sl_distance = abs(entry_price - stop_loss)
            sl_points = sl_distance / 0.0001
            
            # Ensure SL is between 50-120 points
            if sl_points < 50 or sl_points > 120:
                return None
            
            # Target: 1:3 to 1:5 RR
            rr_ratio = 4.0  # Aim for 1:4
            take_profit = entry_price + (sl_distance * rr_ratio)
            
        else:  # BEARISH
            direction = "SELL"
            entry_price = current_price
            stop_loss = selected_ob.high * 1.0005  # Above OB
            
            sl_distance = abs(stop_loss - entry_price)
            sl_points = sl_distance / 0.0001
            
            if sl_points < 50 or sl_points > 120:
                return None
            
            rr_ratio = 4.0
            take_profit = entry_price - (sl_distance * rr_ratio)
        
        # Calculate confidence
        confidence = len(conditions_met) / 8.0  # Max 8 conditions
        
        signal = TradingSignal(
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=rr_ratio,
            confidence=confidence,
            order_block=selected_ob,
            htf_structure=htf_structure,
            session=SessionType.LONDON,  # Would need actual session detection
            conditions_met=conditions_met,
            timestamp=candles_5m[-1].get('time', candles_5m[-1].get('timestamp', 0))
        )
        
        return signal
    
    def analyze(self, candles_5m: List[dict], candles_htf: List[dict] = None) -> Optional[Dict]:
        """
        Main analysis method compatible with existing bot infrastructure.
        Returns signal in expected format.
        """
        # If no HTF data provided, use 5M data as proxy (not ideal but works for testing)
        if candles_htf is None:
            candles_htf = candles_5m
        
        signal = self.generate_signal(candles_5m, candles_htf)
        
        if signal is None:
            return None
        
        # Convert to expected format
        return {
            'direction': signal.direction,
            'entry_price': signal.entry_price,
            'stop_loss': signal.stop_loss,
            'take_profit': signal.take_profit,
            'confidence': signal.confidence,
            'conditions': signal.conditions_met,
            'risk_reward': signal.risk_reward
        }


class SMCStrategy:
    """Wrapper class for backward compatibility."""
    
    def __init__(self, symbol: str = "EURUSD"):
        self.enhanced = EnhancedSMCStrategy(symbol)
    
    def analyze(self, candles: List[dict]) -> Optional[Dict]:
        """Analyze candles and return signal."""
        return self.enhanced.analyze(candles)
