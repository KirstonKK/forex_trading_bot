"""
ICT Analysis Module
Implements Inner Circle Trader (ICT) methodology for market structure analysis.
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional
from enum import Enum


class PatternType(Enum):
    ORDER_BLOCK = "order_block"
    FVG = "fair_value_gap"
    BREAKER = "breaker"
    STRUCTURE_BREAK = "structure_break"


@dataclass
class PriceLevel:
    """Represents a price level with associated data."""
    price: float
    timestamp: int
    volume: float


@dataclass
class ICTPattern:
    """Represents an identified ICT pattern."""
    pattern_type: PatternType
    entry_price: float
    stop_loss: float
    target_price: float
    ratio: float  # Risk:Reward ratio
    timestamp: int
    confirmed: bool = False


class ICTAnalyzer:
    """Analyzes market structure using ICT methodology."""

    def __init__(self, lookback_periods: int = 50):
        self.lookback_periods = lookback_periods

    def identify_order_blocks(self, candles: List[dict]) -> List[ICTPattern]:
        """
        Identify order blocks - levels where institutional orders rest.
        Order blocks are zones where price rejected and reversed.
        """
        if len(candles) < 5:
            return []

        patterns = []
        
        for i in range(2, len(candles) - 1):
            prev = candles[i - 2]
            curr = candles[i]
            next_candle = candles[i + 1]
            
            # Detect reversal - price rejected level and reversed
            if (prev['high'] < curr['high'] and 
                curr['close'] < curr['open'] and 
                next_candle['close'] < curr['close']):
                
                # Order block at current high
                pattern = ICTPattern(
                    pattern_type=PatternType.ORDER_BLOCK,
                    entry_price=curr['high'],
                    stop_loss=curr['high'] * 1.002,
                    target_price=curr['low'] * 0.98,
                    ratio=abs((curr['high'] - (curr['high'] * 0.98)) / 
                             (curr['high'] * 1.002 - curr['high'])),
                    timestamp=curr['timestamp']
                )
                patterns.append(pattern)
        
        return patterns

    def identify_fvg(self, candles: List[dict]) -> List[ICTPattern]:
        """
        Identify Fair Value Gaps (FVG) - imbalances in price action.
        """
        if len(candles) < 3:
            return []

        patterns = []
        
        for i in range(1, len(candles) - 1):
            prev = candles[i - 1]
            curr = candles[i]
            next_candle = candles[i + 1]
            
            # Bullish FVG: gap up
            if prev['high'] < next_candle['low']:
                gap_size = next_candle['low'] - prev['high']
                mid_point = (prev['high'] + next_candle['low']) / 2
                
                pattern = ICTPattern(
                    pattern_type=PatternType.FVG,
                    entry_price=mid_point,
                    stop_loss=next_candle['low'] - (gap_size * 0.5),
                    target_price=prev['high'] + (gap_size * 1.5),
                    ratio=2.0,
                    timestamp=curr['timestamp']
                )
                patterns.append(pattern)
            
            # Bearish FVG: gap down
            elif next_candle['high'] < prev['low']:
                gap_size = prev['low'] - next_candle['high']
                mid_point = (prev['low'] + next_candle['high']) / 2
                
                pattern = ICTPattern(
                    pattern_type=PatternType.FVG,
                    entry_price=mid_point,
                    stop_loss=next_candle['high'] + (gap_size * 0.5),
                    target_price=prev['low'] - (gap_size * 1.5),
                    ratio=2.0,
                    timestamp=curr['timestamp']
                )
                patterns.append(pattern)
        
        return patterns

    def detect_structure_break(self, candles: List[dict]) -> Optional[ICTPattern]:
        """
        Detect breaks of recent structure highs/lows.
        """
        if len(candles) < 20:
            return None
        
        recent = candles[-20:]
        high = max(c['high'] for c in recent)
        low = min(c['low'] for c in recent)
        current = candles[-1]
        
        # Break of structure
        if current['close'] > high and current['close'] > current['open']:
            pattern = ICTPattern(
                pattern_type=PatternType.STRUCTURE_BREAK,
                entry_price=high,
                stop_loss=low,
                target_price=high + (high - low) * 1.5,
                ratio=(high - low * 1.5) / (high - low),
                timestamp=current['timestamp'],
                confirmed=True
            )
            return pattern
        
        if current['close'] < low and current['close'] < current['open']:
            pattern = ICTPattern(
                pattern_type=PatternType.STRUCTURE_BREAK,
                entry_price=low,
                stop_loss=high,
                target_price=low - (high - low) * 1.5,
                ratio=(high - low * 1.5) / (high - low),
                timestamp=current['timestamp'],
                confirmed=True
            )
            return pattern
        
        return None

    def analyze(self, candles: List[dict]) -> List[ICTPattern]:
        """
        Perform complete ICT analysis on price data.
        """
        all_patterns = []
        
        # Identify all patterns
        all_patterns.extend(self.identify_order_blocks(candles))
        all_patterns.extend(self.identify_fvg(candles))
        
        structure = self.detect_structure_break(candles)
        if structure:
            all_patterns.append(structure)
        
        # Filter and confirm patterns
        return [p for p in all_patterns if p.ratio >= 1.5]
