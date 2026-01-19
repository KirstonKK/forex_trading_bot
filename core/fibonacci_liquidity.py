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
    def detect_equal_highs_lows(candles: List[dict], tolerance: float = 0.0005) -> Dict[str, List[float]]:
        """
        Detect equal highs and equal lows (liquidity pools).
        
        Args:
            candles: Price candles
            tolerance: Price similarity tolerance (0.05% default)
            
        Returns:
            Dictionary with 'equal_highs' and 'equal_lows' lists
        """
        if len(candles) < 10:
            return {'equal_highs': [], 'equal_lows': []}
        
        recent = candles[-20:]
        
        # Find swing highs (local maxima)
        swing_highs = []
        for i in range(2, len(recent) - 2):
            if (recent[i]['high'] > recent[i-1]['high'] and 
                recent[i]['high'] > recent[i-2]['high'] and
                recent[i]['high'] > recent[i+1]['high']):
                swing_highs.append(recent[i]['high'])
        
        # Find swing lows (local minima)
        swing_lows = []
        for i in range(2, len(recent) - 2):
            if (recent[i]['low'] < recent[i-1]['low'] and 
                recent[i]['low'] < recent[i-2]['low'] and
                recent[i]['low'] < recent[i+1]['low']):
                swing_lows.append(recent[i]['low'])
        
        # Group equal highs
        equal_highs = []
        for i in range(len(swing_highs)):
            for j in range(i + 1, len(swing_highs)):
                if abs(swing_highs[i] - swing_highs[j]) / swing_highs[i] <= tolerance:
                    equal_highs.append(swing_highs[i])
                    break
        
        # Group equal lows
        equal_lows = []
        for i in range(len(swing_lows)):
            for j in range(i + 1, len(swing_lows)):
                if abs(swing_lows[i] - swing_lows[j]) / swing_lows[i] <= tolerance:
                    equal_lows.append(swing_lows[i])
                    break
        
        return {
            'equal_highs': equal_highs,
            'equal_lows': equal_lows
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
