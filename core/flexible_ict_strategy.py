"""
Flexible ICT Trading Strategy with 6 Setup Options
Based on practical trading plan with realistic confluence requirements.

Setup Options:
1. HTF Bias + Liquidity Sweep + BoS (Safest - best for EU/GU London)
2. HTF Zone + OB + ChoCH (LEGACY - 0% WR, replaced by Option 6)
3. OB + FVG + Fib 79% (LEGACY - 20% WR, replaced by Option 6)
4. Liquidity Sweep + Engulfing (Simple price action — 100% WR, PRIORITY for EU)
5. Full ICT Model: Sweep → BOS + iFVG + SMT + 79% → Continue → Enter → DOL TP
6. Zone + OB/FVG + Fib + Sweep (Corrected consolidation of Opt 2+3 — 57% WR on GBP)

Pair-Specific Priority (waterfall — first match wins):
  EURUSD: Option 4 → Option 1 → Option 5 → Option 6
  GBPUSD: Option 5 → Option 6 → Option 1 → Option 4
  Gold:   Option 1 → Option 4 → Option 5 → Option 6

Risk Management:
- 3+ confirmations = full risk (1.0%)
- 2  confirmations = half risk (0.5%)
- <2 confirmations = no trade
"""

import os
import json
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
from enum import Enum
from datetime import datetime, timezone
from core.legacy.advanced_filters import AdvancedFilters

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
    OPTION_2 = "HTF_ZONE_OB_CHOCH"  # HTF Zone + OB + ChoCH (legacy)
    OPTION_3 = "OB_FVG_FIB"         # OB + FVG + Fib 79% (legacy)
    OPTION_4 = "LIQ_SWEEP_ENGULF"   # Liquidity Sweep + Engulfing (price action)
    OPTION_5 = "ICT_SWEEP_CONFIRM"  # Sweep + BOS + iFVG + SMT + 79% ext (full ICT model)
    OPTION_6 = "ZONE_OB_FIB_SWEEP"  # Corrected consolidation of Opt 2+3 (zone + OB/FVG + Fib + sweep)


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
    
    # Persistent state file — survives restarts
    _STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'signal_state.json')
    
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
        self._signal_cooldown_minutes = 240  # 4 hours between signals on same pair (was 30min = spam)
        
        # All market data for correlated pair access (SMT divergence)
        self._all_market_data = {}  # {'EUR_USD': {'5M': [...], '1H': [...]}, 'GBP_USD': {...}}
        
        # Session levels tracker: {'EUR_USD': {'asia': {'high': x, 'low': y}, 'london': {...}, 'ny': {...}}}
        self._session_levels = {}
        
        # Sweep level dedup: don't re-signal on the same sweep level/direction
        # {'EUR_USD': {'level': 1.1898, 'direction': 'long', 'timestamp': ...}}
        self._last_sweep_signal = {}
        
        # Load persisted state from disk (survives restarts)
        self._load_state()
        
        # Session-specific settings
        self.session_settings = {
            'asian': {'start': 0, 'end': 8, 'min_confidence': 0.80},
            'london': {'start': 8, 'end': 12, 'min_confidence': 0.80},
            'newyork': {'start': 13, 'end': 17, 'min_confidence': 0.80}
        }
        
        # Dynamic R:R — DOL-based targeting with floors:
        #   Forex floor: 1:2 (backtested 60% WR), Gold floor: 1:1.5
        #   No ceiling — DOL confluence determines actual TP
        self.target_rr = 2.0  # Minimum floor for forex (used as reference)
    
    def _load_state(self):
        """Load signal cooldown and trade state from disk (survives restarts)."""
        try:
            if os.path.exists(self._STATE_FILE):
                with open(self._STATE_FILE, 'r') as f:
                    state = json.load(f)
                # Restore cooldown times
                self._last_signal_time = state.get('last_signal_time', {})
                # Restore today's trades (check date)
                saved_date = state.get('current_date')
                today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                if saved_date == today:
                    self.trades_today = state.get('trades_today', {})
                    self.current_date = datetime.now(timezone.utc).date()
                # Restore recent signal directions
                self._recent_signals = state.get('recent_signals', {})
                import logging
                logging.getLogger('strategy').info(
                    f"📂 Loaded signal state: cooldowns={list(self._last_signal_time.keys())}, "
                    f"trades_today={self.trades_today}"
                )
        except Exception as e:
            import logging
            logging.getLogger('strategy').warning(f"Could not load signal state: {e}")
    
    def _save_state(self):
        """Persist signal cooldown and trade state to disk."""
        try:
            os.makedirs(os.path.dirname(self._STATE_FILE), exist_ok=True)
            state = {
                'last_signal_time': self._last_signal_time,
                'trades_today': self.trades_today,
                'current_date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                'recent_signals': self._recent_signals
            }
            with open(self._STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            import logging
            logging.getLogger('strategy').warning(f"Could not save signal state: {e}")
    
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
        if 0 <= hour < 8:
            return 'asian'
        elif 8 <= hour < 12:
            return 'london'
        elif 13 <= hour < 17:
            return 'newyork'
        return 'london'  # Default to london confidence for overlap/late NY
    
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
        hl_count = sum(1 for i in range(5, len(lows)) if lows[i] > min(lows[i-5:i]))
        lh_count = sum(1 for i in range(5, len(highs)) if highs[i] < min(highs[i-5:i]))
        ll_count = sum(1 for i in range(5, len(lows)) if lows[i] < max(lows[i-5:i]))
        
        bullish_score = hh_count + hl_count
        bearish_score = lh_count + ll_count
        
        if bullish_score > bearish_score * 1.15:
            return TrendDirection.BULLISH
        elif bearish_score > bullish_score * 1.15:
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
    
    def detect_engulfing(self, candles: List[dict], timeframe: int = 15) -> Optional[dict]:
        """
        Detect engulfing candles on specified timeframe.
        
        Bullish Engulfing: bearish candle followed by bullish candle that
        opens at/below previous close and closes at/above previous open.
        
        Bearish Engulfing: bullish candle followed by bearish candle that
        opens at/above previous close and closes at/below previous open.
        
        Returns dict with 'direction', 'candle', 'prev_candle' or None.
        """
        # Use actual MTF data if available
        if self.mtf_data:
            tf_candles = self.get_htf_candles(timeframe)
        else:
            tf_candles = self.filters.get_timeframe_data(candles, timeframe)
        
        if len(tf_candles) < 3:
            return None
        
        pip_value = self.get_pip_value()
        min_body = 3 * pip_value  # Engulfing body must be at least 3 pips
        
        # Check last 3 candles for engulfing patterns
        for i in range(len(tf_candles) - 1, max(len(tf_candles) - 4, 0), -1):
            curr = tf_candles[i]
            prev = tf_candles[i - 1]
            
            curr_body = curr['close'] - curr['open']
            prev_body = prev['close'] - prev['open']
            
            # Bullish Engulfing: prev bearish, current bullish and engulfs
            if (prev_body < 0 and curr_body > 0 and
                abs(curr_body) >= min_body and
                curr['open'] <= prev['close'] and
                curr['close'] >= prev['open']):
                return {
                    'direction': 'long',
                    'candle': curr,
                    'prev_candle': prev,
                    'timeframe': timeframe,
                    'body_size': abs(curr_body)
                }
            
            # Bearish Engulfing: prev bullish, current bearish and engulfs
            if (prev_body > 0 and curr_body < 0 and
                abs(curr_body) >= min_body and
                curr['open'] >= prev['close'] and
                curr['close'] <= prev['open']):
                return {
                    'direction': 'short',
                    'candle': curr,
                    'prev_candle': prev,
                    'timeframe': timeframe,
                    'body_size': abs(curr_body)
                }
        
        return None
    
    def find_5m_liquidity_zone(self, candles: List[dict], lookback: int = 60) -> Optional[dict]:
        """
        Find a liquidity zone on 5M: cluster of equal lows/highs that got swept.
        
        A liquidity zone is where price built up equal lows/highs (resting orders)
        and then swept through them.
        
        Returns dict with 'level', 'type' ('low'/'high'), 'swept', 'sweep_candle'.
        """
        if len(candles) < 20:
            return None
        
        pip_value = self.get_pip_value()
        eq_tolerance = 3 * pip_value  # 3 pips for equal levels
        
        recent = candles[-lookback:] if len(candles) >= lookback else candles
        lows = [c['low'] for c in recent]
        highs = [c['high'] for c in recent]
        
        # Find clusters of equal lows (liquidity pool below)
        low_clusters = []
        for i in range(len(lows) - 5):
            matches = [i]
            for j in range(i + 1, len(lows)):
                if abs(lows[j] - lows[i]) < eq_tolerance:
                    matches.append(j)
            if len(matches) >= 2:
                avg_level = sum(lows[m] for m in matches) / len(matches)
                low_clusters.append({'level': avg_level, 'count': len(matches), 'type': 'low'})
        
        # Find clusters of equal highs (liquidity pool above)
        high_clusters = []
        for i in range(len(highs) - 5):
            matches = [i]
            for j in range(i + 1, len(highs)):
                if abs(highs[j] - highs[i]) < eq_tolerance:
                    matches.append(j)
            if len(matches) >= 2:
                avg_level = sum(highs[m] for m in matches) / len(matches)
                high_clusters.append({'level': avg_level, 'count': len(matches), 'type': 'high'})
        
        # Check if any cluster was swept in the last 10 candles
        last_candles = candles[-10:]
        
        # Check low sweeps (for long setups)
        for cluster in sorted(low_clusters, key=lambda x: x['count'], reverse=True):
            for c in last_candles:
                if c['low'] < cluster['level'] - eq_tolerance:
                    # Low was swept and price is back above
                    if candles[-1]['close'] > cluster['level']:
                        cluster['swept'] = True
                        cluster['sweep_low'] = c['low']
                        return cluster
        
        # Check high sweeps (for short setups)
        for cluster in sorted(high_clusters, key=lambda x: x['count'], reverse=True):
            for c in last_candles:
                if c['high'] > cluster['level'] + eq_tolerance:
                    if candles[-1]['close'] < cluster['level']:
                        cluster['swept'] = True
                        cluster['sweep_high'] = c['high']
                        return cluster
        
        return None
    
    def try_option_4(self, candles: List[dict], symbol: str) -> Optional[Dict]:
        """
        Option 4: Liquidity Sweep + Engulfing Confirmation
        
        Simple but effective price action setup:
        1. Price sweeps a liquidity zone on 5M (equal lows/highs or session lows/highs)
        2. 15M engulfing candle confirms reversal
        3. Enter on the close of the engulfing candle
        
        SL: Below/above the swept liquidity level
        TP: 2x risk (1:2 R:R)
        
        This catches setups like:
        - Asian session low sweep → London bullish engulfing → Buy
        - Previous session high sweep → bearish engulfing → Sell
        """
        import logging
        _log = logging.getLogger('strategy')
        confirmations = []
        
        # 1. Check for engulfing candle on 15M (the trigger)
        engulfing = self.detect_engulfing(candles, timeframe=15)
        if not engulfing:
            self._last_rejection_reasons.append("Opt4: No engulfing candle on 15M")
            return None
        
        direction = engulfing['direction']
        confirmations.append("15M_ENGULFING")
        
        # 2. Check for liquidity sweep on 5M
        # First try: check if Asian range or session lows/highs were swept
        has_sweep, sweep_type = self.check_liquidity_sweep(candles, symbol)
        
        if has_sweep:
            # Verify sweep direction matches engulfing
            if direction == 'long' and sweep_type == 'low':
                confirmations.append("LIQUIDITY_SWEEP")
                self._last_sweep_found = True
            elif direction == 'short' and sweep_type == 'high':
                confirmations.append("LIQUIDITY_SWEEP")
                self._last_sweep_found = True
            else:
                has_sweep = False  # Direction mismatch
        
        # Second try: check for 5M liquidity zone sweep
        if not has_sweep:
            liq_zone = self.find_5m_liquidity_zone(candles)
            if liq_zone and liq_zone.get('swept'):
                if direction == 'long' and liq_zone['type'] == 'low':
                    confirmations.append("5M_LIQ_ZONE_SWEEP")
                    self._last_sweep_found = True
                    has_sweep = True
                elif direction == 'short' and liq_zone['type'] == 'high':
                    confirmations.append("5M_LIQ_ZONE_SWEEP")
                    self._last_sweep_found = True
                    has_sweep = True
        
        # Third try: just check if price made a new low/high and reversed
        if not has_sweep:
            recent = candles[-20:]
            if direction == 'long':
                lowest = min(c['low'] for c in recent)
                # Did recent candles sweep the low and recover?
                last_3 = candles[-3:]
                swept_and_recovered = any(c['low'] <= lowest * 1.0001 for c in last_3) and candles[-1]['close'] > lowest
                if swept_and_recovered:
                    confirmations.append("SWING_LOW_SWEEP")
                    has_sweep = True
            else:
                highest = max(c['high'] for c in recent)
                last_3 = candles[-3:]
                swept_and_recovered = any(c['high'] >= highest * 0.9999 for c in last_3) and candles[-1]['close'] < highest
                if swept_and_recovered:
                    confirmations.append("SWING_HIGH_SWEEP")
                    has_sweep = True
        
        if not has_sweep:
            self._last_rejection_reasons.append("Opt4: Engulfing found but no liquidity sweep")
            return None
        
        # 3. Optional bonus confirmations
        # Check for OB at the sweep zone
        order_blocks = self.find_order_blocks(candles, 5)
        current_price = candles[-1]['close']
        pip_value = self.get_pip_value()
        tolerance = 15 * pip_value
        
        for ob in order_blocks:
            expected_dir = 'bullish' if direction == 'long' else 'bearish'
            if ob.direction == expected_dir:
                if ob.low - tolerance <= current_price <= ob.high + tolerance:
                    confirmations.append("OB_AT_SWEEP")
                    break
        
        # Check HTF trend (bonus, not required)
        htf_trend = self.determine_htf_trend(candles, 240)
        if htf_trend == TrendDirection.BULLISH and direction == 'long':
            confirmations.append("HTF_ALIGNED")
        elif htf_trend == TrendDirection.BEARISH and direction == 'short':
            confirmations.append("HTF_ALIGNED")
        
        _log.info(f"✅ [{symbol}] Option 4 HIT: {direction} - {confirmations}")
        
        return {
            'setup_type': SetupType.OPTION_4,
            'direction': direction,
            'confirmations': confirmations,
            'htf_trend': htf_trend if htf_trend != TrendDirection.RANGING else None,
            'has_liquidity_sweep': True,
            'has_bos': False,
            'has_choch': False,
            'has_fib_confluence': False,
            'asian_sweep': 'LIQUIDITY_SWEEP' in confirmations,
            'order_block': None,
            'fvg': None,
            'htf_zone': None
        }
    
    # ====================================================================
    # OPTION 5 COMPONENTS: Full ICT Model
    # Sweep → 5M Confirm (BOS + iFVG + SMT + 79%) → Continuation → Enter → DOL TP
    # ====================================================================

    def set_all_market_data(self, all_data: dict):
        """
        Store market data for ALL symbols so we can cross-reference for SMT.
        Called from the webhook server before analyze().
        
        Args:
            all_data: {'EUR_USD': {'5M': [candles], '1H': [candles], ...}, 'GBP_USD': {...}}
        """
        self._all_market_data = all_data

    def _get_correlated_pair(self, symbol: str) -> Optional[str]:
        """Get the correlated pair for SMT divergence comparison."""
        correlation_map = {
            'EURUSD': 'GBPUSD', 'EUR_USD': 'GBP_USD',
            'GBPUSD': 'EURUSD', 'GBP_USD': 'EUR_USD',
        }
        return correlation_map.get(symbol)

    def _get_correlated_candles(self, symbol: str, timeframe: str = '5M') -> List[dict]:
        """Get candles for the correlated pair (for SMT divergence)."""
        corr_symbol = self._get_correlated_pair(symbol)
        if not corr_symbol or corr_symbol not in self._all_market_data:
            return []
        return self._all_market_data[corr_symbol].get(timeframe, [])

    # --- Session H/L Tracking ---

    def compute_session_levels(self, candles_1h: List[dict], symbol: str) -> dict:
        """
        Compute Asia / London / NY session highs and lows from 1H candles.
        
        Sessions (UTC):
            Asia:   00:00 – 08:00
            London: 07:00 – 16:00  (1h overlap with Asia)
            NY:     12:00 – 21:00  (4h overlap with London)
        
        Returns dict: {
            'asia':   {'high': float, 'low': float, 'candles': [...]},
            'london': {'high': float, 'low': float, 'candles': [...]},
            'ny':     {'high': float, 'low': float, 'candles': [...]},
            'prev_asia':   {'high': float, 'low': float},
            'prev_london': {'high': float, 'low': float},
            'prev_ny':     {'high': float, 'low': float},
        }
        """
        if len(candles_1h) < 24:
            return {}

        session_defs = {
            'asia':   (0, 8),
            'london': (7, 16),
            'ny':     (12, 21),
        }

        # Bucket candles by session using their hour
        from collections import defaultdict
        buckets = defaultdict(list)           # 'asia' -> [candles]
        prev_buckets = defaultdict(list)      # 'prev_asia' -> [candles]

        now_utc = datetime.now(timezone.utc)
        today_midnight = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_midnight = today_midnight.replace(day=today_midnight.day - 1) if today_midnight.day > 1 else today_midnight

        for c in candles_1h:
            ts = datetime.fromtimestamp(c['timestamp'], tz=timezone.utc)
            hour = ts.hour
            is_today = ts >= today_midnight

            for sess_name, (start_h, end_h) in session_defs.items():
                if start_h <= hour < end_h:
                    if is_today:
                        buckets[sess_name].append(c)
                    else:
                        prev_buckets[sess_name].append(c)

        result = {}
        for sess_name in session_defs:
            # Current session
            cs = buckets.get(sess_name, [])
            if cs:
                result[sess_name] = {
                    'high': max(c['high'] for c in cs),
                    'low': min(c['low'] for c in cs),
                    'candles': cs,
                }
            # Previous session
            ps = prev_buckets.get(sess_name, [])
            if ps:
                result[f'prev_{sess_name}'] = {
                    'high': max(c['high'] for c in ps),
                    'low': min(c['low'] for c in ps),
                }

        self._session_levels[symbol] = result
        return result

    def detect_session_level_sweep(self, candles_5m: List[dict], symbol: str) -> Optional[dict]:
        """
        Detect if price swept a session high or low (Asia/London/NY/previous sessions).
        
        A sweep = wick past the level followed by close back inside.
        
        Returns: {'level': float, 'level_name': str, 'direction': 'long'|'short',
                  'sweep_candle_idx': int} or None
        """
        sess = self._session_levels.get(symbol, {})
        if not sess:
            # Try to compute from 1H data if available
            candles_1h = self.get_htf_candles(60)
            if candles_1h:
                sess = self.compute_session_levels(candles_1h, symbol)
        if not sess:
            return None

        pip_value = self.get_pip_value(symbol)
        sweep_tolerance = 2 * pip_value  # Must pierce by at least 2 pips

        # Collect all levels to check
        levels_to_check = []
        for sess_name in ['asia', 'london', 'ny', 'prev_asia', 'prev_london', 'prev_ny']:
            s = sess.get(sess_name)
            if not s:
                continue
            levels_to_check.append({'level': s['high'], 'name': f"{sess_name}_high", 'side': 'high'})
            levels_to_check.append({'level': s['low'], 'name': f"{sess_name}_low", 'side': 'low'})

        if not levels_to_check:
            return None

        # Check last 15 candles for sweep
        recent = candles_5m[-15:] if len(candles_5m) >= 15 else candles_5m
        for i in range(len(recent) - 1, max(len(recent) - 10, -1), -1):
            c = recent[i]
            for lvl in levels_to_check:
                level_price = lvl['level']
                if lvl['side'] == 'high':
                    # Sweep above high: wick above, close below
                    if (c['high'] > level_price + sweep_tolerance and
                            c['close'] < level_price):
                        return {
                            'level': level_price,
                            'level_name': lvl['name'],
                            'direction': 'short',  # Swept high → bearish
                            'sweep_candle_idx': i,
                            'sweep_wick': c['high'],
                        }
                else:  # low
                    # Sweep below low: wick below, close above
                    if (c['low'] < level_price - sweep_tolerance and
                            c['close'] > level_price):
                        return {
                            'level': level_price,
                            'level_name': lvl['name'],
                            'direction': 'long',  # Swept low → bullish
                            'sweep_candle_idx': i,
                            'sweep_wick': c['low'],
                        }
        return None

    def detect_htf_liquidity_sweep(self, candles_5m: List[dict], candles_1h: List[dict],
                                    candles_4h: List[dict], symbol: str) -> Optional[dict]:
        """
        Master sweep detector — checks 1H swing H/L, 4H swing H/L, and session levels.
        Returns the highest-quality sweep found.
        """
        import logging
        _log = logging.getLogger('strategy')
        pip_value = self.get_pip_value(symbol)
        results = []

        # 1. Session level sweep (Asia/London/NY)
        sess_sweep = self.detect_session_level_sweep(candles_5m, symbol)
        if sess_sweep:
            sess_sweep['source'] = 'session'
            sess_sweep['priority'] = 1  # Highest priority
            results.append(sess_sweep)

        # 2. 1H swing high/low sweep
        if len(candles_1h) >= 20:
            swing_levels_1h = self._find_swing_levels(candles_1h, lookback=20)
            for lvl in swing_levels_1h:
                recent = candles_5m[-10:] if len(candles_5m) >= 10 else candles_5m
                for c in recent:
                    if lvl['side'] == 'high' and c['high'] > lvl['level'] + 2 * pip_value and c['close'] < lvl['level']:
                        results.append({
                            'level': lvl['level'], 'level_name': '1H_swing_high',
                            'direction': 'short', 'source': '1H', 'priority': 2,
                            'sweep_wick': c['high'],
                        })
                    elif lvl['side'] == 'low' and c['low'] < lvl['level'] - 2 * pip_value and c['close'] > lvl['level']:
                        results.append({
                            'level': lvl['level'], 'level_name': '1H_swing_low',
                            'direction': 'long', 'source': '1H', 'priority': 2,
                            'sweep_wick': c['low'],
                        })

        # 3. 4H swing high/low sweep
        if len(candles_4h) >= 15:
            swing_levels_4h = self._find_swing_levels(candles_4h, lookback=15)
            for lvl in swing_levels_4h:
                recent = candles_5m[-10:] if len(candles_5m) >= 10 else candles_5m
                for c in recent:
                    if lvl['side'] == 'high' and c['high'] > lvl['level'] + 2 * pip_value and c['close'] < lvl['level']:
                        results.append({
                            'level': lvl['level'], 'level_name': '4H_swing_high',
                            'direction': 'short', 'source': '4H', 'priority': 3,
                            'sweep_wick': c['high'],
                        })
                    elif lvl['side'] == 'low' and c['low'] < lvl['level'] - 2 * pip_value and c['close'] > lvl['level']:
                        results.append({
                            'level': lvl['level'], 'level_name': '4H_swing_low',
                            'direction': 'long', 'source': '4H', 'priority': 3,
                            'sweep_wick': c['low'],
                        })

        if not results:
            return None

        # Return highest priority sweep
        results.sort(key=lambda x: x['priority'])
        best = results[0]
        _log.info(f"🔍 [{symbol}] Opt5 sweep: {best['level_name']} at {best['level']:.5f} → {best['direction']}")
        return best

    def _find_swing_levels(self, candles: List[dict], lookback: int = 20) -> List[dict]:
        """Find swing highs and lows from candle data."""
        levels = []
        recent = candles[-lookback:] if len(candles) >= lookback else candles
        for i in range(2, len(recent) - 2):
            # Swing high
            if (recent[i]['high'] >= recent[i-1]['high'] and
                    recent[i]['high'] >= recent[i-2]['high'] and
                    recent[i]['high'] >= recent[i+1]['high'] and
                    recent[i]['high'] >= recent[i+2]['high']):
                levels.append({'level': recent[i]['high'], 'side': 'high', 'idx': i})
            # Swing low
            if (recent[i]['low'] <= recent[i-1]['low'] and
                    recent[i]['low'] <= recent[i-2]['low'] and
                    recent[i]['low'] <= recent[i+1]['low'] and
                    recent[i]['low'] <= recent[i+2]['low']):
                levels.append({'level': recent[i]['low'], 'side': 'low', 'idx': i})
        return levels

    # --- SMT Divergence ---

    def detect_smt_divergence(self, candles_5m: List[dict], symbol: str,
                               sweep_info: dict) -> Optional[dict]:
        """
        Smart Money Technique (SMT) Divergence.
        
        If symbol sweeps a low/high but the correlated pair does NOT make a
        corresponding new low/high → institutions are manipulating one side.
        This CONFIRMS the sweep is a genuine trap.
        
        Example:
            EU sweeps Asian low (makes new low) but GU holds its Asian low
            → EU low sweep is valid → BUY EU
        
        Note: Bearish SMT rarely fires because EU/GU tend to push highs together.
        This is INTENTIONAL — it acts as a strict quality gate for short entries,
        forcing them to qualify on other confirmations alone.
        Backtest proved: loosening bearish SMT added 6 signals (5 losses).
        
        Returns: {'confirmed': True, 'corr_symbol': str, 'detail': str} or None
        """
        corr_candles = self._get_correlated_candles(symbol)
        if len(corr_candles) < 15:
            return None  # Can't check SMT without correlated data

        corr_symbol = self._get_correlated_pair(symbol)
        recent_corr = corr_candles[-15:] if len(corr_candles) >= 15 else corr_candles

        sweep_dir = sweep_info['direction']
        sweep_level = sweep_info['level']

        if sweep_dir == 'long':
            # Our pair swept a LOW → check if correlated pair also made a new low
            our_low = min(c['low'] for c in candles_5m[-15:])
            corr_low = min(c['low'] for c in recent_corr)
            # Correlated pair should NOT have made a lower low in the same window
            # We check: did correlated pair's recent low hold above its prior swing low?
            corr_prior_lows = [c['low'] for c in corr_candles[-30:-15]] if len(corr_candles) >= 30 else []
            if corr_prior_lows:
                corr_prior_swing_low = min(corr_prior_lows)
                if corr_low > corr_prior_swing_low:
                    return {
                        'confirmed': True,
                        'corr_symbol': corr_symbol,
                        'detail': f"{symbol} swept low but {corr_symbol} held → bullish SMT",
                    }
        else:  # short
            # Our pair swept a HIGH → check if correlated pair also made a new high
            corr_high = max(c['high'] for c in recent_corr)
            corr_prior_highs = [c['high'] for c in corr_candles[-30:-15]] if len(corr_candles) >= 30 else []
            if corr_prior_highs:
                corr_prior_swing_high = max(corr_prior_highs)
                if corr_high < corr_prior_swing_high:
                    return {
                        'confirmed': True,
                        'corr_symbol': corr_symbol,
                        'detail': f"{symbol} swept high but {corr_symbol} held → bearish SMT",
                    }

        return None

    # --- Inverted FVG (iFVG) ---

    def find_ifvgs(self, candles: List[dict]) -> List[dict]:
        """
        Find Inverted Fair Value Gaps (iFVGs).
        
        iFVG lifecycle:
        1. A regular FVG is created (gap between candle 1 high and candle 3 low)
        2. Price later TRADES THROUGH the FVG (fills/inverts it)
        3. The FVG now acts as support/resistance from the OTHER side
        
        A bullish FVG that gets traded through becomes bearish iFVG (resistance)
        A bearish FVG that gets traded through becomes bullish iFVG (support)
        
        Returns list of dicts with keys: top, bottom, direction, original_direction, timestamp
        """
        if len(candles) < 20:
            return []

        # Step 1: Find all FVGs in the data
        all_fvgs = []
        for i in range(2, len(candles)):
            prev = candles[i - 2]
            curr = candles[i - 1]
            nxt = candles[i]

            # Bullish FVG: gap up (candle 1 high < candle 3 low)
            if prev['high'] < nxt['low']:
                all_fvgs.append({
                    'top': nxt['low'],
                    'bottom': prev['high'],
                    'direction': 'bullish',
                    'timestamp': curr['timestamp'],
                    'created_idx': i,
                })
            # Bearish FVG: gap down (candle 1 low > candle 3 high)
            elif prev['low'] > nxt['high']:
                all_fvgs.append({
                    'top': prev['low'],
                    'bottom': nxt['high'],
                    'direction': 'bearish',
                    'timestamp': curr['timestamp'],
                    'created_idx': i,
                })

        # Step 2: Check which FVGs have been traded through (inverted)
        ifvgs = []
        for fvg in all_fvgs:
            created_idx = fvg['created_idx']
            traded_through = False

            # Check candles AFTER the FVG was created
            for j in range(created_idx + 1, len(candles)):
                c = candles[j]
                if fvg['direction'] == 'bullish':
                    # Bullish FVG traded through = price dropped below the FVG bottom
                    if c['close'] < fvg['bottom']:
                        traded_through = True
                        break
                else:
                    # Bearish FVG traded through = price closed above the FVG top
                    if c['close'] > fvg['top']:
                        traded_through = True
                        break

            if traded_through:
                # Invert the direction: bullish FVG → bearish iFVG (now resistance)
                inverted_dir = 'bearish' if fvg['direction'] == 'bullish' else 'bullish'
                ifvgs.append({
                    'top': fvg['top'],
                    'bottom': fvg['bottom'],
                    'direction': inverted_dir,  # Inverted direction
                    'original_direction': fvg['direction'],
                    'timestamp': fvg['timestamp'],
                })

        return ifvgs[-10:]  # Keep last 10

    def price_at_ifvg(self, candles: List[dict], direction: str) -> Optional[dict]:
        """
        Check if current price is at a relevant iFVG for the given direction.
        
        For LONG: price should be at a bullish iFVG (support) — was bearish, got inverted
        For SHORT: price should be at a bearish iFVG (resistance) — was bullish, got inverted
        """
        ifvgs = self.find_ifvgs(candles)
        if not ifvgs:
            return None

        current_price = candles[-1]['close']
        pip_value = self.get_pip_value()
        tolerance = 5 * pip_value

        for ifvg in reversed(ifvgs):  # Most recent first
            if ifvg['direction'] != ('bullish' if direction == 'long' else 'bearish'):
                continue
            if ifvg['bottom'] - tolerance <= current_price <= ifvg['top'] + tolerance:
                return ifvg

        return None

    # --- 79% Fib Extension ---

    def calc_79_extension(self, sweep_info: dict, candles_5m: List[dict],
                           direction: str) -> Optional[dict]:
        """
        Calculate the 79% (0.79) Fib retracement of the sweep swing.
        
        The sweep creates a swing (from the start of the move to the sweep wick).
        We measure 79% retracement of that swing for precision entry.
        
        For LONG (swept low):
            Swing high = high before the sweep, Swing low = sweep wick
            79% entry = sweep_low + (swing_high - sweep_low) * 0.79
        For SHORT (swept high):
            Swing low = low before the sweep, Swing high = sweep wick
            79% entry = sweep_high - (sweep_high - swing_low) * 0.79
        
        Returns: {'level_79': float, 'swing_high': float, 'swing_low': float,
                  'eq_level': float (50%)} or None
        """
        if len(candles_5m) < 15:
            return None

        recent = candles_5m[-20:] if len(candles_5m) >= 20 else candles_5m

        if direction == 'long':
            swing_low = sweep_info.get('sweep_wick', sweep_info['level'])
            # Find the swing high BEFORE the sweep (the top of the range)
            swing_high = max(c['high'] for c in recent[:-3]) if len(recent) > 3 else max(c['high'] for c in recent)
            if swing_high <= swing_low:
                return None
            rng = swing_high - swing_low
            level_79 = swing_low + rng * 0.79
            eq_level = swing_low + rng * 0.50
        else:  # short
            swing_high = sweep_info.get('sweep_wick', sweep_info['level'])
            # Find the swing low BEFORE the sweep
            swing_low = min(c['low'] for c in recent[:-3]) if len(recent) > 3 else min(c['low'] for c in recent)
            if swing_high <= swing_low:
                return None
            rng = swing_high - swing_low
            level_79 = swing_high - rng * 0.79
            eq_level = swing_high - rng * 0.50

        return {
            'level_79': level_79,
            'swing_high': swing_high,
            'swing_low': swing_low,
            'eq_level': eq_level,
            'range': rng,
        }

    def price_at_79(self, current_price: float, fib_data: dict, direction: str,
                     symbol: str) -> bool:
        """Check if price is near the 79% level (within 5 pips / $3 for gold)."""
        pip_value = self.get_pip_value(symbol)
        is_gold = symbol in ['XAUUSD', 'XAU_USD', 'GOLD']
        tolerance = 3.00 if is_gold else 5 * pip_value
        return abs(current_price - fib_data['level_79']) <= tolerance

    def price_at_eq(self, current_price: float, fib_data: dict, symbol: str) -> bool:
        """Check if price is near equilibrium (50% level)."""
        pip_value = self.get_pip_value(symbol)
        is_gold = symbol in ['XAUUSD', 'XAU_USD', 'GOLD']
        tolerance = 3.00 if is_gold else 5 * pip_value
        return abs(current_price - fib_data['eq_level']) <= tolerance

    # --- Draws on Liquidity (DOL) TP ---

    def find_draws_on_liquidity(self, candles_5m: List[dict], candles_1h: List[dict],
                                 direction: str, symbol: str) -> Optional[float]:
        """
        Legacy wrapper — returns nearest DOL target (for Option 5 backward compat).
        Now calls the enhanced find_dol_targets() under the hood.
        """
        targets = self.find_dol_targets(candles_5m, candles_1h, direction, symbol)
        if not targets:
            return None
        # Return the nearest target (first one, sorted by distance)
        return targets[0]['price']

    def find_dol_targets(self, candles_5m: List[dict], candles_1h: List[dict],
                          direction: str, symbol: str,
                          entry_price: float = None, sl_distance: float = None) -> List[Dict]:
        """
        Find ALL draws on liquidity targets scored by confluence.
        
        Each target gets a confluence score based on how many independent
        sources confirm it as a liquidity magnet. Higher score = higher
        probability that price will reach it.
        
        Sources (each contributes +1 to score):
          1. Session levels (prev_asia, prev_london, prev_ny H/L)
          2. Equal highs/lows (liquidity pools from 1H candles)
          3. Unfilled FVGs (price tends to fill gaps)
          4. 4H swing levels (major structure)
          5. Previous day high/low (institutional reference)
        
        Targets within merge_tolerance are merged (scores combined).
        
        Returns: List of {'price': float, 'score': int, 'sources': [str], 'rr': float}
                 Sorted by score DESC, then by distance ASC.
                 Empty list if no DOL found.
        """
        import logging
        _log = logging.getLogger('strategy')
        pip_value = self.get_pip_value(symbol)
        is_gold = symbol in ['XAUUSD', 'XAU_USD', 'GOLD']
        current_price = entry_price or candles_5m[-1]['close']
        min_dist = 5 * pip_value  # Minimum distance to consider a target
        merge_tolerance = 5 * pip_value if not is_gold else 5.0  # Merge targets within 5 pips / $5
        
        # Raw candidates: (price, source_name)
        raw = []

        # --- SOURCE 1: Session levels ---
        sess = self._session_levels.get(symbol, {})
        for sess_name in ['prev_asia', 'prev_london', 'prev_ny', 'asia', 'london', 'ny']:
            s = sess.get(sess_name)
            if not s:
                continue
            if direction == 'long' and s['high'] > current_price + min_dist:
                raw.append((s['high'], f'session_{sess_name}_high'))
            elif direction == 'short' and s['low'] < current_price - min_dist:
                raw.append((s['low'], f'session_{sess_name}_low'))

        # --- SOURCE 2: Equal highs/lows (1H liquidity pools) ---
        if len(candles_1h) >= 20:
            eq_tolerance = 3 * pip_value
            highs = [c['high'] for c in candles_1h[-20:]]
            lows = [c['low'] for c in candles_1h[-20:]]

            # Equal highs
            seen_eq_h = set()
            for i in range(len(highs)):
                if i in seen_eq_h:
                    continue
                cluster = [highs[i]]
                indices = [i]
                for j in range(i + 1, len(highs)):
                    if abs(highs[j] - highs[i]) < eq_tolerance:
                        cluster.append(highs[j])
                        indices.append(j)
                if len(cluster) >= 2:
                    seen_eq_h.update(indices)
                    avg = sum(cluster) / len(cluster)
                    touch_count = len(cluster)
                    if direction == 'long' and avg > current_price + min_dist:
                        # More touches = stronger pool, add extra entries for scoring
                        raw.append((avg, f'equal_highs_{touch_count}x'))
                        if touch_count >= 3:
                            raw.append((avg, 'equal_highs_strong'))  # Bonus for 3+ touches

            # Equal lows
            seen_eq_l = set()
            for i in range(len(lows)):
                if i in seen_eq_l:
                    continue
                cluster = [lows[i]]
                indices = [i]
                for j in range(i + 1, len(lows)):
                    if abs(lows[j] - lows[i]) < eq_tolerance:
                        cluster.append(lows[j])
                        indices.append(j)
                if len(cluster) >= 2:
                    seen_eq_l.update(indices)
                    avg = sum(cluster) / len(cluster)
                    touch_count = len(cluster)
                    if direction == 'short' and avg < current_price - min_dist:
                        raw.append((avg, f'equal_lows_{touch_count}x'))
                        if touch_count >= 3:
                            raw.append((avg, 'equal_lows_strong'))

        # --- SOURCE 3: Unfilled FVGs ---
        fvgs = self.find_fvgs(candles_5m)
        for fvg in fvgs:
            mid = (fvg.top + fvg.bottom) / 2
            if direction == 'long' and fvg.direction == 'bearish' and mid > current_price + min_dist:
                raw.append((mid, 'unfilled_fvg'))
            elif direction == 'short' and fvg.direction == 'bullish' and mid < current_price - min_dist:
                raw.append((mid, 'unfilled_fvg'))

        # --- SOURCE 4: 4H swing levels (major structure) ---
        candles_4h = self.mtf_data.get('4H', []) if self.mtf_data else []
        if len(candles_4h) >= 10:
            swing_4h = self._find_swing_levels(candles_4h, lookback=min(20, len(candles_4h)))
            for lvl in swing_4h:
                if direction == 'long' and lvl['side'] == 'high' and lvl['level'] > current_price + min_dist:
                    raw.append((lvl['level'], '4h_swing_high'))
                elif direction == 'short' and lvl['side'] == 'low' and lvl['level'] < current_price - min_dist:
                    raw.append((lvl['level'], '4h_swing_low'))

        # --- SOURCE 5: Previous day high/low ---
        if len(candles_1h) >= 24:
            # Use last 24 1H candles as proxy for previous day range
            prev_day_candles = candles_1h[-48:-24] if len(candles_1h) >= 48 else candles_1h[:24]
            if prev_day_candles:
                prev_day_high = max(c['high'] for c in prev_day_candles)
                prev_day_low = min(c['low'] for c in prev_day_candles)
                if direction == 'long' and prev_day_high > current_price + min_dist:
                    raw.append((prev_day_high, 'prev_day_high'))
                elif direction == 'short' and prev_day_low < current_price - min_dist:
                    raw.append((prev_day_low, 'prev_day_low'))

        if not raw:
            return []

        # --- MERGE nearby targets and compute confluence scores ---
        # Sort by price
        raw.sort(key=lambda x: x[0])
        
        merged = []  # List of {'price': float, 'score': int, 'sources': [str]}
        
        for price, source in raw:
            # Check if this target is close to an existing merged target
            found = False
            for m in merged:
                if abs(m['price'] - price) <= merge_tolerance:
                    # Merge: average the price, add the source
                    n = len(m['sources'])
                    m['price'] = (m['price'] * n + price) / (n + 1)  # Weighted average
                    m['sources'].append(source)
                    m['score'] += 1
                    found = True
                    break
            if not found:
                merged.append({
                    'price': price,
                    'score': 1,
                    'sources': [source],
                })
        
        # --- Calculate RR for each target ---
        for t in merged:
            if sl_distance and sl_distance > 0:
                tp_distance = abs(t['price'] - current_price)
                t['rr'] = round(tp_distance / sl_distance, 1)
            else:
                t['rr'] = 0.0
        
        # --- Sort: score DESC, then distance ASC (nearest high-score first) ---
        merged.sort(key=lambda t: (-t['score'], abs(t['price'] - current_price)))
        
        _log.info(
            f"🎯 [{symbol}] DOL targets ({direction}): "
            + ", ".join(
                f"{t['price']:.5f} (score={t['score']}, RR={t['rr']}, src={'+'.join(t['sources'][:3])})"
                for t in merged[:5]
            )
        )
        
        return merged

    # --- Option 5: Full ICT Sweep → Confirm → Continue → Entry → DOL ---

    def _is_active_session(self, timestamp: int) -> Tuple[bool, str]:
        """
        Check if a sweep happened during an active session or during premarket/off-session.
        Active = London or NY kill zones. Off = Asia or gaps between sessions.
        
        Returns: (is_active, session_name)
        """
        hour = datetime.fromtimestamp(timestamp, tz=timezone.utc).hour
        if 7 <= hour < 10:
            return True, 'london_open'
        if 9 <= hour < 12:
            return True, 'london'
        if 12 <= hour < 15:
            return True, 'ny_open'
        if 15 <= hour < 17:
            return True, 'ny'
        # Off-session
        if 0 <= hour < 7:
            return False, 'asian'
        return False, 'late_session'

    def try_option_5(self, candles: List[dict], symbol: str) -> Optional[Dict]:
        """
        Option 5: Full ICT Model — Sweep → Confirm → Continue → Enter → DOL TP
        
        FLOW:
        Step 1: Liquidity sweep (1H / 4H / session H/L)
        Step 2: 5M confirmations — BOS + iFVG + SMT divergence + 79% extension
                 Need at least 3 of 4 to confirm
        Step 2b: IF the sweep is off-session (Asia / premarket) →
                 require extra continuation confirmation
        Step 3: 5M continuation — EQ (50%) or FVG or (if 2b) SMT divergence
        Step 4: 1M confirmation (using 5M as proxy since yfinance 1M is limited)
                 — BOS on last few 5M candles
        Step 5: Enter at current price
        Step 6: Target = draws on liquidity (session H/L, equal H/L, unfilled FVGs)
        
        This is the most sophisticated setup — high quality, fewer signals, higher WR.
        """
        import logging
        _log = logging.getLogger('strategy')
        confirmations = []

        # Get multi-timeframe candles
        candles_5m = candles
        candles_1h = self.get_htf_candles(60)
        candles_4h = self.get_htf_candles(240)

        if len(candles_5m) < 50 or len(candles_1h) < 24:
            self._last_rejection_reasons.append("Opt5: Insufficient MTF data")
            return None

        # ====== STEP 1: LIQUIDITY SWEEP ======
        # Compute session levels first
        self.compute_session_levels(candles_1h, symbol)

        sweep_info = self.detect_htf_liquidity_sweep(candles_5m, candles_1h, candles_4h, symbol)
        if not sweep_info:
            # NO fallback to equal H/L — backtest proved those are 20% WR vs 43.8% for structured sweeps
            self._last_rejection_reasons.append("Opt5: No structured sweep (session/1H/4H levels only)")
            return None

        direction = sweep_info['direction']

        # Sweep level dedup: don't re-try the same sweep level in the same direction
        # Prevents hammering 4x on the same 1H swing low when market is trending against us
        pip_value = self.get_pip_value(symbol)
        dedup_tolerance = 30 * pip_value  # Within 30 pips = same level
        dedup_expiry = 24 * 3600  # 24 hours — after that, level is fresh again
        last = self._last_sweep_signal.get(symbol)
        if last and last['direction'] == direction:
            # Check time expiry
            current_ts = candles_5m[-1].get('timestamp', 0)
            last_ts = last.get('timestamp_epoch', 0)
            if (current_ts - last_ts) < dedup_expiry:
                if abs(sweep_info['level'] - last['level']) < dedup_tolerance:
                    self._last_rejection_reasons.append(
                        f"Opt5: Same sweep level already signaled ({sweep_info['level_name']} ~{sweep_info['level']:.5f})")
                    return None

        confirmations.append(f"SWEEP_{sweep_info.get('level_name', 'unknown').upper()}")

        # Determine if sweep happened in an active session
        current_timestamp = candles_5m[-1]['timestamp']
        is_active, session_name = self._is_active_session(current_timestamp)

        # ====== STEP 2: 5M CONFIRMATIONS (need 3/4) ======
        confirm_count = 0

        # 2a. BOS (Break of Structure)
        has_bos = self.check_bos(candles_5m, direction)
        if has_bos:
            confirmations.append("BOS")
            confirm_count += 1
            self._last_bos_found = True

        # 2b. iFVG (Inverted Fair Value Gap)
        ifvg = self.price_at_ifvg(candles_5m, direction)
        if ifvg:
            confirmations.append("iFVG")
            confirm_count += 1

        # 2c. SMT Divergence (correlated pair doesn't confirm the sweep)
        smt = self.detect_smt_divergence(candles_5m, symbol, sweep_info)
        if smt and smt['confirmed']:
            confirmations.append("SMT_DIVERGENCE")
            confirm_count += 1
            _log.info(f"🔀 [{symbol}] SMT: {smt['detail']}")

        # 2d. 79% Fib Extension
        fib_data = self.calc_79_extension(sweep_info, candles_5m, direction)
        current_price = candles_5m[-1]['close']
        if fib_data and self.price_at_79(current_price, fib_data, direction, symbol):
            confirmations.append("FIB_79_EXT")
            confirm_count += 1

        # ── Mandatory gates (backtest-proven) ──
        # BOS is non-negotiable: no structure break = no trade
        if not has_bos:
            self._last_rejection_reasons.append("Opt5: No BOS after sweep (mandatory)")
            return None

        # iFVG is mandatory: 30.6% WR with iFVG vs 18.8% without (backtest data)
        if not ifvg:
            self._last_rejection_reasons.append("Opt5: No iFVG at entry (mandatory — 30.6% vs 18.8% WR)")
            return None

        # FIB_79_EXT is mandatory: 34.5% WR with vs 10% without (backtest data)
        if not (fib_data and self.price_at_79(current_price, fib_data, direction, symbol)):
            self._last_rejection_reasons.append("Opt5: Price not at 79% extension (mandatory — 34.5% vs 10% WR)")
            return None

        # Need at least 3 out of 4 confirmations total
        if confirm_count < 3:
            self._last_rejection_reasons.append(
                f"Opt5: Only {confirm_count}/3 confirmations ({', '.join(confirmations)})")
            return None

        # ====== STEP 2b: OFF-SESSION FILTER ======
        # Backtest showed OFF_SESSION_MOMENTUM_OK signals were mostly losers.
        # Only allow off-session trades if SMT divergence confirms them.
        if not is_active:
            if smt and smt['confirmed']:
                confirmations.append("OFF_SESSION_SMT_OK")
                _log.info(f"⏰ [{symbol}] Opt5: Off-session ({session_name}) allowed — SMT confirmed")
            else:
                self._last_rejection_reasons.append(
                    f"Opt5: Off-session ({session_name}) — SMT required but not found")
                return None

        # ====== STEP 3: CONTINUATION (EQ / FVG / SMT) ======
        has_continuation = False

        # 3a. Price at or past equilibrium (50% of the range)
        if fib_data and self.price_at_eq(current_price, fib_data, symbol):
            confirmations.append("EQ_CONTINUATION")
            has_continuation = True

        # 3b. Price at a regular FVG in direction
        if not has_continuation:
            fvgs = self.find_fvgs(candles_5m)
            pip_value = self.get_pip_value(symbol)
            tolerance = 8 * pip_value
            for fvg in reversed(fvgs):
                expected_dir = 'bearish' if direction == 'long' else 'bullish'
                if fvg.direction == expected_dir:
                    if fvg.bottom - tolerance <= current_price <= fvg.top + tolerance:
                        confirmations.append("FVG_CONTINUATION")
                        has_continuation = True
                        break

        # 3c. If from step 2b (off-session sweep), SMT counts as continuation too
        if not has_continuation and smt and smt['confirmed']:
            confirmations.append("SMT_CONTINUATION")
            has_continuation = True

        # 3d. ChoCH as continuation fallback
        if not has_continuation:
            if self.check_choch(candles_5m, direction):
                confirmations.append("CHOCH_CONTINUATION")
                has_continuation = True

        if not has_continuation:
            self._last_rejection_reasons.append("Opt5: No continuation signal (need EQ/FVG/SMT/ChoCH)")
            return None

        # ====== STEP 4: LTF CONFIRM (5M micro-BOS as proxy for 1M) ======
        # Check the last 5 candles for a micro BOS in direction
        micro_confirmed = False
        last_candles = candles_5m[-6:]
        if len(last_candles) >= 4:
            if direction == 'long':
                # Micro bullish: recent close above a prior high
                prior_high = max(c['high'] for c in last_candles[:-2])
                if last_candles[-1]['close'] > prior_high or last_candles[-2]['close'] > prior_high:
                    micro_confirmed = True
            else:
                prior_low = min(c['low'] for c in last_candles[:-2])
                if last_candles[-1]['close'] < prior_low or last_candles[-2]['close'] < prior_low:
                    micro_confirmed = True

        if not micro_confirmed:
            self._last_rejection_reasons.append("Opt5: No micro-BOS on 5M (LTF entry trigger)")
            return None
        confirmations.append("MICRO_BOS")

        # ====== STEP 5: ENTRY ======
        entry_price = current_price

        # ====== STEP 6: DOL-BASED TP ======
        dol_tp = self.find_draws_on_liquidity(candles_5m, candles_1h, direction, symbol)

        _log.info(
            f"✅ [{symbol}] Option 5 HIT: {direction} | "
            f"Sweep: {sweep_info['level_name']} | "
            f"Confirms: {', '.join(confirmations)} | "
            f"DOL TP: {dol_tp:.5f}" if dol_tp else
            f"✅ [{symbol}] Option 5 HIT: {direction} | "
            f"Sweep: {sweep_info['level_name']} | "
            f"Confirms: {', '.join(confirmations)} | DOL TP: fallback R:R"
        )

        # Record this sweep level so we don't re-signal on it
        self._last_sweep_signal[symbol] = {
            'level': sweep_info['level'],
            'direction': direction,
            'level_name': sweep_info.get('level_name', ''),
            'timestamp': candles[-1].get('time', ''),
            'timestamp_epoch': candles[-1].get('timestamp', 0),
        }

        return {
            'setup_type': SetupType.OPTION_5,
            'direction': direction,
            'confirmations': confirmations,
            'htf_trend': self.determine_htf_trend(candles, 240),
            'has_liquidity_sweep': True,
            'has_bos': has_bos,
            'has_choch': 'CHOCH_CONTINUATION' in confirmations,
            'has_fib_confluence': 'FIB_79_EXT' in confirmations,
            'asian_sweep': 'asia' in sweep_info.get('level_name', ''),
            'order_block': None,
            'fvg': None,
            'htf_zone': None,
            'sweep_info': sweep_info,
            'smt_info': smt,
            'fib_data': fib_data,
            'dol_tp': dol_tp,
        }

    # ====================================================================
    # OPTION 6: CORRECTED CONSOLIDATION OF OPTIONS 2 & 3
    # Zone + OB/FVG + Fib 79% + Liquidity Sweep + BOS/ChoCH
    #
    # Fixes applied vs original Options 2/3:
    #   - HTF zone detection: require minimum body size + mitigation check
    #   - OB quality gate: minimum strength threshold + freshness
    #   - FVG size filter: reject micro-gaps (< 2 pips)
    #   - Fib 79%: proper swing detection (swing points, not raw range)
    #   - Liquidity sweep: MANDATORY (was completely missing from Opt 2/3)
    #   - BOS or ChoCH: at least one structural confirmation required
    # ====================================================================

    def _find_validated_htf_zones(self, candles: List[dict], timeframe: int = 240) -> List[HTFZone]:
        """
        IMPROVED HTF zone detection (fixes Option 2's loose zones).
        
        Changes vs find_htf_zones():
        1. Candle body must be >= avg body * 1.5 (significant move)
        2. Zone is only valid if NOT yet mitigated (price hasn't fully
           retraced through it after creation)
        3. Only keep the 3 most recent unmitigated zones
        """
        if self.mtf_data:
            candles_htf = self.get_htf_candles(timeframe)
        else:
            candles_htf = self.filters.get_timeframe_data(candles, timeframe)

        if len(candles_htf) < 30:
            return []

        recent = candles_htf[-30:]
        avg_body = sum(abs(c['close'] - c['open']) for c in recent) / len(recent)
        min_body = avg_body * 1.5  # Significant candle requirement

        zones: List[HTFZone] = []
        for i in range(len(recent) - 5):
            candle = recent[i]
            body = abs(candle['close'] - candle['open'])
            if body < min_body:
                continue  # Skip weak candles — this is the key fix

            # Supply zone: strong bearish candle → next 3 candles all close below
            if candle['close'] < candle['open']:
                next_3 = recent[i+1:i+4]
                if len(next_3) >= 3 and all(c['close'] < candle['low'] for c in next_3):
                    # Mitigation check: has price come back ABOVE zone high after creation?
                    mitigated = any(c['close'] > candle['high'] for c in recent[i+4:])
                    if not mitigated:
                        zones.append(HTFZone(
                            high=candle['high'],
                            low=candle['open'],
                            timeframe=f"{timeframe}M",
                            zone_type='supply'
                        ))

            # Demand zone: strong bullish candle → next 3 candles all close above
            elif candle['close'] > candle['open']:
                next_3 = recent[i+1:i+4]
                if len(next_3) >= 3 and all(c['close'] > candle['high'] for c in next_3):
                    mitigated = any(c['close'] < candle['low'] for c in recent[i+4:])
                    if not mitigated:
                        zones.append(HTFZone(
                            high=candle['close'],
                            low=candle['low'],
                            timeframe=f"{timeframe}M",
                            zone_type='demand'
                        ))

        return zones[-3:]  # Keep 3 most recent unmitigated zones

    def _find_quality_order_blocks(self, candles: List[dict]) -> List[OrderBlock]:
        """
        IMPROVED OB detection (fixes Option 3's false positives).
        
        Changes vs find_order_blocks():
        1. Minimum strength threshold (displacement move must be >= 2x avg body)
        2. Freshness check — OB must not have been tested more than once
        3. Only return top 3 OBs by strength
        """
        candles_5m = candles
        if self.mtf_data:
            candles_5m = self.get_htf_candles(5) or candles

        if len(candles_5m) < 20:
            return []

        avg_body = sum(abs(c['close'] - c['open']) for c in candles_5m[-30:]) / min(30, len(candles_5m))
        min_displacement = avg_body * 2.0  # Stricter than the 1.5x in check_bos

        order_blocks: List[OrderBlock] = []
        start_idx = max(2, len(candles_5m) - 30)

        for i in range(start_idx, len(candles_5m) - 1):
            curr = candles_5m[i]
            next_c = candles_5m[i + 1]
            displacement = abs(next_c['close'] - next_c['open'])

            if displacement < min_displacement:
                continue  # Weak move → not a real OB

            # Bullish OB: bearish candle → strong bullish break above
            if (curr['close'] < curr['open'] and
                next_c['close'] > next_c['open'] and
                next_c['close'] > curr['high']):

                # Freshness: count how many times price re-entered this zone
                tests = sum(1 for c in candles_5m[i+2:] if c['low'] <= curr['high'] and c['close'] > curr['low'])
                if tests <= 1:  # Max 1 retest
                    strength = displacement / avg_body
                    order_blocks.append(OrderBlock(
                        high=curr['high'], low=curr['low'],
                        timestamp=curr['timestamp'], direction='bullish',
                        timeframe='5M', strength=strength
                    ))

            # Bearish OB: bullish candle → strong bearish break below
            elif (curr['close'] > curr['open'] and
                  next_c['close'] < next_c['open'] and
                  next_c['close'] < curr['low']):

                tests = sum(1 for c in candles_5m[i+2:] if c['high'] >= curr['low'] and c['close'] < curr['high'])
                if tests <= 1:
                    strength = displacement / avg_body
                    order_blocks.append(OrderBlock(
                        high=curr['high'], low=curr['low'],
                        timestamp=curr['timestamp'], direction='bearish',
                        timeframe='5M', strength=strength
                    ))

        return sorted(order_blocks, key=lambda x: x.strength, reverse=True)[:3]

    def _find_quality_fvgs(self, candles: List[dict]) -> List[FVG]:
        """
        IMPROVED FVG detection (fixes micro-gap false positives).
        
        Changes vs find_fvgs():
        1. Minimum gap size of 2 pips (rejects noise gaps)
        2. Only keep gaps that are still OPEN (not yet filled)
        """
        candles_5m = candles
        if self.mtf_data:
            candles_5m = self.get_htf_candles(5) or candles

        if len(candles_5m) < 10:
            return []

        pip_value = self.get_pip_value()
        min_gap = 2 * pip_value  # 2 pips minimum gap

        fvgs: List[FVG] = []
        for i in range(2, len(candles_5m)):
            prev = candles_5m[i - 2]
            next_c = candles_5m[i]

            # Bullish FVG
            if prev['high'] < next_c['low']:
                gap_size = next_c['low'] - prev['high']
                if gap_size >= min_gap:
                    # Check if still open (not filled by subsequent candles)
                    filled = any(c['low'] <= prev['high'] for c in candles_5m[i+1:])
                    if not filled:
                        fvgs.append(FVG(
                            top=next_c['low'], bottom=prev['high'],
                            timestamp=candles_5m[i-1]['timestamp'], direction='bullish'
                        ))

            # Bearish FVG
            elif prev['low'] > next_c['high']:
                gap_size = prev['low'] - next_c['high']
                if gap_size >= min_gap:
                    filled = any(c['high'] >= prev['low'] for c in candles_5m[i+1:])
                    if not filled:
                        fvgs.append(FVG(
                            top=prev['low'], bottom=next_c['high'],
                            timestamp=candles_5m[i-1]['timestamp'], direction='bearish'
                        ))

        return fvgs[-8:]

    def _find_proper_fib_79(self, candles: List[dict], direction: str) -> Optional[float]:
        """
        IMPROVED 79% Fib calculation (fixes Option 3's crude swing detection).
        
        Instead of using raw 30-candle high/low (which catches noise), this
        finds actual swing points using 3-bar pivot logic, then calculates
        the 79% retracement between the most recent swing high and swing low.
        """
        if len(candles) < 20:
            return None

        recent = candles[-40:] if len(candles) >= 40 else candles

        # Find swing highs and lows using 3-bar pivot
        swing_highs = []
        swing_lows = []
        for i in range(2, len(recent) - 2):
            if (recent[i]['high'] >= recent[i-1]['high'] and
                recent[i]['high'] >= recent[i-2]['high'] and
                recent[i]['high'] >= recent[i+1]['high'] and
                recent[i]['high'] >= recent[i+2]['high']):
                swing_highs.append(recent[i]['high'])

            if (recent[i]['low'] <= recent[i-1]['low'] and
                recent[i]['low'] <= recent[i-2]['low'] and
                recent[i]['low'] <= recent[i+1]['low'] and
                recent[i]['low'] <= recent[i+2]['low']):
                swing_lows.append(recent[i]['low'])

        if not swing_highs or not swing_lows:
            return None

        # Use most recent swing high and swing low
        sh = swing_highs[-1]
        sl = swing_lows[-1]

        if sh <= sl:
            return None

        if direction == 'long':
            # For longs: 79% retracement from high → buying in the discount
            return sh - (sh - sl) * 0.79
        else:
            # For shorts: 79% retracement from low → selling in the premium
            return sl + (sh - sl) * 0.79

    def try_option_6(self, candles: List[dict], symbol: str) -> Optional[Dict]:
        """
        Option 6: Zone + OB/FVG + Fib 79% + Sweep Confirmation
        
        CORRECTED consolidation of Options 2 & 3 — fixes every weakness:
        
        Required (ALL mandatory):
        1. HTF Zone tap — price at a VALIDATED 4H/1H supply or demand zone
        2. OB or FVG at zone — quality-filtered OB or FVG overlapping the zone
        3. 79% Fib confluence — proper swing-based Fib within 0.5% of entry
        4. Liquidity sweep — MUST have swept nearby liquidity (the missing piece)
        5. BOS or ChoCH — at least one structural confirmation
        
        Bonus (not required):
        - HTF trend alignment
        - Engulfing at zone
        - Both BOS and ChoCH
        
        Why this works when Opt 2/3 didn't:
        - Option 2 had no sweep, loose zones, trivial ChoCH → 0% WR
        - Option 3 had no sweep, bad OBs, wrong Fib swing → 20% WR
        - This adds the sweep gate + tightens every detection algorithm
        """
        import logging
        _log = logging.getLogger('strategy')
        confirmations = []

        current_price = candles[-1]['close']
        pip_value = self.get_pip_value()

        # ====== STEP 1: HTF ZONE TAP (validated zones only) ======
        htf_zones_4h = self._find_validated_htf_zones(candles, 240)
        htf_zones_1h = self._find_validated_htf_zones(candles, 60)
        all_zones = htf_zones_4h + htf_zones_1h

        if not all_zones:
            self._last_rejection_reasons.append("Opt6: No validated HTF zones")
            return None

        tapped_zone = None
        zone_buffer = 5 * pip_value  # Small buffer for zone tap
        for zone in all_zones:
            if (zone.low - zone_buffer) <= current_price <= (zone.high + zone_buffer):
                tapped_zone = zone
                break

        if not tapped_zone:
            self._last_rejection_reasons.append("Opt6: Price not at HTF zone")
            return None

        direction = 'long' if tapped_zone.zone_type == 'demand' else 'short'
        confirmations.append(f"HTF_ZONE_{tapped_zone.timeframe}")

        # ====== STEP 2: QUALITY OB OR FVG AT ZONE ======
        quality_obs = self._find_quality_order_blocks(candles)
        quality_fvgs = self._find_quality_fvgs(candles)

        ob_tolerance = 10 * pip_value
        entry_ob = None
        entry_fvg = None

        # Check for OB overlapping with HTF zone
        expected_ob_dir = 'bullish' if direction == 'long' else 'bearish'
        for ob in quality_obs:
            if ob.direction == expected_ob_dir:
                # OB must overlap the HTF zone AND price must be at the OB
                ob_overlaps_zone = not (ob.high < tapped_zone.low or ob.low > tapped_zone.high)
                price_at_ob = (ob.low - ob_tolerance) <= current_price <= (ob.high + ob_tolerance)
                if ob_overlaps_zone and price_at_ob:
                    entry_ob = ob
                    confirmations.append("QUALITY_OB")
                    break

        # Check for FVG overlapping with HTF zone (if no OB found)
        if not entry_ob:
            expected_fvg_dir = 'bearish' if direction == 'long' else 'bullish'
            for fvg in quality_fvgs:
                if fvg.direction == expected_fvg_dir:
                    fvg_overlaps_zone = not (fvg.top < tapped_zone.low or fvg.bottom > tapped_zone.high)
                    price_at_fvg = (fvg.bottom - ob_tolerance) <= current_price <= (fvg.top + ob_tolerance)
                    if fvg_overlaps_zone and price_at_fvg:
                        entry_fvg = fvg
                        confirmations.append("QUALITY_FVG")
                        break

        if not entry_ob and not entry_fvg:
            self._last_rejection_reasons.append("Opt6: No quality OB/FVG at HTF zone")
            return None

        # ====== STEP 3: 79% FIB CONFLUENCE (proper swing-based) ======
        fib_79_level = self._find_proper_fib_79(candles, direction)

        if fib_79_level is None:
            self._last_rejection_reasons.append("Opt6: Could not compute Fib (no clear swings)")
            return None

        fib_tolerance = 0.005  # 0.5% tolerance
        if abs(current_price - fib_79_level) / fib_79_level > fib_tolerance:
            self._last_rejection_reasons.append(
                f"Opt6: Price not at 79% Fib ({current_price:.5f} vs {fib_79_level:.5f})")
            return None

        confirmations.append("FIB_79")

        # ====== STEP 4: LIQUIDITY SWEEP (mandatory — the key missing piece) ======
        has_sweep = False
        sweep_type = None

        # Try session/Asian sweep first
        sweep_found, sweep_dir = self.check_liquidity_sweep(candles, symbol)
        if sweep_found:
            if (direction == 'long' and sweep_dir == 'low') or (direction == 'short' and sweep_dir == 'high'):
                has_sweep = True
                sweep_type = 'SESSION_SWEEP'

        # Try 5M liquidity zone sweep
        if not has_sweep:
            liq_zone = self.find_5m_liquidity_zone(candles)
            if liq_zone and liq_zone.get('swept'):
                if (direction == 'long' and liq_zone['type'] == 'low') or \
                   (direction == 'short' and liq_zone['type'] == 'high'):
                    has_sweep = True
                    sweep_type = '5M_LIQ_SWEEP'

        if not has_sweep:
            self._last_rejection_reasons.append("Opt6: No liquidity sweep (mandatory for this setup)")
            return None

        confirmations.append(sweep_type)

        # ====== STEP 5: STRUCTURAL CONFIRMATION (BOS or ChoCH) ======
        has_bos = self.check_bos(candles, direction)
        has_choch = self.check_choch(candles, direction)

        if has_bos:
            confirmations.append("BOS")
        if has_choch:
            confirmations.append("CHOCH")

        if not has_bos and not has_choch:
            self._last_rejection_reasons.append("Opt6: No BOS or ChoCH (need structural shift)")
            return None

        # ====== STEP 6: HTF TREND ALIGNMENT (MANDATORY) ======
        # Backtest data: 57% WR with HTF_ALIGNED vs 33% without (GBP)
        # On EU, nearly all losses were counter-trend — this gate is critical
        htf_trend = self.determine_htf_trend(candles, 240)
        if not ((htf_trend == TrendDirection.BULLISH and direction == 'long') or \
                (htf_trend == TrendDirection.BEARISH and direction == 'short')):
            self._last_rejection_reasons.append(
                f"Opt6: HTF trend not aligned ({htf_trend.value} vs {direction}) — mandatory filter")
            return None

        confirmations.append("HTF_ALIGNED")

        # ====== BONUS CONFIRMATIONS ======
        # Engulfing at zone (extra confidence)
        engulfing = self.detect_engulfing(candles, timeframe=15)
        if engulfing and engulfing['direction'] == direction:
            confirmations.append("ENGULFING_BONUS")

        _log.info(
            f"✅ [{symbol}] Option 6 HIT: {direction} | "
            f"Zone: {tapped_zone.zone_type} ({tapped_zone.timeframe}) | "
            f"Confirms: {', '.join(confirmations)}"
        )

        return {
            'setup_type': SetupType.OPTION_6,
            'direction': direction,
            'confirmations': confirmations,
            'htf_trend': htf_trend if htf_trend != TrendDirection.RANGING else None,
            'has_liquidity_sweep': True,
            'has_bos': has_bos,
            'has_choch': has_choch,
            'has_fib_confluence': True,
            'asian_sweep': sweep_type == 'SESSION_SWEEP',
            'order_block': entry_ob,
            'fvg': entry_fvg,
            'htf_zone': tapped_zone,
        }

    def find_sweep_level(self, candles: List[dict], direction: str, setup_type: str = None) -> float:
        """
        Find the NEAREST swing pivot for SL placement.
        
        Uses pivot detection (bar lower/higher than neighbours) to find the
        closest structural level, NOT the absolute extreme over a wide window.
        This keeps SL tight (8-15 pips) instead of anchoring to 20-30 candle extremes.
        
        For SHORT: Find the nearest swing high pivot above entry
        For LONG: Find the nearest swing low pivot below entry
        """
        if len(candles) < 10:
            return None
        
        # Lookback — kept short to find NEAREST structure
        if setup_type == 'HTF_LIQUIDITY_BOS':
            lookback = min(10, len(candles))
        elif setup_type in ('LIQ_SWEEP_ENGULF', 'ICT_SWEEP_CONFIRM'):
            lookback = min(12, len(candles))
        elif setup_type == 'ZONE_OB_FIB_SWEEP':
            lookback = min(15, len(candles))
        else:
            lookback = min(15, len(candles))
        
        recent = candles[-lookback:]
        
        # --- Pivot-based swing detection ---
        # A swing low pivot: bar whose low is lower than both neighbours
        # A swing high pivot: bar whose high is higher than both neighbours
        # We scan from MOST RECENT backward and return the NEAREST one
        
        if direction == 'long':
            # Find nearest swing low pivot (scan backward, skip last 2 bars)
            for i in range(len(recent) - 3, 0, -1):
                if recent[i]['low'] <= recent[i-1]['low'] and recent[i]['low'] <= recent[i+1]['low']:
                    return recent[i]['low']
            # Fallback: lowest of last 10 candles (not full lookback)
            return min(c['low'] for c in recent[-10:])
        else:
            # Find nearest swing high pivot (scan backward, skip last 2 bars)
            for i in range(len(recent) - 3, 0, -1):
                if recent[i]['high'] >= recent[i-1]['high'] and recent[i]['high'] >= recent[i+1]['high']:
                    return recent[i]['high']
            # Fallback: highest of last 10 candles (not full lookback)
            return max(c['high'] for c in recent[-10:])
    
    def calculate_sl_tp(self, entry: float, setup_data: Dict, candles: List[dict], 
                        symbol: str) -> Tuple[Optional[float], Optional[float], float]:
        """
        Calculate SL/TP based on ICT principles:
        - SL: Beyond the liquidity sweep level (swing high/low that was swept)
        - TP: Dynamic DOL-based targeting (all options), with floor of 1:2 forex / 1:1.5 gold
        
        DOL targets scored by confluence:
          - Session levels, equal H/L, unfilled FVGs, 4H swings, prev day H/L
          - Tier 1 (score>=3): Aim far (maximize RR)
          - Tier 2 (score==2): Moderate distance (balance)
          - Tier 3 (score==1): Nearest only (conservative)
          - No ceiling — 1:7+ is valid if the pool is strong
        
        HTF_LIQUIDITY_BOS gets tighter SL due to high confidence (95%)
        Gold uses different pip/point values than forex pairs.
        """
        import logging
        _log = logging.getLogger('strategy')
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
        # Gold: $3-5 buffer, Forex: 2-3 pips buffer (tight — pivot is already the structure)
        if is_gold:
            buffer = 3.00 if setup_type == 'HTF_LIQUIDITY_BOS' else 5.00
        elif setup_type == 'HTF_LIQUIDITY_BOS':
            buffer = 2 * pip_value  # 2 pips buffer for high-confidence forex
        else:
            buffer = 2 * pip_value  # 2 pips buffer (pivot-based SL is already precise)
        
        if is_long:
            stop_loss = sweep_level - buffer  # SL below the swept low
        else:
            stop_loss = sweep_level + buffer  # SL above the swept high
        
        # === SANITY CHECK: SL must be on correct side of entry ===
        # Long: SL must be BELOW entry | Short: SL must be ABOVE entry
        if is_long and stop_loss >= entry:
            # SL above entry for a long = invalid, use recent swing low instead
            recent_low = min(c['low'] for c in candles[-20:])
            stop_loss = recent_low - buffer
        elif not is_long and stop_loss <= entry:
            # SL below entry for a short = invalid, use recent swing high instead
            recent_high = max(c['high'] for c in candles[-20:])
            stop_loss = recent_high + buffer
        
        sl_distance = abs(entry - stop_loss)
        sl_points = sl_distance / point_value
        
        # === ATR-based dynamic minimum SL ===
        # SL must be at least 1.5x the average 5M candle range to avoid noise
        recent_ranges = [c['high'] - c['low'] for c in candles[-20:]]
        avg_range = sum(recent_ranges) / len(recent_ranges) if recent_ranges else 0
        atr_min_sl = (avg_range * 1.5) / point_value  # 1.5x ATR in points
        
        # Max SL limits - different for Gold vs Forex
        if is_gold:
            if setup_type == 'HTF_LIQUIDITY_BOS':
                max_sl_points = 2000   # $20 max for HTF_LIQUIDITY_BOS
                min_sl_points = 1000   # $10 min
            else:
                max_sl_points = 3500   # $35 max for other setups
                min_sl_points = 1500   # $15 min
        else:
            # Forex: Tighter SL = better R:R, pivot-based placement is precise
            if setup_type == 'HTF_LIQUIDITY_BOS':
                max_sl_points = 120  # 12 pips max for HTF_LIQUIDITY_BOS
                min_sl_points = 50   # 5 pips min for HTF_LIQUIDITY_BOS
            elif setup_type in ('LIQ_SWEEP_ENGULF', 'ICT_SWEEP_CONFIRM'):
                max_sl_points = 150  # 15 pips max for sweep-based setups
                min_sl_points = 70   # 7 pips min
            elif setup_type == 'ZONE_OB_FIB_SWEEP':
                max_sl_points = 170  # 17 pips max for Option 6
                min_sl_points = 70   # 7 pips min
            else:
                max_sl_points = 170  # 17 pips max for OB_FVG_FIB, HTF_ZONE_OB_CHOCH
                min_sl_points = 70   # 7 pips min
        
        # Use the LARGER of static minimum or ATR-based minimum
        effective_min = max(min_sl_points, atr_min_sl)
        
        # If SL is too tight, widen it to the minimum
        if sl_points < effective_min:
            # Instead of rejecting, widen SL to minimum distance
            min_sl_distance = effective_min * point_value
            if direction == 'long':
                stop_loss = entry - min_sl_distance
            else:
                stop_loss = entry + min_sl_distance
            sl_distance = min_sl_distance
            sl_points = effective_min
        
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
        
        # ================================================================
        # DYNAMIC TP: DOL-based targeting for ALL options
        # 
        # Strategy:
        #   1. Find all DOL targets scored by confluence
        #   2. Pick the BEST target (highest score) that meets minimum RR
        #   3. If multiple targets have same score, pick nearest (safer)
        #   4. Fall back to fixed RR floor if no DOL found
        #
        # Minimum floors (never worse than these):
        #   Gold:  1:1.5 RR
        #   Forex: 1:2.0 RR
        # No ceiling — if a strong liquidity pool is at 1:7 or beyond, take it
        # ================================================================
        
        # Minimum RR floors
        if is_gold:
            min_rr_floor = 1.5   # Gold floor
        else:
            min_rr_floor = 2.0   # Forex floor
        
        # Get 5M and 1H candles for DOL search
        candles_5m = self.mtf_data.get('5M', candles) if self.mtf_data else candles
        candles_1h = self.mtf_data.get('1H', []) if self.mtf_data else []
        
        # Find all DOL targets with confluence scores
        dol_targets = self.find_dol_targets(
            candles_5m, candles_1h, direction, symbol,
            entry_price=entry, sl_distance=sl_distance
        )
        
        take_profit = None
        chosen_target = None
        
        if dol_targets:
            # Filter targets that meet minimum RR floor
            min_tp_distance = sl_distance * min_rr_floor
            
            valid_targets = []
            for t in dol_targets:
                tp_dist = abs(t['price'] - entry)
                if tp_dist >= min_tp_distance:
                    t['rr'] = round(tp_dist / sl_distance, 1)
                    valid_targets.append(t)
            
            if valid_targets:
                # TIERED SELECTION with RR caps per tier:
                # Higher confluence = we trust the target more = allow higher RR
                # Lower confluence = cap the RR to avoid unreachable TPs
                #
                # Tier 1 (score >= 4): Extreme confluence — no RR cap
                # Tier 2 (score == 3): Strong — cap at 1:8 
                # Tier 3 (score == 2): Moderate — cap at 1:5
                # Tier 4 (score == 1): Weak — cap at 1:3
                
                tier_caps = {1: 3.0, 2: 5.0, 3: 8.0}  # score → max RR
                
                # Apply RR caps to each target based on score
                capped_targets = []
                for t in valid_targets:
                    max_rr = tier_caps.get(t['score'], 999.0)  # No cap for score >= 4
                    if t['rr'] <= max_rr:
                        capped_targets.append(t)
                    else:
                        # Cap the TP price to max_rr distance
                        capped_dist = sl_distance * max_rr
                        capped_t = dict(t)
                        if direction == 'long':
                            capped_t['price'] = entry + capped_dist
                        else:
                            capped_t['price'] = entry - capped_dist
                        capped_t['rr'] = max_rr
                        capped_t['sources'] = t['sources'] + [f'capped_from_{t["rr"]}']
                        capped_targets.append(capped_t)
                
                if capped_targets:
                    # Sort: score DESC, then nearest first (safest high-quality target)
                    capped_targets.sort(key=lambda t: (-t['score'], abs(t['price'] - entry)))
                    chosen_target = capped_targets[0]
                
                if chosen_target:
                    take_profit = chosen_target['price']
                    _log.info(
                        f"🎯 [{symbol}] Dynamic TP: {take_profit:.5f} "
                        f"(RR 1:{chosen_target['rr']}, score={chosen_target['score']}, "
                        f"sources={'+'.join(chosen_target['sources'][:4])})"
                    )
        
        # Fallback: No DOL target found or all below floor → use fixed RR floor
        if take_profit is None:
            if direction == 'long':
                take_profit = entry + (sl_distance * min_rr_floor)
            else:
                take_profit = entry - (sl_distance * min_rr_floor)
            _log.info(
                f"📐 [{symbol}] Fixed TP fallback: {take_profit:.5f} "
                f"(RR 1:{min_rr_floor}, no qualifying DOL targets)"
            )
        
        # Final sanity check — SL/TP must be on correct sides
        if direction == 'long' and (stop_loss >= entry or take_profit <= entry):
            return None, None, 0
        if direction == 'short' and (stop_loss <= entry or take_profit >= entry):
            return None, None, 0
        
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        rr_ratio = reward / risk if risk > 0 else 0
        
        # Minimum RR check - Gold: 1.3, Forex: 1.8 (slightly below floor to allow rounding)
        min_rr_check = 1.3 if is_gold else 1.8
        if rr_ratio < min_rr_check:
            return None, None, 0
        
        return stop_loss, take_profit, rr_ratio
    
    def determine_risk_percentage(self, confirmation_count: int) -> float:
        """
        Risk Management: 3 confirmations = 1.0%, 2 = 0.5%, <2 = no trade.
        """
        risk_map = {3: 1.0, 2: 0.5}
        return risk_map.get(min(confirmation_count, 3), 0.0)
    
    def can_take_trade(self, timestamp: int, symbol: str = 'EURUSD') -> bool:
        """Check daily limits (max 3 trades/day per symbol).
        
        Note: 4-hour cooldown is handled separately by check_signal_cooldown().
        """
        current_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
        
        # Reset all counters on new day
        if self.current_date != current_date:
            self.current_date = current_date
            self.trades_today = {}  # Reset all pairs
            self._save_state()
        
        # Get trade count for this specific symbol
        symbol_trades = self.trades_today.get(symbol, 0)
        
        # Allow up to 3 signals per day per pair
        # Catches London open, NY session, and late-session setups
        if symbol_trades >= 3:
            _log.debug(f"⏸️ [{symbol}] Daily limit reached ({symbol_trades}/3)")
            return False
        
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
        import logging
        _log = logging.getLogger('strategy')
        
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
        
        _log.info(f"📊 [{symbol}] Passed session/news filters — analyzing setups... (price: {base_candles[-1]['close']:.5f})")
        
        # Check if we already took a trade for this symbol today
        if not self.can_take_trade(current_timestamp, symbol):
            self._last_rejection_reasons.append(f"Already traded {symbol} today (1 per day limit)")
            return None
        
        # Determine priority based on symbol
        # Pair-specific priority (waterfall — first match wins):
        #   EURUSD: Option 4 (100% WR) → Option 1 (50% WR) → Option 5 (testing) → Option 6 (corrected Opt 2+3)
        #   GBPUSD: Option 5 (full ICT) → Option 6 (57% WR, 2.15 PF) → Option 1 (50% WR) → Option 4 (100% WR)
        #   Gold:   Option 1 → Option 4 → Option 5 → Option 6
        #
        # Legacy Options 2 & 3 are REPLACED by Option 6 (corrected consolidation).
        # Original try_option_2/try_option_3 methods kept for reference but NOT called.
        if 'XAU' in symbol:
            # Gold: HTF bias works best for trend continuation
            options = [
                self.try_option_1,                                    # HTF_LIQUIDITY_BOS (50% WR)
                lambda c, s=symbol: self.try_option_4(c, s),          # LIQ_SWEEP_ENGULF (100% WR)
                lambda c, s=symbol: self.try_option_5(c, s),          # ICT_SWEEP_CONFIRM (full ICT)
                lambda c, s=symbol: self.try_option_6(c, s),          # ZONE_OB_FIB_SWEEP (corrected Opt 2+3)
            ]
        elif 'GBP' in symbol:
            # GBP pairs: Option 5 first (full ICT, rare but high quality),
            # then Option 6 (57% WR, 2.15 PF — best confirmed backtest on GBP),
            # then Options 1 & 4 as fallback
            options = [
                lambda c, s=symbol: self.try_option_5(c, s),          # ICT_SWEEP_CONFIRM — PRIORITY for GBP
                lambda c, s=symbol: self.try_option_6(c, s),          # ZONE_OB_FIB_SWEEP (57% WR, 2.15 PF on GBP)
                self.try_option_1,                                    # HTF_LIQUIDITY_BOS (50% WR)
                lambda c, s=symbol: self.try_option_4(c, s),          # LIQ_SWEEP_ENGULF (100% WR)
                # --- LEGACY (replaced by Option 6) ---
                # lambda c, s=symbol: self.try_option_2(c, s),        # HTF_ZONE_OB_CHOCH — 0% WR (fixed in Opt 6)
                # lambda c: self.try_option_3(c),                     # OB_FVG_FIB — 20% WR (fixed in Opt 6)
            ]
        else:
            # EURUSD (and other forex): Option 4 prioritized — simple,
            # 100% WR, catches the classic Asian sweep → London engulfing
            options = [
                lambda c, s=symbol: self.try_option_4(c, s),          # LIQ_SWEEP_ENGULF — PRIORITY for EU
                self.try_option_1,                                    # HTF_LIQUIDITY_BOS (50% WR)
                lambda c, s=symbol: self.try_option_5(c, s),          # ICT_SWEEP_CONFIRM (full ICT)
                lambda c, s=symbol: self.try_option_6(c, s),          # ZONE_OB_FIB_SWEEP (corrected Opt 2+3)
                # --- LEGACY (replaced by Option 6) ---
                # lambda c, s=symbol: self.try_option_2(c, s),        # HTF_ZONE_OB_CHOCH — 0% WR (fixed in Opt 6)
                # lambda c: self.try_option_3(c),                     # OB_FVG_FIB — 20% WR (fixed in Opt 6)
            ]
        
        setup_data = None
        for option_func in options:
            try:
                setup_data = option_func(base_candles, symbol)
            except TypeError:
                # try_option_3 only takes candles, no symbol arg
                setup_data = option_func(base_candles)
            if setup_data:
                _log.info(f"✅ [{symbol}] Setup found: {setup_data['setup_type'].value} ({setup_data['direction']}) - Confirmations: {setup_data['confirmations']}")
                break
        
        if not setup_data:
            # Rejection reasons already added by try_option methods
            if not self._last_rejection_reasons:
                self._last_rejection_reasons.append("No valid ICT setup pattern")
            _log.info(f"❌ [{symbol}] No setup: {'; '.join(self._last_rejection_reasons)}")
            return None
        
        direction = setup_data['direction']
        
        # ===== NEW FILTERS =====
        
        # 1. Correlation Filter - prevent opposite signals on EU/GBP
        if self.check_correlation_conflict(symbol, direction, current_timestamp):
            self._last_rejection_reasons.append("Correlation conflict (opposite signal on related pair)")
            _log.info(f"⚠️ [{symbol}] Rejected: Correlation conflict")
            return None
        
        # 2. 15M Confirmation - ensure 15M structure agrees
        if not self.check_15m_confirmation(direction):
            self._last_rejection_reasons.append("15M structure conflicts with trade direction")
            _log.info(f"⚠️ [{symbol}] Rejected: 15M structure conflicts")
            return None
        
        # 3. 5M Entry Trigger - wait for 5M ChoCH before entry
        #    SKIP for Option 4 (engulfing IS the trigger) and for setups with 3+ confirmations
        setup_type = setup_data.get('setup_type')
        confirmation_count = len(setup_data.get('confirmations', []))
        is_engulfing_setup = (setup_type == SetupType.OPTION_4)
        has_strong_confirmations = (confirmation_count >= 3)
        
        if not is_engulfing_setup and not has_strong_confirmations:
            if not self.check_5m_entry_trigger(base_candles, direction):
                self._last_rejection_reasons.append("No 5M ChoCH confirmation yet (wait for LTF entry)")
                _log.info(f"⚠️ [{symbol}] Rejected: No 5M ChoCH trigger")
                return None
        elif not self.check_5m_entry_trigger(base_candles, direction):
            _log.info(f"ℹ️ [{symbol}] Skipping ChoCH gate: {'engulfing trigger' if is_engulfing_setup else f'{confirmation_count} confirmations'}")
        
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
        if rr_ratio >= 6.0:
            confidence += 0.05  # Extra boost for high-RR DOL targets
        if setup_data['htf_trend'] and setup_data['htf_trend'] != TrendDirection.RANGING:
            confidence += 0.05
        
        confidence = min(confidence, 0.95)
        
        # Record trade for this symbol (1 per day limit)
        self.record_trade(symbol)
        
        # Record signal time for cooldown tracking
        self._last_signal_time[symbol] = current_timestamp
        
        # Persist state to disk so cooldowns survive restarts
        self._save_state()
        
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
