"""
Fibonacci Retracement Calculator
Used for 79% retracement confluence
"""

from typing import List, Dict, Optional, Tuple


class FibonacciCalculator:
    """Calculate Fibonacci retracement levels."""
    
    # Standard Fibonacci levels
    LEVELS = {
        0.0: "0%",
        0.236: "23.6%",
        0.382: "38.2%",
        0.5: "50%",
        0.618: "61.8%",
        0.79: "79%",  # Our key level
        1.0: "100%"
    }
    
    @staticmethod
    def calculate_fib_levels(swing_high: float, swing_low: float) -> Dict[str, float]:
        """
        Calculate Fibonacci retracement levels.
        
        Args:
            swing_high: Recent swing high
            swing_low: Recent swing low
            
        Returns:
            Dictionary of fib levels
        """
        price_range = swing_high - swing_low
        
        levels = {}
        for ratio, label in FibonacciCalculator.LEVELS.items():
            level_price = swing_high - (price_range * ratio)
            levels[label] = level_price
        
        return levels
    
    @staticmethod
    def is_at_79_percent(current_price: float, swing_high: float, swing_low: float, tolerance: float = 0.002) -> bool:
        """
        Check if current price is at 79% Fibonacci level.
        
        Args:
            current_price: Current market price
            swing_high: Recent swing high
            swing_low: Recent swing low
            tolerance: Price tolerance (0.2% default)
            
        Returns:
            True if price is within tolerance of 79% level
        """
        levels = FibonacciCalculator.calculate_fib_levels(swing_high, swing_low)
        fib_79 = levels["79%"]
        
        distance = abs(current_price - fib_79) / fib_79
        return distance <= tolerance
    
    @staticmethod
    def get_swing_points(candles: List[dict], lookback: int = 50) -> Tuple[float, float]:
        """
        Identify swing high and swing low for Fibonacci calculation.
        
        Args:
            candles: Price candles
            lookback: How many candles to look back
            
        Returns:
            (swing_high, swing_low)
        """
        if len(candles) < lookback:
            lookback = len(candles)
        
        recent = candles[-lookback:]
        
        swing_high = max(c['high'] for c in recent)
        swing_low = min(c['low'] for c in recent)
        
        return swing_high, swing_low


class LiquidityAnalyzer:
    """Analyze liquidity pools (equal highs/equal lows)."""
    
    @staticmethod
    def _find_swing_points(candles: List[dict], point_type: str) -> List[float]:
        """Find swing highs or lows (local extrema)."""
        points = []
        key = 'high' if point_type == 'high' else 'low'
        compare = (lambda a, b: a > b) if point_type == 'high' else (lambda a, b: a < b)
        
        for i in range(2, len(candles) - 2):
            val = candles[i][key]
            if (compare(val, candles[i-1][key]) and 
                compare(val, candles[i-2][key]) and
                compare(val, candles[i+1][key])):
                points.append(val)
        return points
    
    @staticmethod
    def _group_equal_points(points: List[float], tolerance: float) -> List[float]:
        """Group similar price points within tolerance."""
        equal_points = []
        for i, p1 in enumerate(points):
            for p2 in points[i + 1:]:
                if abs(p1 - p2) / p1 <= tolerance:
                    equal_points.append(p1)
                    break
        return equal_points
    
    @staticmethod
    def detect_equal_highs_lows(candles: List[dict], tolerance: float = 0.0005) -> Dict[str, List[float]]:
        """Detect equal highs and equal lows (liquidity pools)."""
        if len(candles) < 10:
            return {'equal_highs': [], 'equal_lows': []}
        
        recent = candles[-20:]
        swing_highs = LiquidityAnalyzer._find_swing_points(recent, 'high')
        swing_lows = LiquidityAnalyzer._find_swing_points(recent, 'low')
        
        return {
            'equal_highs': LiquidityAnalyzer._group_equal_points(swing_highs, tolerance),
            'equal_lows': LiquidityAnalyzer._group_equal_points(swing_lows, tolerance)
        }
    
    @staticmethod
    def check_liquidity_swept(candles: List[dict], liquidity: Dict[str, List[float]]) -> Tuple[bool, str]:
        """
        Check if liquidity (equal highs/lows) has been swept.
        
        Args:
            candles: Price candles
            liquidity: Dictionary from detect_equal_highs_lows
            
        Returns:
            (swept, direction) - direction is 'both', 'high', 'low', or 'none'
        """
        if len(candles) < 3:
            return False, 'none'
        
        recent = candles[-5:]
        equal_highs = liquidity.get('equal_highs', [])
        equal_lows = liquidity.get('equal_lows', [])
        
        if not equal_highs and not equal_lows:
            return False, 'none'
        
        # Check if highs were swept
        highs_swept = False
        if equal_highs:
            highest_liquidity = max(equal_highs)
            highs_swept = any(c['high'] > highest_liquidity for c in recent)
        
        # Check if lows were swept
        lows_swept = False
        if equal_lows:
            lowest_liquidity = min(equal_lows)
            lows_swept = any(c['low'] < lowest_liquidity for c in recent)
        
        if highs_swept and lows_swept:
            return True, 'both'
        elif highs_swept:
            return True, 'high'
        elif lows_swept:
            return True, 'low'
        else:
            return False, 'none'


class ChangeOfCharacter:
    """Detect Change of Character (ChoCH) - internal structure break."""
    
    @staticmethod
    def detect_choch(candles: List[dict]) -> Optional[str]:
        """
        Detect Change of Character.
        ChoCH = Breaking internal structure (smaller swing high/low).
        
        Args:
            candles: Price candles
            
        Returns:
            'bullish', 'bearish', or None
        """
        if len(candles) < 10:
            return None
        
        recent = candles[-10:]
        
        # Find recent swing points
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        
        # Bullish ChoCH: Price breaks above recent swing high
        recent_swing_high = max(highs[:-3])  # Exclude last 3
        if recent[-1]['close'] > recent_swing_high:
            # Confirm it was previously making lower highs
            prev_highs = highs[-6:-3]
            if prev_highs and max(prev_highs) < recent_swing_high:
                return 'bullish'
        
        # Bearish ChoCH: Price breaks below recent swing low
        recent_swing_low = min(lows[:-3])
        if recent[-1]['close'] < recent_swing_low:
            # Confirm it was previously making higher lows
            prev_lows = lows[-6:-3]
            if prev_lows and min(prev_lows) > recent_swing_low:
                return 'bearish'
        
        return None
