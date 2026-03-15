"""
Advanced Trading Filters
Multi-timeframe, liquidity sweeps, news filters, and pattern confluence
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone, timedelta
from enum import Enum
import numpy as np


class NewsImpact(Enum):
    """News event impact levels."""
    HIGH = "high"  # NFP, FOMC, CPI, etc.
    MEDIUM = "medium"  # PPI, Retail Sales, etc.
    LOW = "low"


@dataclass
class DailyLevel:
    """Previous day high/low."""
    pdh: float  # Previous Day High
    pdl: float  # Previous Day Low
    date: datetime


@dataclass
class AsianRange:
    """Asian session range (00:00 - 09:00 UTC)."""
    high: float
    low: float
    date: datetime


@dataclass
class LiquiditySweep:
    """Detected liquidity sweep pattern."""
    timestamp: int
    sweep_type: str  # 'high' or 'low'
    sweep_price: float
    rejection_price: float
    strength: float  # 0-1


@dataclass
class CandlePattern:
    """Detected candle pattern."""
    pattern_type: str  # 'engulfing_bullish', 'engulfing_bearish', etc.
    timestamp: int
    timeframe: str
    strength: float


class AdvancedFilters:
    """Advanced filtering system for trade entries."""

    def __init__(self):
        self.previous_day_levels = {}
        self.asian_ranges = {}
        
        # High-impact news events - ONLY checked on their actual days
        # NFP: First Friday of month
        # FOMC: 8 scheduled meetings per year (check externally)
        # CPI/PPI: Mid-month (around 10th-15th)
        # For now, we'll only block NFP (first Friday) as it's the most impactful
        # Other news should be checked against an actual economic calendar API
        self.high_impact_news = {
            # Format: 'name': {'day_rule': 'first_friday' | 'mid_month' | 'specific', 'time': hour, 'duration': hours}
            'NFP': {'day_rule': 'first_friday', 'time': 13, 'duration': 2},  # First Friday, 1:30 PM UTC
        }
        
        # FOMC dates are specific - would need external calendar
        # For simplicity, only strictly enforcing NFP which is predictable

    # ============================================
    # 1. MULTI-TIMEFRAME CONFIRMATION
    # ============================================
    
    def get_timeframe_data(self, candles: List[dict], timeframe_minutes: int) -> List[dict]:
        """
        Convert candle data to higher timeframe.
        
        Args:
            candles: 1H candle data
            timeframe_minutes: Target timeframe (240=4H, 60=1H, 15=15m, 5=5m)
        """
        if not candles or timeframe_minutes == 60:  # Already 1H
            return candles
        
        if timeframe_minutes < 60:
            # For lower timeframes, simulate by splitting candles
            # In real system, would fetch actual lower TF data
            return self._simulate_lower_timeframe(candles, timeframe_minutes)
        
        # Aggregate to higher timeframe
        aggregated = []
        ratio = timeframe_minutes // 60  # How many 1H candles per target candle
        
        for i in range(0, len(candles), ratio):
            chunk = candles[i:i+ratio]
            if not chunk:
                continue
            
            agg_candle = {
                'timestamp': chunk[0]['timestamp'],
                'open': chunk[0]['open'],
                'high': max(c['high'] for c in chunk),
                'low': min(c['low'] for c in chunk),
                'close': chunk[-1]['close'],
                'volume': sum(c.get('volume', 0) for c in chunk)
            }
            aggregated.append(agg_candle)
        
        return aggregated

    def _simulate_lower_timeframe(self, candles: List[dict], timeframe_minutes: int) -> List[dict]:
        """Simulate lower timeframe data from hourly."""
        simulated = []
        segments = 60 // timeframe_minutes
        
        for candle in candles:
            o, h, l, c = candle['open'], candle['high'], candle['low'], candle['close']
            price_range = h - l
            
            for seg in range(segments):
                # Distribute price movement across segments
                seg_open = o + (c - o) * (seg / segments)
                seg_close = o + (c - o) * ((seg + 1) / segments)
                seg_high = max(seg_open, seg_close) + price_range * 0.2
                seg_low = min(seg_open, seg_close) - price_range * 0.2
                
                simulated.append({
                    'timestamp': candle['timestamp'] + (seg * timeframe_minutes * 60),
                    'open': seg_open,
                    'high': min(seg_high, h),
                    'low': max(seg_low, l),
                    'close': seg_close,
                    'volume': candle.get('volume', 0) / segments
                })
        
        return simulated

    def check_mtf_alignment(self, candles: List[dict], direction: str) -> Tuple[bool, float]:
        """
        Check multi-timeframe trend alignment (4H, 1H, 15m, 5m).
        
        Args:
            candles: Base 1H candles
            direction: 'long' or 'short'
            
        Returns:
            (is_aligned, confluence_score)
        """
        timeframes = [240, 60, 15, 5]  # 4H, 1H, 15m, 5m
        scores = []
        
        for tf in timeframes:
            tf_candles = self.get_timeframe_data(candles, tf)
            if len(tf_candles) < 20:
                continue
            
            # Check if trend aligns with direction
            trend_score = self._calculate_trend_score(tf_candles, direction)
            scores.append(trend_score)
        
        # Require at least 3 timeframes to align
        if len(scores) < 3:
            return False, 0.0
        
        avg_score = sum(scores) / len(scores)
        is_aligned = avg_score > 0.6 and min(scores) > 0.4
        
        return is_aligned, avg_score

    def _calculate_trend_score(self, candles: List[dict], direction: str) -> float:
        """Calculate trend strength score for a timeframe."""
        if len(candles) < 20:
            return 0.0
        
        recent = candles[-20:]
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        
        def count_extremes(values, compare_higher=True):
            """Count higher/lower extremes in sequence."""
            comparator = max if compare_higher else min
            return sum(
                1 for i in range(5, len(values)) 
                if (values[i] > comparator(values[i-5:i])) == compare_higher
            )
        
        if direction == 'long':
            extreme_count = count_extremes(highs, True) + count_extremes(lows, True)
        else:
            extreme_count = count_extremes(highs, False) + count_extremes(lows, False)
        
        return min(extreme_count / 30, 1.0)

    # ============================================
    # 2. PREVIOUS DAY HIGH/LOW
    # ============================================
    
    def update_daily_levels(self, candles: List[dict]):
        """Update previous day high/low levels."""
        if not candles:
            return
        
        # Group candles by day
        daily_data = {}
        for candle in candles:
            dt = datetime.fromtimestamp(candle['timestamp'], tz=timezone.utc)
            date_key = dt.date()
            
            if date_key not in daily_data:
                daily_data[date_key] = {'high': candle['high'], 'low': candle['low']}
            else:
                daily_data[date_key]['high'] = max(daily_data[date_key]['high'], candle['high'])
                daily_data[date_key]['low'] = min(daily_data[date_key]['low'], candle['low'])
        
        # Store as previous day levels
        dates = sorted(daily_data.keys())
        for i in range(1, len(dates)):
            prev_date = dates[i-1]
            curr_date = dates[i]
            
            self.previous_day_levels[curr_date] = DailyLevel(
                pdh=daily_data[prev_date]['high'],
                pdl=daily_data[prev_date]['low'],
                date=datetime.combine(curr_date, datetime.min.time())
            )

    def _calculate_level_score(self, candles: List[dict], level: float, 
                               price: float, is_bullish: bool) -> Tuple[bool, float]:
        """Calculate respect score for a price level."""
        recent = candles[-5:]
        
        if is_bullish:
            touches = any(abs(c['low'] - level) / level < 0.001 for c in recent)
            respected = price > level
        else:
            touches = any(abs(c['high'] - level) / level < 0.001 for c in recent)
            respected = price < level
        
        if touches and respected:
            return respected, 0.9
        elif respected:
            return respected, 0.7
        return respected, 0.3

    def check_pdh_pdl_respect(self, candles: List[dict], direction: str) -> Tuple[bool, float]:
        """Check if price respects previous day high/low."""
        if not candles:
            return False, 0.0
        
        current = candles[-1]
        current_date = datetime.fromtimestamp(current['timestamp'], tz=timezone.utc).date()
        
        if current_date not in self.previous_day_levels:
            self.update_daily_levels(candles)
            if current_date not in self.previous_day_levels:
                return True, 0.5
        
        levels = self.previous_day_levels[current_date]
        current_price = current['close']
        
        if direction == 'long':
            return self._calculate_level_score(candles, levels.pdl, current_price, True)
        return self._calculate_level_score(candles, levels.pdh, current_price, False)

    # ============================================
    # 3. LIQUIDITY SWEEP DETECTION
    # ============================================
    
    def _check_bullish_sweep(self, sweep: dict, reversal: dict, recent_low: float) -> Optional[LiquiditySweep]:
        """Check for bullish liquidity sweep (swept low, reversed up)."""
        swept_low = sweep['low'] < recent_low and sweep['close'] > recent_low
        confirmed = reversal['close'] > sweep['close'] and reversal['close'] > reversal['open']
        
        if swept_low and confirmed:
            strength = min((reversal['close'] - recent_low) / recent_low * 100, 1.0)
            return LiquiditySweep(
                timestamp=reversal['timestamp'],
                sweep_type='low',
                sweep_price=sweep['low'],
                rejection_price=reversal['close'],
                strength=strength
            )
        return None
    
    def _check_bearish_sweep(self, sweep: dict, reversal: dict, recent_high: float) -> Optional[LiquiditySweep]:
        """Check for bearish liquidity sweep (swept high, reversed down)."""
        swept_high = sweep['high'] > recent_high and sweep['close'] < recent_high
        confirmed = reversal['close'] < sweep['close'] and reversal['close'] < reversal['open']
        
        if swept_high and confirmed:
            strength = min((recent_high - reversal['close']) / recent_high * 100, 1.0)
            return LiquiditySweep(
                timestamp=reversal['timestamp'],
                sweep_type='high',
                sweep_price=sweep['high'],
                rejection_price=reversal['close'],
                strength=strength
            )
        return None

    def detect_liquidity_sweep(self, candles: List[dict]) -> Optional[LiquiditySweep]:
        """Detect liquidity sweep: false breakout followed by reversal."""
        if len(candles) < 15:
            return None
        
        recent = candles[-15:]
        lookback = recent[-10:-2]
        sweep_candle, reversal_candle = recent[-2], recent[-1]
        
        recent_high = max(c['high'] for c in lookback)
        recent_low = min(c['low'] for c in lookback)
        
        # Check bullish sweep first, then bearish
        return (self._check_bullish_sweep(sweep_candle, reversal_candle, recent_low) or
                self._check_bearish_sweep(sweep_candle, reversal_candle, recent_high))

    # ============================================
    # 4. CANDLE PATTERN CONFLUENCE
    # ============================================
    
    def detect_engulfing_pattern(self, candles: List[dict], timeframe: str = '30m') -> Optional[CandlePattern]:
        """Detect bullish/bearish engulfing patterns."""
        if len(candles) < 2:
            return None
        
        prev = candles[-2]
        curr = candles[-1]
        
        prev_body = abs(prev['close'] - prev['open'])
        curr_body = abs(curr['close'] - curr['open'])
        
        # Bullish engulfing
        if (prev['close'] < prev['open'] and  # Previous bearish
            curr['close'] > curr['open'] and  # Current bullish
            curr['open'] <= prev['close'] and  # Opens at/below prev close
            curr['close'] >= prev['open'] and  # Closes at/above prev open
            curr_body > prev_body * 1.2):  # Current body 20% larger
            
            return CandlePattern(
                pattern_type='engulfing_bullish',
                timestamp=curr['timestamp'],
                timeframe=timeframe,
                strength=0.8
            )
        
        # Bearish engulfing
        if (prev['close'] > prev['open'] and  # Previous bullish
            curr['close'] < curr['open'] and  # Current bearish
            curr['open'] >= prev['close'] and  # Opens at/above prev close
            curr['close'] <= prev['open'] and  # Closes at/below prev open
            curr_body > prev_body * 1.2):  # Current body 20% larger
            
            return CandlePattern(
                pattern_type='engulfing_bearish',
                timestamp=curr['timestamp'],
                timeframe=timeframe,
                strength=0.8
            )
        
        return None

    def check_breaker_in_fvg(self, candles: List[dict], fvg_zone: Tuple[float, float]) -> bool:
        """
        Check if there's a breaker block within the FVG zone on 5m.
        Breaker = failed support becomes resistance (or vice versa).
        """
        if not fvg_zone or len(candles) < 10:
            return False
        
        fvg_low, fvg_high = fvg_zone
        recent = candles[-10:]
        
        for i in range(len(recent) - 3):
            candle = recent[i]
            candle_mid = (candle['high'] + candle['low']) / 2
            
            # Check if candle is within FVG
            if fvg_low <= candle_mid <= fvg_high:
                # Check if it acted as support/resistance then broke
                next_candles = recent[i+1:i+4]
                
                # Breaker pattern: price tested level, then broke through
                if any(c['close'] < candle['low'] for c in next_candles):
                    return True  # Broke below = potential sell breaker
                if any(c['close'] > candle['high'] for c in next_candles):
                    return True  # Broke above = potential buy breaker
        
        return False

    # ============================================
    # 5. ASIAN RANGE HIGH/LOW SWEEP
    # ============================================
    
    def update_asian_range(self, candles: List[dict]):
        """Update Asian session range (00:00 - 09:00 UTC)."""
        asian_data = {}
        
        for candle in candles:
            dt = datetime.fromtimestamp(candle['timestamp'], tz=timezone.utc)
            
            # Asian session: 00:00 - 09:00 UTC
            if 0 <= dt.hour < 9:
                date_key = dt.date()
                
                if date_key not in asian_data:
                    asian_data[date_key] = {'high': candle['high'], 'low': candle['low']}
                else:
                    asian_data[date_key]['high'] = max(asian_data[date_key]['high'], candle['high'])
                    asian_data[date_key]['low'] = min(asian_data[date_key]['low'], candle['low'])
        
        # Store ranges
        for date_key, data in asian_data.items():
            self.asian_ranges[date_key] = AsianRange(
                high=data['high'],
                low=data['low'],
                date=datetime.combine(date_key, datetime.min.time())
            )

    def check_asian_range_sweep(self, candles: List[dict]) -> Tuple[bool, str]:
        """
        Check if price swept Asian high/low during London/NY session.
        
        Returns:
            (swept, sweep_direction)
        """
        if not candles:
            return False, ''
        
        current = candles[-1]
        current_dt = datetime.fromtimestamp(current['timestamp'], tz=timezone.utc)
        current_date = current_dt.date()
        current_hour = current_dt.hour
        
        # Only check during London/NY session (9:00 - 22:00 UTC)
        if not (9 <= current_hour < 22):
            return False, ''
        
        if current_date not in self.asian_ranges:
            self.update_asian_range(candles)
            if current_date not in self.asian_ranges:
                return False, ''
        
        asian_range = self.asian_ranges[current_date]
        recent = candles[-10:]  # Look at more candles for sweep confirmation
        current_price = current['close']
        
        # Calculate buffer (3 pips) for sweep confirmation
        pip_value = 0.0001
        buffer = 3 * pip_value  # 3 pips buffer (EU often sweeps by 3-8 pips)
        
        # Check if swept high (bearish signal)
        # MUST have price trade ABOVE asian high, then close BACK BELOW
        swept_high = any(c['high'] > asian_range.high + buffer for c in recent)
        if swept_high:
            # Ensure price has come back inside - this is the actual sweep
            if current_price < asian_range.high:
                return True, 'high'
        
        # Check if swept low (bullish signal)
        # MUST have price trade BELOW asian low, then close BACK ABOVE
        swept_low = any(c['low'] < asian_range.low - buffer for c in recent)
        if swept_low:
            # Ensure price has come back inside - this is the actual sweep
            if current_price > asian_range.low:
                return True, 'low'
        
        return False, ''

    # ============================================
    # 6. NEWS FILTER
    # ============================================
    
    def is_news_time(self, timestamp: int) -> Tuple[bool, str]:
        """
        Check if current time is within 30 min before/after high-impact news.
        Only blocks on ACTUAL news days, not every day.
        
        Returns:
            (is_news_time, reason)
        """
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        current_hour = dt.hour
        current_minute = dt.minute
        current_time = current_hour + current_minute / 60.0
        
        # Check each news event with proper day validation
        for news_name, details in self.high_impact_news.items():
            day_rule = details.get('day_rule', 'none')
            news_hour = details['time']
            news_duration = details['duration']
            
            # Check if this news event happens TODAY
            is_news_day = False
            
            if day_rule == 'first_friday':
                # First Friday of month: weekday=4 (Friday) and day 1-7
                is_news_day = dt.weekday() == 4 and 1 <= dt.day <= 7
            elif day_rule == 'mid_month':
                # Mid-month news (CPI/PPI): typically 10th-15th
                is_news_day = 10 <= dt.day <= 15
            elif day_rule == 'specific':
                # Would check against calendar - skip for now
                is_news_day = False
            
            if not is_news_day:
                continue
                
            # Create avoidance window: 30 min before to 30 min after
            avoid_start = news_hour - 0.5
            avoid_end = news_hour + news_duration + 0.5
            
            if avoid_start <= current_time <= avoid_end:
                return True, f"{news_name} at {news_hour}:00 UTC"
        
        return False, ''

    def can_trade_now(self, timestamp: int) -> Tuple[bool, str]:
        """
        Comprehensive check: Can we trade now?
        - Not during high-impact news
        - Not on weekends (market closed)
        - Not outside quality session hours (08:00–21:00 UTC)
        
        Session window rationale:
          08:00–17:00 — London session (primary liquidity)
          13:00–16:00 — London/NY overlap (peak volatility)
          16:00–21:00 — New York session (secondary liquidity)
        
        Blocked: 21:00–08:00 UTC (Asian session + pre-London).
        Pre-London (07:00–08:00) sweeps look valid but often fake out
        before the real London move. Better to wait for real liquidity.
        
        Returns:
            (can_trade, reason_if_not)
        """
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        
        # Check news (this already handles NFP on first Friday)
        is_news, news_reason = self.is_news_time(timestamp)
        if is_news:
            return False, f"News event: {news_reason}"
        
        # Block weekends only (forex closed Sat + Sun before 5pm EST / 22:00 UTC)
        weekday = dt.weekday()
        hour = dt.hour
        
        if weekday == 5:  # Saturday - fully closed
            return False, "Weekend - market closed"
        
        if weekday == 6 and hour < 22:  # Sunday before ~5pm EST
            return False, "Sunday - market not yet open"
        
        if weekday == 4 and hour >= 22:  # Friday after ~5pm EST
            return False, "Friday close - market closing"
        
        # Session-hour filter (tightened 2026-03-12 based on 97-trade analysis):
        # Data-driven allowed hours: 08-13, 15, 18-19 UTC
        # Blocked hours with 0-15% WR:
        #   01:00 (14%), 07:00 (10%), 14:00 (bad), 16-17 (0%), 20-21 (0%)
        # Good hours: 00 (75%), 08-10 (mixed), 13 (44%), 15 (60%), 18 (100%), 19
        # Conservative: stick to London + peak NY, skip dead zones
        # US30 / index detection: check if we're being called for an index symbol
        # The strategy passes symbol context through can_trade_now_symbol() if available.
        # For backward compat, the basic can_trade_now() uses forex hours.
        # US30 hours are handled by can_trade_now_us30() below.
        _allowed_hours = {8, 9, 10, 11, 12, 13, 15, 18, 19}
        if hour not in _allowed_hours:
            return False, f"Outside quality hours ({hour:02d}:00 UTC — allowed: 08-13, 15, 18-19)"
        
        return True, ''
    
    def can_trade_now_us30(self, timestamp: int) -> Tuple[bool, str]:
        """
        Session filter for US30 (Dow Jones index).
        
        US30 Kill Zones (UTC):
          13:30-15:30  — NYSE Open (highest volume, best setups)
          15:00-16:00  — Silver Bullet window
          16:00-18:00  — Mid-session continuation
          19:00-20:00  — Power Hour
        
        Blocked: Everything else (low volume futures, wide spreads)
        Skip first 5 min after open (13:30-13:35) — spread chaos.
        """
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        weekday = dt.weekday()
        hour = dt.hour
        
        # Weekend check (same as forex)
        if weekday == 5:
            return False, "Weekend - market closed"
        if weekday == 6 and hour < 22:
            return False, "Sunday - market not yet open"
        if weekday == 4 and hour >= 22:
            return False, "Friday close - market closing"
        
        # News check
        is_news, news_reason = self.is_news_time(timestamp)
        if is_news:
            return False, f"News event: {news_reason}"
        
        # US30 allowed hours: 13-19 UTC (NYSE open through power hour)
        # This covers: NYSE open (13:30), Silver Bullet (15:00), Power Hour (19:00)
        _us30_allowed_hours = {13, 14, 15, 16, 17, 18, 19}
        if hour not in _us30_allowed_hours:
            return False, f"US30: Outside NYSE hours ({hour:02d}:00 UTC — allowed: 13-19)"
        
        return True, ''

    def get_current_session(self, timestamp: int) -> str:
        """
        Get the current trading session name.
        
        Returns:
            Session name: 'PRE_LONDON', 'LONDON', 'OVERLAP', 'NY', or 'CLOSED'
        """
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        hour = dt.hour
        
        if 7 <= hour < 8:
            return 'PRE_LONDON'  # Asian sweep detection time
        elif 8 <= hour < 13:
            return 'LONDON'
        elif 13 <= hour < 16:
            return 'OVERLAP'  # London/NY overlap - best volatility
        elif 16 <= hour < 21:
            return 'NY'
        else:
            return 'CLOSED'

    # ============================================
    # 7. ORDER BLOCKS (5M & 15M)
    # ============================================
    
    def identify_order_block_mtf(self, candles: List[dict], timeframes: List[int] = [5, 15]) -> List[Tuple[float, float, str]]:
        """
        Identify order blocks on multiple timeframes (5m, 15m).
        
        Returns:
            List of (block_low, block_high, timeframe)
        """
        order_blocks = []
        
        for tf in timeframes:
            tf_candles = self.get_timeframe_data(candles, tf)
            blocks = self._find_order_blocks_single_tf(tf_candles, f"{tf}m")
            order_blocks.extend(blocks)
        
        return order_blocks

    def _find_order_blocks_single_tf(self, candles: List[dict], tf_name: str) -> List[Tuple[float, float, str]]:
        """Find order blocks on a single timeframe."""
        if len(candles) < 10:
            return []
        
        blocks = []
        
        for i in range(len(candles) - 5, len(candles) - 1):
            if i < 2:
                continue
            
            prev = candles[i - 1]
            curr = candles[i]
            next_candle = candles[i + 1]
            
            # Bullish order block: strong bullish reversal
            if (curr['close'] > curr['open'] and  # Bullish
                next_candle['close'] > curr['close'] and  # Continuation
                curr['close'] > prev['high']):  # Breaks above previous
                
                block_low = curr['low']
                block_high = curr['open']
                blocks.append((block_low, block_high, tf_name))
            
            # Bearish order block: strong bearish reversal
            if (curr['close'] < curr['open'] and  # Bearish
                next_candle['close'] < curr['close'] and  # Continuation
                curr['close'] < prev['low']):  # Breaks below previous
                
                block_low = curr['open']
                block_high = curr['high']
                blocks.append((block_low, block_high, tf_name))
        
        return blocks[-3:] if blocks else []  # Return last 3 most recent
