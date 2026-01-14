"""
Smart Money Concepts (SMC) Strategy
Implements BOS (Break of Structure) + Pullback + Entry strategies.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from enum import Enum
import numpy as np


class StructureType(Enum):
    """Types of market structure."""
    HIGHER_HIGH = "higher_high"
    HIGHER_LOW = "higher_low"
    LOWER_LOW = "lower_low"
    LOWER_HIGH = "lower_high"


class EntryZoneType(Enum):
    """Types of entry zones."""
    FVG = "fvg"
    DISCOUNT_ZONE = "discount_zone"
    ORDER_BLOCK = "order_block"
    EQUAL_HIGH_LOW = "equal_high_low"


@dataclass
class BreakOfStructure:
    """Represents a break of structure in price action."""
    timestamp: int
    price: float
    structure_type: StructureType
    strength: float  # 0-1, confidence of BOS
    higher_low: Optional[float] = None
    lower_high: Optional[float] = None


@dataclass
class PullbackZone:
    """Pullback zone after BOS."""
    timestamp: int
    entry_price: float
    zone_high: float
    zone_low: float
    confidence: float  # 0-1


@dataclass
class SMCEntrySignal:
    """Complete entry signal based on SMC methodology."""
    timestamp: int
    entry_price: float
    entry_zone_type: EntryZoneType
    stop_loss: float
    target_price: float
    risk_reward_ratio: float
    bos: BreakOfStructure
    pullback_zone: PullbackZone
    strength: float  # 0-1, overall signal strength


class SMCAnalyzer:
    """Analyzes price action using Smart Money Concepts."""

    def __init__(self):
        self.last_structure = None

    def detect_break_of_structure(self, candles: List[dict]) -> Optional[BreakOfStructure]:
        """
        Detect break of structure (BOS).
        
        Uptrend BOS: Price breaks above previous higher high
        Downtrend BOS: Price breaks below previous lower low
        """
        if len(candles) < 10:
            return None
        
        # Get recent 20 candles for structure analysis
        recent = candles[-20:]
        current_price = candles[-1]['close']
        
        # Identify structure in last 15 candles
        structure_candles = recent[-15:]
        s_highs = [c['high'] for c in structure_candles]
        s_lows = [c['low'] for c in structure_candles]
        
        max_high = max(s_highs[:-2])  # Exclude last 2
        min_low = min(s_lows[:-2])
        
        # Check for BOS above (relaxed to 0.07% from 0.1%)
        if current_price > max_high * 1.0007:
            # Recent higher lows
            recent_low = min([c['low'] for c in recent[-5:]])
            strength = min((current_price - max_high) / (max_high * 0.007), 1.0)
            
            return BreakOfStructure(
                timestamp=candles[-1]['timestamp'],
                price=current_price,
                structure_type=StructureType.HIGHER_HIGH,
                strength=min(strength, 1.0),
                higher_low=recent_low
            )
        
        # Check for BOS below
        if current_price < min_low * 0.9993:
            # Recent lower highs
            recent_high = max([c['high'] for c in recent[-5:]])
            strength = min((min_low - current_price) / (min_low * 0.007), 1.0)
            
            return BreakOfStructure(
                timestamp=candles[-1]['timestamp'],
                price=current_price,
                structure_type=StructureType.LOWER_LOW,
                strength=min(strength, 1.0),
                lower_high=recent_high
            )
        
        return None

    def detect_pullback(self, candles: List[dict], bos: BreakOfStructure) -> Optional[PullbackZone]:
        """
        Detect pullback zone after BOS.
        Pullback should show actual retracement, not just random movement.
        Look for pullback that retraces 25-50% of recent move.
        """
        if len(candles) < 10:
            return None
        
        recent = candles[-8:]  # Last 8 candles
        current_price = candles[-1]['close']
        
        if bos.structure_type == StructureType.HIGHER_HIGH:
            # Uptrend - pullback goes down, then consolidates
            high = max(c['high'] for c in recent)
            low = min(c['low'] for c in recent)
            pullback_range = high - low
            
            # Require meaningful pullback (at least 0.15% of price)
            min_pullback = current_price * 0.0015
            if pullback_range < min_pullback:
                return None
            
            # Check if we're near the bottom of pullback (good entry)
            # Current price should be within 20-50% of the pullback range from bottom
            distance_from_low = current_price - low
            if 0.2 * pullback_range <= distance_from_low <= 0.6 * pullback_range:
                confidence = 0.85
            elif 0.1 * pullback_range <= distance_from_low <= 0.7 * pullback_range:
                confidence = 0.7
            else:
                return None  # Not in good pullback zone
            
            return PullbackZone(
                timestamp=candles[-1]['timestamp'],
                entry_price=current_price,
                zone_high=high,
                zone_low=low,
                confidence=confidence
            )
        
        elif bos.structure_type == StructureType.LOWER_LOW:
            # Downtrend - pullback goes up, then consolidates
            high = max(c['high'] for c in recent)
            low = min(c['low'] for c in recent)
            pullback_range = high - low
            
            # Require meaningful pullback
            min_pullback = current_price * 0.0015
            if pullback_range < min_pullback:
                return None
            
            # Check if we're near the top of pullback (good entry for short)
            distance_from_high = high - current_price
            if 0.2 * pullback_range <= distance_from_high <= 0.6 * pullback_range:
                confidence = 0.85
            elif 0.1 * pullback_range <= distance_from_high <= 0.7 * pullback_range:
                confidence = 0.7
            else:
                return None  # Not in good pullback zone
            
            return PullbackZone(
                timestamp=candles[-1]['timestamp'],
                entry_price=current_price,
                zone_high=high,
                zone_low=low,
                confidence=confidence
            )
        
        return None

    def identify_fair_value_gap(self, candles: List[dict]) -> Optional[Tuple[float, float, EntryZoneType]]:
        """
        Identify Fair Value Gap (FVG) - genuine unfilled imbalance.
        Requires significant gaps (at least 0.1% of price), not noise.
        Bullish FVG: Previous candle high < Next candle low (gap up)
        """
        if len(candles) < 3:
            return None
        
        # Check last 3 candles for valid gap
        for i in range(len(candles) - 3, max(len(candles) - 5, 1), -1):  # Only check last 2 gaps
            recent = candles[i:i+3]
            if len(recent) < 3:
                continue
            
            current_price = candles[-1]['close']
            min_gap_size = current_price * 0.001  # At least 0.1% (stricter)
            
            # Bullish FVG (gap up)
            if recent[0]['high'] < recent[2]['low']:
                gap_size = recent[2]['low'] - recent[0]['high']
                if gap_size >= min_gap_size:  # Only count significant gaps
                    gap_top = recent[2]['low']
                    gap_bottom = recent[0]['high']
                    return (gap_bottom, gap_top, EntryZoneType.FVG)
            
            # Bearish FVG (gap down)
            if recent[2]['high'] < recent[0]['low']:
                gap_size = recent[0]['low'] - recent[2]['high']
                if gap_size >= min_gap_size:  # Only count significant gaps
                    gap_top = recent[0]['low']
                    gap_bottom = recent[2]['high']
                    return (gap_bottom, gap_top, EntryZoneType.FVG)
        
        return None

    def identify_discount_zone(self, candles: List[dict]) -> Optional[Tuple[float, float]]:
        """
        Identify discount zone - area where price retracted to previous support.
        For uptrends: area near the last significant swing low.
        Must be within 25-50% retracement range.
        """
        if len(candles) < 25:
            return None
        
        recent = candles[-25:]
        current_price = candles[-1]['close']
        
        # Find the last significant swing low (in last 20 candles)
        lookback = recent[-20:]
        lows = [c['low'] for c in lookback]
        highs = [c['high'] for c in lookback]
        
        # Previous swing low (support)
        previous_low = min(lows[:-5])  # Exclude last 5
        previous_high = max(highs[:-5])
        
        # Range of the move
        move_range = previous_high - previous_low
        
        # Discount zone: 25-75% retracement from high back to low
        retrace_start = previous_high - (move_range * 0.25)
        retrace_end = previous_high - (move_range * 0.75)
        
        # Only return if current price is in this zone
        if retrace_end <= current_price <= retrace_start:
            zone_bottom = retrace_end * 0.995
            zone_top = retrace_start * 1.005
            return (zone_bottom, zone_top)
        
        return None

    def identify_order_block(self, candles: List[dict]) -> Optional[Tuple[float, float]]:
        """
        Identify order block - level where price reversed sharply.
        Requires: strong reversal candle + meaningful range.
        """
        if len(candles) < 8:
            return None
        
        # Look for clear reversals in last 10 candles
        for i in range(len(candles) - 8, len(candles) - 2):
            if i < 1:
                continue
            
            prev = candles[i - 1]
            curr = candles[i]
            
            prev_range = prev['high'] - prev['low']
            curr_range = curr['high'] - curr['low']
            
            # Strong bearish reversal - order block at top
            if (prev['close'] > prev['open'] and  # Previous was bullish
                curr['close'] < curr['open'] and  # Current is bearish
                curr_range > prev_range * 0.6 and  # Current has good range
                curr['close'] < prev['close'] * 0.998):  # Closes below previous
                
                block_top = curr['high'] * 1.001
                block_bottom = prev['open']
                return (block_bottom, block_top)
            
            # Strong bullish reversal - order block at bottom
            if (prev['close'] < prev['open'] and  # Previous was bearish
                curr['close'] > curr['open'] and  # Current is bullish
                curr_range > prev_range * 0.6 and  # Current has good range
                curr['close'] > prev['close'] * 1.002):  # Closes above previous
                
                block_bottom = curr['low'] * 0.999
                block_top = prev['open']
                return (block_bottom, block_top)
        
        return None

    def generate_entry_signal(self, candles: List[dict]) -> Optional[SMCEntrySignal]:
        """
        Generate complete entry signal based on SMC strategy.
        
        Pattern: BOS → Pullback → Entry at FVG/Discount Zone/Order Block
        """
        if len(candles) < 20:
            return None
        
        # Step 1: Detect BOS
        bos = self.detect_break_of_structure(candles)
        if not bos:
            return None
        
        # Step 2: Detect pullback with proper retracement
        recent = candles[-5:]
        high = max(c['high'] for c in recent)
        low = min(c['low'] for c in recent)
        pullback_size = high - low
        
        # Pullback exists if there's volatility
        if pullback_size < candles[-1]['close'] * 0.0002:
            return None
        
        pullback = PullbackZone(
            timestamp=candles[-1]['timestamp'],
            entry_price=candles[-1]['close'],
            zone_high=high,
            zone_low=low,
            confidence=0.75
        )
        
        # Step 3: Identify entry zone
        current_price = candles[-1]['close']
        entry_zone_type = None
        entry_low = None
        entry_high = None
        
        # Check FVG first
        fvg = self.identify_fair_value_gap(candles)
        if fvg:
            entry_low, entry_high, entry_zone_type = fvg
        
        # Check order block
        if entry_zone_type is None:
            ob = self.identify_order_block(candles)
            if ob:
                entry_low, entry_high = ob
                entry_zone_type = EntryZoneType.ORDER_BLOCK
        
        # Check discount zone
        if entry_zone_type is None:
            discount = self.identify_discount_zone(candles)
            if discount:
                entry_low, entry_high = discount
                entry_zone_type = EntryZoneType.DISCOUNT_ZONE
        
        if entry_zone_type is None:
            return None
        
        # Step 4: Calculate SL and TP
        if bos.structure_type == StructureType.HIGHER_HIGH:
            # Long entry
            stop_loss = entry_low * 0.998
            # Use 2.0x RR ratio (more achievable than 2.5x, better than 1.8x)
            target_price = current_price + (current_price - stop_loss) * 2.0
        else:
            # Short entry
            stop_loss = entry_high * 1.002
            target_price = current_price - (stop_loss - current_price) * 2.0
        
        # Calculate RR ratio
        risk = abs(current_price - stop_loss)
        reward = abs(target_price - current_price)
        rr_ratio = reward / risk if risk > 0 else 0
        
        # Require minimum RR ratio of 1.5:1
        if rr_ratio < 1.5:
            return None
        
        # Overall signal strength - require stronger signals
        strength = min(bos.strength * 0.6 + pullback.confidence * 0.4, 1.0)
        
        # Filter: require signal strength of 0.65+ (high confidence)
        if strength < 0.65:
            return None
        
        return SMCEntrySignal(
            timestamp=candles[-1]['timestamp'],
            entry_price=current_price,
            entry_zone_type=entry_zone_type,
            stop_loss=stop_loss,
            target_price=target_price,
            risk_reward_ratio=rr_ratio,
            bos=bos,
            pullback_zone=pullback,
            strength=strength
        )

    def analyze(self, candles: List[dict]) -> Optional[SMCEntrySignal]:
        """Perform complete SMC analysis."""
        return self.generate_entry_signal(candles)
