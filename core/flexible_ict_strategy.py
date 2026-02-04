"""
Flexible ICT Trading Strategy with 3 Setup Options
Based on practical trading plan with realistic confluence requirements.

Setup Options:
1. HTF Bias + Liquidity Sweep + BoS (Safest - best for EU/GU London)
2. HTF Zone + OB + ChoCH (Reversal & Continuation - best for NY)
3. OB + FVG + Fib 79% (Precision Entry - best for clean pullbacks)

Risk Management:
- 3 confirmations = full risk
- 2 confirmations = half risk
- 1 confirmation = no trade
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
from enum import Enum
from datetime import datetime, timezone
from core.advanced_filters import AdvancedFilters

# Import news filter (with fallback if not available)
try:
    from integrations.news_filter import is_news_blackout
except ImportError:
    def is_news_blackout(symbol=None):
        return (False, None)  # No blocking if module not found


class TrendDirection(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"


class SetupType(Enum):
    OPTION_1 = "HTF_LIQUIDITY_BOS"  # HTF Bias + Liquidity + BoS
    OPTION_2 = "HTF_ZONE_OB_CHOCH"  # HTF Zone + OB + ChoCH
    OPTION_3 = "OB_FVG_FIB"         # OB + FVG + Fib 79%


@dataclass
class OrderBlock:
    high: float
    low: float
    timestamp: int
    direction: str
    timeframe: str  # '5M', '30M', '1H', '4H'
    strength: float


@dataclass
class FVG:
    """Fair Value Gap"""
    top: float
    bottom: float
    timestamp: int
    direction: str  # 'bullish' or 'bearish'


@dataclass
class HTFZone:
    """Higher Timeframe Zone (4H or 1H)"""
    high: float
    low: float
    timeframe: str
    zone_type: str  # 'supply' or 'demand'


@dataclass
class FlexibleSignal:
    timestamp: int
    symbol: str
    setup_type: SetupType
    direction: str  # 'long' or 'short'
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    risk_percentage: float  # 1.0 for full, 0.5 for half
    
    # Confirmations
    confirmations: List[str]
    confirmation_count: int
    
    # Details
    htf_trend: Optional[TrendDirection]
    order_block: Optional[OrderBlock]
    fvg: Optional[FVG]
    htf_zone: Optional[HTFZone]
    
    # Flags
    has_liquidity_sweep: bool
    has_bos: bool
    has_choch: bool
    has_fib_confluence: bool
    asian_sweep: bool
    
    confidence: float


class FlexibleICTStrategy:
    """Flexible ICT strategy with 3 setup options."""
    
    def __init__(self):
        self.filters = AdvancedFilters()
        self.trades_today = {}  # Track per symbol: {'EURUSD': 1, 'GBPUSD': 0}
        self._last_rejection_reasons = []  # Track why signals were rejected
        self._last_sweep_found = False  # Track if sweep was detected
        self._last_bos_found = False    # Track if BoS was detected
        self.current_date = None
        self.current_symbol = 'EURUSD'  # Track current symbol for pip calculations
        # Store multi-timeframe data
        self.mtf_data = {}  # {'4H': [...], '1H': [...], '15M': [...], '5M': [...]}
        
        # Correlation tracking - prevents opposite signals on correlated pairs
        self._recent_signals = {}  # {'EURUSD': {'direction': 'short', 'time': timestamp}}
        
        # Signal cooldown - prevent duplicate/similar signals
        self._last_signal_time = {}  # {'EURUSD': timestamp}
        self._signal_cooldown_minutes = 30  # 30 min minimum between signals on same pair
        
        # Session-specific settings
        self.session_settings = {
            'london': {'start': 8, 'end': 12, 'min_confidence': 0.85},
            'newyork': {'start': 13, 'end': 17, 'min_confidence': 0.90}
        }
        
        # Fixed R:R - DO NOT CHANGE (60% win rate achieved with 1:2)
        self.target_rr = 2.0  # 1:2 R:R - backtested
    
    def get_pip_value(self, symbol: str = None) -> float:
        """
        Get pip value for the symbol.
        - Forex pairs (EURUSD, GBPUSD): 0.0001 (4th decimal)
        - Gold (XAUUSD): 0.10 ($0.10 per point)
        """
        sym = symbol or self.current_symbol
        if sym in ['XAUUSD', 'XAU_USD', 'GOLD']:
            return 0.10  # Gold moves in $0.10 increments
        return 0.0001  # Standard forex pairs
    
    def get_point_value(self, symbol: str = None) -> float:
        """
        Get point value for the symbol (smaller unit for SL/TP calculations).
        - Forex pairs: 0.00001 (5th decimal)
        - Gold: 0.01 ($0.01)
        """
        sym = symbol or self.current_symbol
        if sym in ['XAUUSD', 'XAU_USD', 'GOLD']:
            return 0.01  # Gold point value
        return 0.00001  # Standard forex pairs
    
    def set_mtf_data(self, mtf_data: Dict[str, List[dict]]):
        """Set multi-timeframe data for analysis."""
        self.mtf_data = mtf_data
    
    def get_htf_candles(self, timeframe: int = 240) -> List[dict]:
        """Get HTF candles from stored MTF data."""
        tf_map = {240: '4H', 60: '1H', 15: '15M', 5: '5M'}
        tf_key = tf_map.get(timeframe, '4H')
        return self.mtf_data.get(tf_key, [])
    
    def check_correlation_conflict(self, symbol: str, direction: str, timestamp: int) -> bool:
        """
        Check if there's a conflicting signal on a correlated pair.
        EU and GBP are highly correlated - opposite signals = one is wrong.
        Returns True if conflict exists (should reject).
        """
        correlated_pairs = {
            'EURUSD': ['GBPUSD'],
            'GBPUSD': ['EURUSD']
        }
        
        related = correlated_pairs.get(symbol, [])
        current_hour = datetime.fromtimestamp(timestamp, tz=timezone.utc).hour
        
        for related_symbol in related:
            if related_symbol in self._recent_signals:
                sig = self._recent_signals[related_symbol]
                sig_hour = datetime.fromisoformat(sig['time']).hour
                
                # If signal within same hour and opposite direction
                if sig_hour == current_hour and sig['direction'] != direction:
                    return True
        
        return False
    
    def record_signal_direction(self, symbol: str, direction: str, timestamp: int = None):
        """Record signal direction for correlation checking and cooldown."""
        self._recent_signals[symbol] = {
            'direction': direction,
            'time': datetime.now(timezone.utc).isoformat()
        }
        # Record signal time for cooldown
        self._last_signal_time[symbol] = timestamp or int(datetime.now(timezone.utc).timestamp())
    
    def check_signal_cooldown(self, symbol: str, timestamp: int) -> bool:
        """
        Check if enough time has passed since last signal on this pair.
        Prevents duplicate/similar signals within cooldown period.
        
        Returns True if we can signal, False if in cooldown.
        """
        last_time = self._last_signal_time.get(symbol)
        if last_time is None:
            return True
        
        minutes_elapsed = (timestamp - last_time) / 60
        if minutes_elapsed < self._signal_cooldown_minutes:
            return False
        
        return True
    
    def check_5m_entry_trigger(self, candles: List[dict], direction: str) -> bool:
        """
        Wait for 5M micro-structure confirmation before entering.
        
        For LONG: Need 5M ChoCH (lower low followed by higher high)
        For SHORT: Need 5M ChoCH (higher high followed by lower low)
        
        This prevents entering too early before the move starts.
        """
        if len(candles) < 10:
            return False
        
        recent = candles[-10:]  # Last 10 5M candles (50 mins)
        
        if direction == 'long':
            # For longs: Look for bullish ChoCH
            # Price made a lower low, then broke above a previous high
            lows = [c['low'] for c in recent]
            highs = [c['high'] for c in recent]
            
            # Find the lowest point
            lowest_idx = lows.index(min(lows))
            
            # After lowest point, did we break a previous high?
            if lowest_idx < len(recent) - 2:  # Need at least 2 candles after
                pre_low_high = max(highs[:lowest_idx]) if lowest_idx > 0 else highs[0]
                post_low_high = max(highs[lowest_idx:])
                
                # Current price should be above the high before the sweep
                if post_low_high > pre_low_high and recent[-1]['close'] > pre_low_high:
                    return True
            return False
        
        else:  # SHORT
            # For shorts: Look for bearish ChoCH
            # Price made a higher high, then broke below a previous low
            lows = [c['low'] for c in recent]
            highs = [c['high'] for c in recent]
            
            # Find the highest point
            highest_idx = highs.index(max(highs))
            
            # After highest point, did we break a previous low?
            if highest_idx < len(recent) - 2:  # Need at least 2 candles after
                pre_high_low = min(lows[:highest_idx]) if highest_idx > 0 else lows[0]
                post_high_low = min(lows[highest_idx:])
                
                # Current price should be below the low before the sweep
                if post_high_low < pre_high_low and recent[-1]['close'] < pre_high_low:
                    return True
            return False
    
    def get_session_type(self, timestamp: int) -> str:
        """Determine current trading session."""
        hour = datetime.fromtimestamp(timestamp, tz=timezone.utc).hour
        if 8 <= hour < 12:
            return 'london'
        elif 13 <= hour < 17:
            return 'newyork'
        return 'other'
    
    def check_15m_confirmation(self, direction: str) -> bool:
        """
        Verify 15M timeframe confirms the trade direction.
        Requires 15M structure to show same bias as 5M entry.
        """
        candles_15m = self.get_htf_candles(15)
        if len(candles_15m) < 20:
            return True  # Not enough data, allow trade
        
        # Check 15M trend
        trend_15m = self.determine_htf_trend(candles_15m, 15)
        
        if direction == 'long' and trend_15m == TrendDirection.BEARISH:
            return False
        if direction == 'short' and trend_15m == TrendDirection.BULLISH:
            return False
        
        return True
    
    def determine_htf_trend(self, candles: List[dict], timeframe: int = 240) -> TrendDirection:
        """Determine HTF trend (4H or 1H) using actual HTF data."""
        # Use actual MTF data if available
        if self.mtf_data:
            candles_htf = self.get_htf_candles(timeframe)
        else:
            # Fallback to deriving from base candles
            candles_htf = self.filters.get_timeframe_data(candles, timeframe)
        
        if len(candles_htf) < 20:
            return TrendDirection.RANGING
        
        recent = candles_htf[-20:]
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        
        # Count higher highs/higher lows vs lower highs/lower lows
        hh_count = sum(1 for i in range(5, len(highs)) if highs[i] > max(highs[i-5:i]))
        hl_count = sum(1 for i in range(5, len(lows)) if lows[i] > max(lows[i-5:i]))
        lh_count = sum(1 for i in range(5, len(highs)) if highs[i] < min(highs[i-5:i]))
        ll_count = sum(1 for i in range(5, len(lows)) if lows[i] < min(lows[i-5:i]))
        
        bullish_score = hh_count + hl_count
        bearish_score = lh_count + ll_count
        
        if bullish_score > bearish_score * 1.3:
            return TrendDirection.BULLISH
        elif bearish_score > bullish_score * 1.3:
            return TrendDirection.BEARISH
        return TrendDirection.RANGING
    
    def find_htf_zones(self, candles: List[dict], timeframe: int = 240) -> List[HTFZone]:
        """Find HTF zones (4H or 1H supply/demand) using actual MTF data."""
        # Use actual MTF data if available
        if self.mtf_data:
            candles_htf = self.get_htf_candles(timeframe)
        else:
            candles_htf = self.filters.get_timeframe_data(candles, timeframe)
        
        if len(candles_htf) < 30:
            return []
        
        zones = []
        recent = candles_htf[-30:]
        
        for i in range(len(recent) - 5):
            candle = recent[i]
            
            # Supply zone (strong bearish move from here)
            if candle['close'] < candle['open']:  # Bearish candle
                next_5 = recent[i+1:i+6]
                if all(c['close'] < candle['low'] for c in next_5[:3]):
                    zones.append(HTFZone(
                        high=candle['high'],
                        low=candle['open'],
                        timeframe=f"{timeframe}M",
                        zone_type='supply'
                    ))
            
            # Demand zone (strong bullish move from here)
            elif candle['close'] > candle['open']:  # Bullish candle
                next_5 = recent[i+1:i+6]
                if all(c['close'] > candle['high'] for c in next_5[:3]):
                    zones.append(HTFZone(
                        high=candle['close'],
                        low=candle['low'],
                        timeframe=f"{timeframe}M",
                        zone_type='demand'
                    ))
        
        return zones[-5:]  # Keep last 5 zones
    
    def find_order_blocks(self, candles: List[dict], timeframe: int = 5) -> List[OrderBlock]:
        """
        Find order blocks on specified timeframe using actual MTF data.
        
        ICT Order Block Definition:
        - Bullish OB: Last BEARISH candle before a strong bullish move
        - Bearish OB: Last BULLISH candle before a strong bearish move
        """
        # Use actual MTF data if available
        if self.mtf_data:
            candles_tf = self.get_htf_candles(timeframe)
        elif timeframe == 5:
            # For 5M, just use the input candles directly (they're already 5M)
            candles_tf = candles
        else:
            candles_tf = self.filters.get_timeframe_data(candles, timeframe)
        
        if len(candles_tf) < 20:
            return []
        
        order_blocks = []
        # Look at last 30 candles
        start_idx = max(2, len(candles_tf) - 30)
        for i in range(start_idx, len(candles_tf) - 1):
            curr = candles_tf[i]
            next_c = candles_tf[i + 1]
            
            # Bullish OB: BEARISH candle followed by bullish candle that breaks above
            if (curr['close'] < curr['open'] and  # Current is bearish
                next_c['close'] > next_c['open'] and  # Next is bullish
                next_c['close'] > curr['high']):  # Next breaks above current's high
                
                strength = (next_c['close'] - curr['low']) / curr['low']
                ob = OrderBlock(
                    high=curr['high'],  # OB high is the bearish candle's high
                    low=curr['low'],     # OB low is the bearish candle's low
                    timestamp=curr['timestamp'],
                    direction='bullish',
                    timeframe=f"{timeframe}M",
                    strength=strength
                )
                order_blocks.append(ob)
            
            # Bearish OB: BULLISH candle followed by bearish candle that breaks below
            elif (curr['close'] > curr['open'] and  # Current is bullish
                  next_c['close'] < next_c['open'] and  # Next is bearish
                  next_c['close'] < curr['low']):  # Next breaks below current's low
                
                strength = (curr['high'] - next_c['close']) / next_c['close']
                ob = OrderBlock(
                    high=curr['high'],  # OB high is the bullish candle's high
                    low=curr['low'],     # OB low is the bullish candle's low
                    timestamp=curr['timestamp'],
                    direction='bearish',
                    timeframe=f"{timeframe}M",
                    strength=strength
                )
                order_blocks.append(ob)
        
        return sorted(order_blocks, key=lambda x: x.strength, reverse=True)[:5]
    
    def find_fvgs(self, candles: List[dict]) -> List[FVG]:
        """Find Fair Value Gaps on 5M using actual MTF data."""
        # Use actual MTF data if available
        if self.mtf_data:
            candles_5m = self.get_htf_candles(5)
        else:
            # Input candles are already 5M, use them directly
            candles_5m = candles
        
        if len(candles_5m) < 10:
            return []
        
        fvgs = []
        for i in range(2, len(candles_5m)):
            prev = candles_5m[i - 2]
            curr = candles_5m[i - 1]
            next_c = candles_5m[i]
            
            # Bullish FVG: gap between prev high and next low
            if prev['high'] < next_c['low']:
                fvgs.append(FVG(
                    top=next_c['low'],
                    bottom=prev['high'],
                    timestamp=curr['timestamp'],
                    direction='bullish'
                ))
            
            # Bearish FVG: gap between prev low and next high
            elif prev['low'] > next_c['high']:
                fvgs.append(FVG(
                    top=prev['low'],
                    bottom=next_c['high'],
                    timestamp=curr['timestamp'],
                    direction='bearish'
                ))
        
        return fvgs[-10:]  # Keep recent FVGs
    
    def is_in_liquidity_zone(self, candles: List[dict], current_price: float) -> bool:
        """
        Check if current price is IN a liquidity zone (EQUAL highs/lows cluster).
        We should NOT enter trades when price is sitting in liquidity - wait for sweep.
        
        This checks for EQUAL highs/lows (within 3 pips of each other), not just any highs/lows.
        
        Returns:
            True if price is at a significant liquidity pool (don't trade here)
        """
        if len(candles) < 30:
            return False
        
        recent = candles[-30:]
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        
        pip_value = self.get_pip_value()
        eq_tolerance = 3 * pip_value  # 3 pips - for finding EQUAL levels
        zone_tolerance = 5 * pip_value  # 5 pips - for price at zone
        
        # Find clusters of EQUAL highs (within 3 pips of each other)
        for i in range(len(highs) - 2):
            cluster_highs = [highs[i]]
            for j in range(i + 1, len(highs)):
                if abs(highs[j] - highs[i]) < eq_tolerance:
                    cluster_highs.append(highs[j])
            
            # If we have 3+ equal highs AND price is near them, it's a liquidity zone
            if len(cluster_highs) >= 3:
                avg_level = sum(cluster_highs) / len(cluster_highs)
                if abs(current_price - avg_level) < zone_tolerance:
                    return True
        
        # Find clusters of EQUAL lows
        for i in range(len(lows) - 2):
            cluster_lows = [lows[i]]
            for j in range(i + 1, len(lows)):
                if abs(lows[j] - lows[i]) < eq_tolerance:
                    cluster_lows.append(lows[j])
            
            if len(cluster_lows) >= 3:
                avg_level = sum(cluster_lows) / len(cluster_lows)
                if abs(current_price - avg_level) < zone_tolerance:
                    return True
        
        return False
    
    def check_liquidity_sweep(self, candles: List[dict], symbol: str) -> Tuple[bool, str]:
        """Check for liquidity sweep (equal highs/lows or Asian session)."""
        if len(candles) < 20:
            return False, None
        
        # For EU/GU: prioritize Asian range sweep
        if symbol in ['EURUSD', 'GBPUSD']:
            asian_swept, sweep_dir = self.filters.check_asian_range_sweep(candles)
            if asian_swept:
                return True, sweep_dir
        
        # Check equal highs/lows sweep
        recent = candles[-20:]
        highs = [c['high'] for c in recent[:-3]]
        lows = [c['low'] for c in recent[:-3]]
        
        # Find equal highs (within 0.1%)
        equal_highs = []
        for i in range(len(highs) - 1):
            if abs(highs[i] - highs[i+1]) / highs[i] < 0.001:
                equal_highs.append(highs[i])
        
        # Find equal lows
        equal_lows = []
        for i in range(len(lows) - 1):
            if abs(lows[i] - lows[i+1]) / lows[i] < 0.001:
                equal_lows.append(lows[i])
        
        last_3 = recent[-3:]
        
        # Check if swept high (for shorts)
        for eh in equal_highs:
            if any(c['high'] > eh for c in last_3):
                return True, 'high'
        
        # Check if swept low (for longs)
        for el in equal_lows:
            if any(c['low'] < el for c in last_3):
                return True, 'low'
        
        return False, None
    
    def check_bos(self, candles: List[dict], direction: str) -> bool:
        """
        Check Break of Structure - price has broken a swing point with DISPLACEMENT.
        
        For ICT: After liquidity sweep, we look for an IMPULSIVE BoS to confirm direction.
        The break should be a strong candle (displacement), not a weak break.
        """
        if len(candles) < 20:
            return False
        
        # Look at larger window for BoS confirmation
        recent = candles[-40:] if len(candles) >= 40 else candles
        
        # Calculate average candle size for comparison
        avg_body = sum(abs(c['close'] - c['open']) for c in recent) / len(recent)
        min_displacement = avg_body * 1.5  # Displacement should be 1.5x average
        
        # Find all swing points
        swing_highs = []
        swing_lows = []
        
        for i in range(3, len(recent) - 3):
            # Swing high: higher than 2 candles on each side
            is_swing_high = all(recent[i]['high'] >= recent[j]['high'] for j in range(i-2, i)) and \
                           all(recent[i]['high'] >= recent[j]['high'] for j in range(i+1, min(i+3, len(recent))))
            if is_swing_high:
                swing_highs.append((i, recent[i]['high']))
            
            # Swing low: lower than 2 candles on each side
            is_swing_low = all(recent[i]['low'] <= recent[j]['low'] for j in range(i-2, i)) and \
                          all(recent[i]['low'] <= recent[j]['low'] for j in range(i+1, min(i+3, len(recent))))
            if is_swing_low:
                swing_lows.append((i, recent[i]['low']))
        
        if direction == 'long':
            # For bullish BoS: an IMPULSIVE candle breaks above swing high
            for swing_idx, swing_high in swing_highs:
                for j in range(swing_idx + 2, len(recent)):
                    candle = recent[j]
                    body_size = abs(candle['close'] - candle['open'])
                    is_bullish = candle['close'] > candle['open']
                    
                    # Check for impulsive bullish break
                    if is_bullish and candle['close'] > swing_high and body_size >= min_displacement:
                        return True
            return False
        else:
            # For bearish BoS: an IMPULSIVE candle breaks below swing low  
            for swing_idx, swing_low in swing_lows:
                for j in range(swing_idx + 2, len(recent)):
                    candle = recent[j]
                    body_size = abs(candle['close'] - candle['open'])
                    is_bearish = candle['close'] < candle['open']
                    
                    # Check for impulsive bearish break
                    if is_bearish and candle['close'] < swing_low and body_size >= min_displacement:
                        return True
            return False
    
    def check_choch(self, candles: List[dict], direction: str) -> bool:
        """Check Change of Character - momentum shift."""
        if len(candles) < 10:
            return False
        
        recent = candles[-10:]
        
        if direction == 'long':
            # Looking for higher low formation (just 2 consecutive higher lows)
            lows = [c['low'] for c in recent[-4:]]
            return len(lows) >= 2 and lows[-1] > lows[-2]
        else:
            # Looking for lower high formation
            highs = [c['high'] for c in recent[-4:]]
            return len(highs) >= 2 and highs[-1] < highs[-2]
    
    def check_fib_confluence(self, candles: List[dict], level: float, direction: str) -> bool:
        """Check if price is at 79% Fib retracement."""
        if len(candles) < 30:
            return False
        
        recent = candles[-30:]
        swing_high = max(c['high'] for c in recent)
        swing_low = min(c['low'] for c in recent)
        
        if direction == 'long':
            fib_79 = swing_high - (swing_high - swing_low) * 0.79
            return abs(level - fib_79) / fib_79 < 0.005  # Within 0.5%
        else:
            fib_79 = swing_low + (swing_high - swing_low) * 0.79
            return abs(level - fib_79) / fib_79 < 0.005
    
    def price_in_zone(self, price: float, zone_high: float, zone_low: float) -> bool:
        """Check if price is within a zone."""
        return zone_low <= price <= zone_high
    
    def check_ob_fvg_overlap(self, ob: OrderBlock, fvgs: List[FVG]) -> Optional[FVG]:
        """Check if OB overlaps with any FVG."""
        for fvg in fvgs:
            if fvg.direction == ob.direction:
                # Check overlap
                ob_range = (ob.low, ob.high)
                fvg_range = (fvg.bottom, fvg.top)
                
                overlap = not (ob_range[1] < fvg_range[0] or ob_range[0] > fvg_range[1])
                if overlap:
                    return fvg
        return None
    
    def try_option_1(self, candles: List[dict], symbol: str) -> Optional[Dict]:
        """
        Option 1: HTF Bias + Liquidity Sweep + BoS + FVG/OB Entry
        
        ICT Entry Model (High Win Rate Version):
        1. HTF trend - BOTH 4H and 1H must agree (stronger filter) ✅
        2. Liquidity sweep (took out highs/lows) ✅
        3. BoS in direction of HTF ✅
        4. ChoCH confirmation (momentum shift) ✅
        5. Price taps into FRESH FVG or OB (entry zone) ✅
        
        We DON'T enter at the liquidity zone - we wait for price to
        sweep, then come back to an FVG/OB for optimal entry.
        """
        confirmations = []
        
        # 1. HTF Trend - REQUIRE BOTH 4H AND 1H TO ALIGN for higher win rate
        htf_trend_4h = self.determine_htf_trend(candles, 240)
        htf_trend_1h = self.determine_htf_trend(candles, 60)
        
        # Both timeframes must agree (no ranging allowed)
        if htf_trend_4h == TrendDirection.RANGING or htf_trend_1h == TrendDirection.RANGING:
            self._last_rejection_reasons.append("HTF ranging (no clear trend)")
            return None
        
        if htf_trend_4h != htf_trend_1h:
            self._last_rejection_reasons.append(f"HTF conflict (4H={htf_trend_4h.value}, 1H={htf_trend_1h.value})")
            return None  # Conflicting bias - skip
        
        htf_trend = htf_trend_4h  # Both agree
        
        confirmations.append("HTF_BIAS_ALIGNED")
        direction = 'long' if htf_trend == TrendDirection.BULLISH else 'short'
        
        # 2. Liquidity Sweep (must have ALREADY happened)
        has_sweep, sweep_type = self.check_liquidity_sweep(candles, symbol)
        if has_sweep:
            self._last_sweep_found = True  # Track for stats
        if not has_sweep:
            self._last_rejection_reasons.append("No liquidity sweep detected")
            return None
        
        # Ensure sweep aligns with direction
        if direction == 'long' and sweep_type != 'low':
            self._last_rejection_reasons.append("Sweep direction mismatch (need low sweep for long)")
            return None
        if direction == 'short' and sweep_type != 'high':
            self._last_rejection_reasons.append("Sweep direction mismatch (need high sweep for short)")
            return None
        
        confirmations.append("LIQUIDITY_SWEEP")
        
        # 3. BoS (confirms reversal after sweep)
        has_bos = self.check_bos(candles, direction)
        if has_bos:
            self._last_bos_found = True  # Track for stats
        if not has_bos:
            self._last_rejection_reasons.append("No Break of Structure after sweep")
            return None
        
        confirmations.append("BOS")
        
        # 4. ChoCH confirmation - NOW REQUIRED for higher win rate
        has_choch = self.check_choch(candles, direction)
        if not has_choch:
            self._last_rejection_reasons.append("No ChoCH confirmation (momentum shift required)")
            return None
        confirmations.append("CHOCH")
        
        # 5. Price must be at FRESH FVG or OB for entry (not stale zones)
        current_price = candles[-1]['close']
        pip_value = self.get_pip_value()
        tolerance = 10 * pip_value  # 10 pips tolerance (tighter for precision)
        
        # Find the swept level (liquidity that was taken)
        # For SHORT: find the recent swing high that was swept
        # For LONG: find the recent swing low that was swept
        swept_level = self.find_sweep_level(candles, direction)
        
        # CRITICAL: Entry must be on the CORRECT side of the swept level
        # For SHORT: entry must be BELOW the swept high (price retraced from above)
        # For LONG: entry must be ABOVE the swept low (price retraced from below)
        if swept_level:
            buffer = 0.0005  # 5 pips buffer
            if direction == 'short' and current_price > swept_level - buffer:
                return None  # Price still too high, hasn't dropped below sweep level
            if direction == 'long' and current_price < swept_level + buffer:
                return None  # Price still too low, hasn't risen above sweep level
        
        # Find FVGs for entry - ICT RETRACEMENT ENTRY
        # After sweep + BoS, price RETRACES into an FVG before continuing
        # For SHORT: price retraces UP into a BULLISH FVG (gap from rally before drop)
        # For LONG: price retraces DOWN into a BEARISH FVG (gap from drop before rally)
        recent_candles = candles[-25:] if len(candles) >= 25 else candles
        fvgs = self.find_fvgs(recent_candles)
        entry_fvg = None
        for fvg in fvgs:
            # Bullish FVG = gap created by up-move → for SHORT entries (sell on retrace UP)
            # Bearish FVG = gap created by down-move → for LONG entries (buy on retrace DOWN)
            expected_fvg_dir = 'bullish' if direction == 'short' else 'bearish'
            if fvg.direction == expected_fvg_dir:
                if fvg.bottom - tolerance <= current_price <= fvg.top + tolerance:
                    entry_fvg = fvg
                    break
        
        # Find fresh OBs if no FVG - same retracement logic
        # For SHORT: price retraces to BEARISH OB (bullish candle before drop - where sellers enter)
        # For LONG: price retraces to BULLISH OB (bearish candle before rally - where buyers enter)
        order_blocks = self.find_order_blocks(recent_candles, 5)
        entry_ob = None
        if not entry_fvg:
            for ob in order_blocks:
                expected_ob_dir = 'bearish' if direction == 'short' else 'bullish'
                if ob.direction == expected_ob_dir:
                    if ob.low - tolerance <= current_price <= ob.high + tolerance:
                        entry_ob = ob
                        break
        
        # Must have either FVG or OB entry
        if not entry_fvg and not entry_ob:
            self._last_rejection_reasons.append("Price not at FVG/OB entry zone")
            return None  # Price not at entry zone yet, wait
        
        # CRITICAL: Check for REJECTION at the entry zone
        # The candle should show a wick in the direction we want to trade
        # This confirms the zone is being respected
        current_candle = candles[-1]
        body_size = abs(current_candle['close'] - current_candle['open'])
        upper_wick = current_candle['high'] - max(current_candle['open'], current_candle['close'])
        lower_wick = min(current_candle['open'], current_candle['close']) - current_candle['low']
        
        if direction == 'short':
            # For SHORT: want upper wick (rejection from above) showing sellers stepping in
            # Upper wick should be significant relative to body
            if upper_wick < body_size * 0.5 and upper_wick < 0.0003:  # At least 3 pips wick or 50% of body
                self._last_rejection_reasons.append("No rejection candle (need upper wick for short)")
                return None  # No rejection, wait
        else:
            # For LONG: want lower wick (rejection from below) showing buyers stepping in
            if lower_wick < body_size * 0.5 and lower_wick < 0.0003:
                self._last_rejection_reasons.append("No rejection candle (need lower wick for long)")
                return None  # No rejection, wait
        
        if entry_fvg:
            confirmations.append("FVG_ENTRY")
        if entry_ob:
            confirmations.append("OB_ENTRY")
        confirmations.append("REJECTION")
        
        return {
            'setup_type': SetupType.OPTION_1,
            'direction': direction,
            'confirmations': confirmations,
            'htf_trend': htf_trend,
            'has_liquidity_sweep': True,
            'has_bos': True,
            'asian_sweep': sweep_type in ['low', 'high'],
            'order_block': entry_ob,
            'fvg': entry_fvg,
            'htf_zone': None
        }
    
    def try_option_2(self, candles: List[dict], symbol: str) -> Optional[Dict]:
        """
        Option 2: HTF Zone + OB + ChoCH
        Requirements:
        - Price taps HTF zone (4H/1H) ✅
        - OB on 5M aligned with HTF zone ✅
        - ChoCH on LTF ✅
        """
        confirmations = []
        
        # 1. HTF Zones
        htf_zones_4h = self.find_htf_zones(candles, 240)
        htf_zones_1h = self.find_htf_zones(candles, 60)
        htf_zones = htf_zones_4h + htf_zones_1h
        
        if not htf_zones:
            return None
        
        current_price = candles[-1]['close']
        tapped_zone = None
        
        for zone in htf_zones:
            if self.price_in_zone(current_price, zone.high, zone.low):
                tapped_zone = zone
                break
        
        if not tapped_zone:
            return None
        
        confirmations.append("HTF_ZONE")
        direction = 'long' if tapped_zone.zone_type == 'demand' else 'short'
        
        # 2. 5M OB aligned with zone
        order_blocks_5m = self.find_order_blocks(candles, 5)
        aligned_ob = None
        
        for ob in order_blocks_5m:
            if ob.direction == ('bullish' if direction == 'long' else 'bearish'):
                # Check if OB is within or near HTF zone
                if (ob.low <= tapped_zone.high and ob.high >= tapped_zone.low):
                    aligned_ob = ob
                    break
        
        if not aligned_ob:
            return None
        
        confirmations.append("OB_5M")
        
        # 3. ChoCH
        has_choch = self.check_choch(candles, direction)
        if not has_choch:
            return None
        
        confirmations.append("CHOCH")
        
        # Bonus: check liquidity sweep (not required)
        has_sweep, _ = self.check_liquidity_sweep(candles, symbol)
        
        return {
            'setup_type': SetupType.OPTION_2,
            'direction': direction,
            'confirmations': confirmations,
            'htf_trend': None,  # Not required for this setup
            'has_liquidity_sweep': has_sweep,
            'has_bos': False,
            'has_choch': True,
            'asian_sweep': False,
            'order_block': aligned_ob,
            'fvg': None,
            'htf_zone': tapped_zone
        }
    
    def try_option_3(self, candles: List[dict]) -> Optional[Dict]:
        """
        Option 3: OB + FVG + Fib 79%
        
        Precision Entry Model:
        - 5M OB exists ✅
        - FVG overlapping the OB ✅
        - 79% Fib retracement ✅
        - Price is AT the OB/FVG zone (entry) ✅
        """
        confirmations = []
        current_price = candles[-1]['close']
        
        # 1. Find 5M OBs
        order_blocks_5m = self.find_order_blocks(candles, 5)
        if not order_blocks_5m:
            return None
        
        # Find OB that price is currently tapping
        tapped_ob = None
        for ob in order_blocks_5m:
            if ob.low <= current_price <= ob.high:
                tapped_ob = ob
                break
        
        if not tapped_ob:
            return None  # Price not at OB yet
        
        confirmations.append("OB_5M")
        direction = 'long' if tapped_ob.direction == 'bullish' else 'short'
        
        # 2. Find FVGs overlapping this OB
        fvgs = self.find_fvgs(candles)
        overlapping_fvg = self.check_ob_fvg_overlap(tapped_ob, fvgs)
        
        if not overlapping_fvg:
            return None
        
        confirmations.append("FVG")
        
        # 3. Check 79% Fib
        ob_mid = (tapped_ob.high + tapped_ob.low) / 2
        has_fib = self.check_fib_confluence(candles, ob_mid, direction)
        
        if not has_fib:
            return None
        
        confirmations.append("FIB_79")
        
        # Bonus: HTF bias (preferred but not mandatory)
        htf_trend = self.determine_htf_trend(candles, 240)
        
        return {
            'setup_type': SetupType.OPTION_3,
            'direction': direction,
            'confirmations': confirmations,
            'htf_trend': htf_trend if htf_trend != TrendDirection.RANGING else None,
            'has_liquidity_sweep': False,
            'has_bos': False,
            'has_choch': False,
            'asian_sweep': False,
            'order_block': tapped_ob,
            'fvg': overlapping_fvg,
            'htf_zone': None,
            'has_fib_confluence': True
        }
    
    def find_sweep_level(self, candles: List[dict], direction: str, setup_type: str = None) -> float:
        """
        Find the liquidity sweep level (swing high/low that was swept).
        This is where we place SL - beyond the swept level.
        
        For SHORT: Find the recent swing high that was swept
        For LONG: Find the recent swing low that was swept
        
        For HTF_LIQUIDITY_BOS setups: Use TIGHTER structure (last 10 candles) for 5-7 pip SL
        For other setups: Use standard structure (last 20 candles)
        """
        if len(candles) < 10:
            return None
        
        # HTF_LIQUIDITY_BOS gets tighter SL (10 candles = ~50 min for 5M)
        # This gives 5-7 pip SL for high-confidence setups
        if setup_type == 'HTF_LIQUIDITY_BOS':
            lookback = min(10, len(candles))
        else:
            # Standard setups use wider structure (20 candles = ~100 min)
            lookback = min(20, len(candles))
        
        recent = candles[-lookback:]
        
        if direction == 'short':
            # Find the highest swing high in recent candles (exclude last 3)
            swing_high = max(c['high'] for c in recent[:-3])
            return swing_high
        else:
            # Find the lowest swing low in recent candles (exclude last 3)
            swing_low = min(c['low'] for c in recent[:-3])
            return swing_low
    
    def calculate_sl_tp(self, entry: float, setup_data: Dict, candles: List[dict], 
                        symbol: str) -> Tuple[Optional[float], Optional[float], float]:
        """
        Calculate SL/TP based on ICT principles:
        - SL: Beyond the liquidity sweep level (swing high/low that was swept)
        - TP: 2x the risk (1:2 RR)
        
        HTF_LIQUIDITY_BOS gets tighter SL due to high confidence (95%)
        Gold uses different pip/point values than forex pairs.
        """
        direction = setup_data['direction']
        pip_value = self.get_pip_value(symbol)
        point_value = self.get_point_value(symbol)
        is_gold = symbol in ['XAUUSD', 'XAU_USD', 'GOLD']
        is_long = direction == 'long'
        setup_type = setup_data['setup_type'].value if hasattr(setup_data['setup_type'], 'value') else str(setup_data['setup_type'])
        
        # ICT SL Placement: Beyond the liquidity sweep level
        # This is the swing high/low that was swept before entry
        # Pass setup_type to use tighter structure for HTF_LIQUIDITY_BOS
        sweep_level = self.find_sweep_level(candles, direction, setup_type)
        
        if sweep_level is None:
            # Fallback to OB/zone based SL
            if setup_data['order_block']:
                ob = setup_data['order_block']
                sweep_level = ob.low if is_long else ob.high
            elif setup_data['htf_zone']:
                zone = setup_data['htf_zone']
                sweep_level = zone.low if is_long else zone.high
            else:
                recent = candles[-20:]
                sweep_level = min(c['low'] for c in recent) if is_long else max(c['high'] for c in recent)
        
        # Apply buffer beyond the sweep level
        # Gold: $5-10 buffer (Gold is volatile, needs room), Forex: 3-5 pips buffer
        if is_gold:
            buffer = 5.00 if setup_type == 'HTF_LIQUIDITY_BOS' else 10.00  # $5-10 buffer for Gold
        elif setup_type == 'HTF_LIQUIDITY_BOS':
            buffer = 3 * pip_value  # 3 pips buffer for high-confidence forex
        else:
            buffer = 5 * pip_value  # 5 pips buffer for standard forex
        
        if is_long:
            stop_loss = sweep_level - buffer  # SL below the swept low
        else:
            stop_loss = sweep_level + buffer  # SL above the swept high
        
        sl_distance = abs(entry - stop_loss)
        sl_points = sl_distance / point_value
        
        # Max SL limits - different for Gold vs Forex
        # Gold at $5000 needs $15-50 SL (0.3%-1% of price) to avoid noise
        if is_gold:
            if setup_type == 'HTF_LIQUIDITY_BOS':
                max_sl_points = 3000   # $30 max for HTF_LIQUIDITY_BOS
                min_sl_points = 1500   # $15 min
            else:
                max_sl_points = 5000   # $50 max for other setups
                min_sl_points = 2000   # $20 min
        else:
            # Forex: 5-25 pips SL range
            if setup_type == 'HTF_LIQUIDITY_BOS':
                max_sl_points = 70   # 7 pips max for HTF_LIQUIDITY_BOS
                min_sl_points = 50   # 5 pips min for HTF_LIQUIDITY_BOS
            else:
                max_sl_points = 250  # 25 pips max for other setups
                min_sl_points = 80   # 8 pips min (too tight = noise)
        
        # Validate SL range
        if sl_points < min_sl_points:
            return None, None, 0  # Too tight
        
        # If SL is too big, cap it to max allowed
        if sl_points > max_sl_points:
            # Recalculate stop_loss with max distance
            max_sl_distance = max_sl_points * point_value
            if direction == 'long':
                stop_loss = entry - max_sl_distance
            else:
                stop_loss = entry + max_sl_distance
            sl_distance = max_sl_distance
            sl_points = max_sl_points
        
        # Calculate TP - Gold uses 1:1.5 RR (higher win rate), Forex uses 1:2
        # Gold is more volatile, tighter TP = higher probability of hitting
        if is_gold:
            rr_multiplier = 1.5  # 1:1.5 for Gold
        else:
            rr_multiplier = 2.0  # 1:2 for Forex
        
        if direction == 'long':
            take_profit = entry + (sl_distance * rr_multiplier)
        else:
            take_profit = entry - (sl_distance * rr_multiplier)
        
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        rr_ratio = reward / risk if risk > 0 else 0
        
        # Minimum RR check - Gold: 1.3, Forex: 1.8
        min_rr = 1.3 if is_gold else 1.8
        if rr_ratio < min_rr:
            return None, None, 0
        
        return stop_loss, take_profit, rr_ratio
    
    def determine_risk_percentage(self, confirmation_count: int) -> float:
        """
        Risk Management: 3 confirmations = 1.0%, 2 = 0.5%, <2 = no trade.
        """
        risk_map = {3: 1.0, 2: 0.5}
        return risk_map.get(min(confirmation_count, 3), 0.0)
    
    def can_take_trade(self, timestamp: int, symbol: str = 'EURUSD') -> bool:
        """Check daily limits (max 1 trade/day per symbol for highest quality)."""
        current_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
        
        # Reset all counters on new day
        if self.current_date != current_date:
            self.current_date = current_date
            self.trades_today = {}  # Reset all pairs
        
        # Get trade count for this specific symbol
        symbol_trades = self.trades_today.get(symbol, 0)
        
        # Only 1 trade per day per pair for highest win rate
        # The first setup of the day is usually the cleanest
        if symbol_trades >= 1:
            return False
        
        # Session check is now done at the top of analyze()
        return True
    
    def record_trade(self, symbol: str):
        """Record that a trade was taken for a symbol today."""
        self.trades_today[symbol] = self.trades_today.get(symbol, 0) + 1
    
    def analyze(self, candles: List[dict], symbol: str = 'EURUSD', mtf_data: Dict[str, List[dict]] = None, backtest_mode: bool = False) -> Optional[Dict]:
        """
        Main analysis - Try all 3 options in order of priority.
        
        Priority for EU/GU: Option 1 > Option 2 > Option 3
        Priority for Gold: Option 2 > Option 1 > Option 3
        
        Args:
            candles: Base candles (5M) for fallback
            symbol: Trading pair
            mtf_data: Multi-timeframe data {'4H': [...], '1H': [...], '15M': [...], '5M': [...]}
            backtest_mode: If True, use candle timestamp for session checks instead of current time
        """
        # Reset rejection reasons and stats flags
        self._last_rejection_reasons = []
        self._last_sweep_found = False
        self._last_bos_found = False
        
        # Set current symbol for pip calculations
        self.current_symbol = symbol
        
        # Set multi-timeframe data if provided
        if mtf_data:
            self.set_mtf_data(mtf_data)
        
        # Use 5M candles as base for timestamp check
        base_candles = mtf_data.get('5M', candles) if mtf_data else candles
        
        if len(base_candles) < 50:
            self._last_rejection_reasons.append("Insufficient data (need 50+ candles)")
            return None
        
        # Use candle timestamp for backtest, current time for live trading
        candle_timestamp = base_candles[-1]['timestamp']
        if backtest_mode:
            current_timestamp = candle_timestamp  # Use candle time for backtests
        else:
            current_timestamp = int(datetime.now(timezone.utc).timestamp())
        
        # ===== SESSION CHECK FIRST - Must be in trading hours =====
        can_trade, session_reason = self.filters.can_trade_now(current_timestamp)
        if not can_trade:
            self._last_rejection_reasons.append(f"Outside trading session: {session_reason}")
            return None
        
        # ===== SIGNAL COOLDOWN - Prevent duplicate signals =====
        if not self.check_signal_cooldown(symbol, current_timestamp):
            self._last_rejection_reasons.append(f"Signal cooldown ({self._signal_cooldown_minutes}min between signals)")
            return None
        
        # ===== NEWS FILTER - Check for high-impact events (skip in backtest) =====
        if not backtest_mode:
            is_blackout, news_reason = is_news_blackout(symbol)
            if is_blackout:
                self._last_rejection_reasons.append(news_reason)
                return None
            return None
        
        # Check if we already took a trade for this symbol today
        if not self.can_take_trade(current_timestamp, symbol):
            self._last_rejection_reasons.append(f"Already traded {symbol} today (1 per day limit)")
            return None
        
        # Determine priority based on symbol
        # Focus on Option 1 only for EU/GU as it has the best win rate (55%+)
        # Option 2 and 3 have lower win rates and drag down performance
        if symbol == 'XAUUSD':
            options = [self.try_option_2, self.try_option_1]  # Gold prefers HTF zones
        else:  # EU, GU - use Option 1 only for best win rate
            options = [self.try_option_1]
        
        setup_data = None
        for option_func in options:
            setup_data = option_func(base_candles, symbol)
            if setup_data:
                break
        
        if not setup_data:
            # Rejection reasons already added by try_option methods
            if not self._last_rejection_reasons:
                self._last_rejection_reasons.append("No valid ICT setup pattern")
            return None
        
        direction = setup_data['direction']
        
        # ===== NEW FILTERS =====
        
        # 1. Correlation Filter - prevent opposite signals on EU/GBP
        if self.check_correlation_conflict(symbol, direction, current_timestamp):
            self._last_rejection_reasons.append("Correlation conflict (opposite signal on related pair)")
            return None
        
        # 2. 15M Confirmation - ensure 15M structure agrees
        if not self.check_15m_confirmation(direction):
            self._last_rejection_reasons.append("15M structure conflicts with trade direction")
            return None
        
        # 3. 5M Entry Trigger - wait for 5M ChoCH before entry
        if not self.check_5m_entry_trigger(base_candles, direction):
            self._last_rejection_reasons.append("No 5M ChoCH confirmation yet (wait for LTF entry)")
            return None
        
        # 4. Session-specific confidence threshold
        session = self.get_session_type(current_timestamp)
        min_confidence = self.session_settings.get(session, {}).get('min_confidence', 0.85)
        
        # Check confirmation count
        confirmation_count = len(setup_data['confirmations'])
        if confirmation_count < 2:
            self._last_rejection_reasons.append(f"Insufficient confirmations ({confirmation_count}/2 required)")
            return None  # Need at least 2 confirmations
        
        # Calculate risk percentage
        risk_percentage = self.determine_risk_percentage(confirmation_count)
        
        # Calculate SL/TP
        entry_price = base_candles[-1]['close']
        
        # Note: is_in_liquidity_zone check DISABLED for now
        # Since Option 1 already requires entry at FVG/OB (not liquidity zone),
        # this extra check was overly restrictive and blocking valid entries.
        # The FVG/OB entry requirement IS the "not at liquidity zone" protection.
        # if self.is_in_liquidity_zone(base_candles, entry_price):
        #     return None  # Don't enter when sitting in liquidity zone
        
        stop_loss, take_profit, rr_ratio = self.calculate_sl_tp(
            entry_price, setup_data, base_candles, symbol
        )
        
        if stop_loss is None:
            self._last_rejection_reasons.append("Invalid SL/TP calculation (SL out of range)")
            return None
        
        # Calculate confidence
        confidence = 0.60 + (confirmation_count * 0.10)
        if rr_ratio >= 4.0:
            confidence += 0.05
        if setup_data['htf_trend'] and setup_data['htf_trend'] != TrendDirection.RANGING:
            confidence += 0.05
        
        confidence = min(confidence, 0.95)
        
        # Record trade for this symbol (1 per day limit)
        self.record_trade(symbol)
        
        # Record signal time for cooldown tracking
        self._last_signal_time[symbol] = current_timestamp
        
        return {
            'timestamp': current_timestamp,
            'symbol': symbol,
            'setup_type': setup_data['setup_type'].value,
            'direction': setup_data['direction'],
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'risk_reward': rr_ratio,
            'risk_percentage': risk_percentage,
            'confirmations': setup_data['confirmations'],
            'confirmation_count': confirmation_count,
            'htf_trend': setup_data['htf_trend'].value if setup_data['htf_trend'] else 'none',
            'has_liquidity_sweep': setup_data['has_liquidity_sweep'],
            'has_bos': setup_data['has_bos'],
            'has_choch': setup_data.get('has_choch', False),
            'has_fib_confluence': setup_data.get('has_fib_confluence', False),
            'asian_sweep': setup_data['asian_sweep'],
            'confidence': confidence
        }
    
    def get_last_rejection_reasons(self) -> List[str]:
        """Get the reasons why the last analysis was rejected."""
        return self._last_rejection_reasons if self._last_rejection_reasons else ['No valid ICT setup']
    
    def get_last_analysis_stats(self) -> dict:
        """Get stats from the last analysis (sweeps, BoS detected)."""
        return {
            'sweep_found': self._last_sweep_found,
            'bos_found': self._last_bos_found
        }


# Compatibility wrapper for existing code
class ProfessionalStrategy(FlexibleICTStrategy):
    """Wrapper for backward compatibility."""
    pass
