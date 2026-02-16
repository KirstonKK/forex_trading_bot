"""
Smart Money Concepts (SMC) Strategy
Implements BOS (Break of Structure) + Pullback + Entry strategies.
Uses Enhanced SMC Strategy with multi-timeframe analysis.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from enum import Enum
import numpy as np

# Import enhanced strategy
try:
    from core.legacy.enhanced_smc_strategy import EnhancedSMCStrategy
    USE_ENHANCED = True
except ImportError:
    USE_ENHANCED = False


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

    def _create_bos(self, timestamp: int, price: float, structure_type: StructureType,
                    strength: float, reference_level: float) -> BreakOfStructure:
        """Create a BreakOfStructure object."""
        bos = BreakOfStructure(
            timestamp=timestamp,
            price=price,
            structure_type=structure_type,
            strength=min(strength, 1.0)
        )
        if structure_type == StructureType.HIGHER_HIGH:
            bos.higher_low = reference_level
        else:
            bos.lower_high = reference_level
        return bos

    def detect_break_of_structure(self, candles: List[dict]) -> Optional[BreakOfStructure]:
        """Detect break of structure (BOS)."""
        if len(candles) < 10:
            return None
        
        recent = candles[-20:]
        current_price = candles[-1]['close']
        structure_candles = recent[-15:]
        
        max_high = max(c['high'] for c in structure_candles[:-2])
        min_low = min(c['low'] for c in structure_candles[:-2])
        
        # BOS above (bullish)
        if current_price > max_high * 1.0007:
            recent_low = min(c['low'] for c in recent[-5:])
            strength = min((current_price - max_high) / (max_high * 0.007), 1.0)
            return self._create_bos(candles[-1]['timestamp'], current_price,
                                    StructureType.HIGHER_HIGH, strength, recent_low)
        
        # BOS below (bearish)
        if current_price < min_low * 0.9993:
            recent_high = max(c['high'] for c in recent[-5:])
            strength = min((min_low - current_price) / (min_low * 0.007), 1.0)
            return self._create_bos(candles[-1]['timestamp'], current_price,
                                    StructureType.LOWER_LOW, strength, recent_high)
        
        return None

    def _calculate_pullback_confidence(self, distance: float, pullback_range: float) -> Optional[float]:
        """Calculate pullback zone confidence based on distance ratio."""
        ratio = distance / pullback_range
        if 0.2 <= ratio <= 0.6:
            return 0.85
        if 0.1 <= ratio <= 0.7:
            return 0.7
        return None

    def detect_pullback(self, candles: List[dict], bos: BreakOfStructure) -> Optional[PullbackZone]:
        """Detect pullback zone after BOS."""
        if len(candles) < 10:
            return None
        
        recent = candles[-8:]
        current_price = candles[-1]['close']
        high = max(c['high'] for c in recent)
        low = min(c['low'] for c in recent)
        pullback_range = high - low
        
        # Require meaningful pullback (at least 0.15% of price)
        if pullback_range < current_price * 0.0015:
            return None
        
        # Calculate distance based on structure type
        if bos.structure_type == StructureType.HIGHER_HIGH:
            distance = current_price - low
        elif bos.structure_type == StructureType.LOWER_LOW:
            distance = high - current_price
        else:
            return None
        
        confidence = self._calculate_pullback_confidence(distance, pullback_range)
        if not confidence:
            return None
        
        return PullbackZone(
            timestamp=candles[-1]['timestamp'],
            entry_price=current_price,
            zone_high=high,
            zone_low=low,
            confidence=confidence
        )

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

    def _find_entry_zone(self, candles: List[dict]) -> Optional[Tuple[float, float, EntryZoneType]]:
        """Find the best entry zone from FVG, order block, or discount zone."""
        # Check FVG first (highest priority)
        fvg = self.identify_fair_value_gap(candles)
        if fvg:
            return fvg
        
        # Check order block
        ob = self.identify_order_block(candles)
        if ob:
            return (ob[0], ob[1], EntryZoneType.ORDER_BLOCK)
        
        # Check discount zone
        discount = self.identify_discount_zone(candles)
        if discount:
            return (discount[0], discount[1], EntryZoneType.DISCOUNT_ZONE)
        
        return None
    
    def _calculate_sl_tp(self, current_price: float, entry_low: float, entry_high: float,
                         is_long: bool, rr_multiplier: float = 2.0) -> Tuple[float, float, float]:
        """Calculate stop loss, take profit, and RR ratio."""
        if is_long:
            stop_loss = entry_low * 0.998
            risk = current_price - stop_loss
            target_price = current_price + risk * rr_multiplier
        else:
            stop_loss = entry_high * 1.002
            risk = stop_loss - current_price
            target_price = current_price - risk * rr_multiplier
        
        risk = abs(current_price - stop_loss)
        reward = abs(target_price - current_price)
        rr_ratio = reward / risk if risk > 0 else 0
        
        return stop_loss, target_price, rr_ratio

    def generate_entry_signal(self, candles: List[dict]) -> Optional[SMCEntrySignal]:
        """Generate complete entry signal based on SMC strategy."""
        if len(candles) < 20:
            return None
        
        # Step 1: Detect BOS
        bos = self.detect_break_of_structure(candles)
        if not bos:
            return None
        
        # Step 2: Validate pullback
        recent = candles[-5:]
        high, low = max(c['high'] for c in recent), min(c['low'] for c in recent)
        if (high - low) < candles[-1]['close'] * 0.0002:
            return None
        
        pullback = PullbackZone(
            timestamp=candles[-1]['timestamp'],
            entry_price=candles[-1]['close'],
            zone_high=high, zone_low=low, confidence=0.75
        )
        
        # Step 3: Find entry zone
        entry_zone = self._find_entry_zone(candles)
        if not entry_zone:
            return None
        entry_low, entry_high, entry_zone_type = entry_zone
        
        # Step 4: Calculate SL/TP
        is_long = bos.structure_type == StructureType.HIGHER_HIGH
        current_price = candles[-1]['close']
        stop_loss, target_price, rr_ratio = self._calculate_sl_tp(
            current_price, entry_low, entry_high, is_long
        )
        
        # Validate minimum RR and signal strength
        if rr_ratio < 1.5:
            return None
        
        strength = min(bos.strength * 0.6 + pullback.confidence * 0.4, 1.0)
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


class SMCStrategy:
    """
    Main SMC Strategy class.
    Uses enhanced strategy if available, falls back to basic strategy.
    """
    
    def __init__(self, symbol: str = "EURUSD"):
        self.symbol = symbol
        if USE_ENHANCED:
            self.enhanced = EnhancedSMCStrategy(symbol)
            self.analyzer = None
        else:
            self.analyzer = SMCAnalyzer()
            self.enhanced = None
    
    def analyze(self, candles: List[dict]) -> Optional[Dict]:
        """
        Analyze candles and return trading signal.
        
        Args:
            candles: List of candlestick data
            
        Returns:
            Signal dict with entry, SL, TP if signal found, else None
        """
        # Use enhanced strategy if available
        if self.enhanced:
            return self.enhanced.analyze(candles)
        
        # Fall back to basic strategy
        signal = self.analyzer.analyze(candles)
        if signal is None:
            return None
        
        # Convert SMCEntrySignal to dict format
        direction = "BUY" if signal.bos.structure_type == StructureType.HIGHER_HIGH else "SELL"
        
        return {
            'direction': direction,
            'entry_price': signal.entry_price,
            'stop_loss': signal.stop_loss,
            'take_profit': signal.target_price,
            'confidence': signal.strength,
            'risk_reward': signal.risk_reward_ratio
        }
