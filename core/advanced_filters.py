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
        
        # High-impact news events (UTC hours)
        self.high_impact_news = {
            'NFP': {'day': 4, 'time': 13, 'duration': 2},  # First Friday, 1:30 PM UTC
            'FOMC': {'time': 18, 'duration': 3},  # 6 PM UTC
            'CPI': {'time': 13, 'duration': 2},  # 1:30 PM UTC
            'PPI': {'time': 13, 'duration': 1.5},  # 1:30 PM UTC
            'GDP': {'time': 13, 'duration': 1},
            'Interest_Rate': {'time': 12, 'duration': 2},
        }

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
        
        # Check for higher highs/lows (bullish) or lower highs/lows (bearish)
        if direction == 'long':
            # Count higher highs and higher lows
            hh_count = sum(1 for i in range(5, len(highs)) if highs[i] > max(highs[i-5:i]))
            hl_count = sum(1 for i in range(5, len(lows)) if lows[i] > max(lows[i-5:i]))
            score = (hh_count + hl_count) / 30  # Normalize to 0-1
        else:  # short
            # Count lower highs and lower lows
            lh_count = sum(1 for i in range(5, len(highs)) if highs[i] < min(highs[i-5:i]))
            ll_count = sum(1 for i in range(5, len(lows)) if lows[i] < min(lows[i-5:i]))
            score = (lh_count + ll_count) / 30
        
        return min(score, 1.0)

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

    def check_pdh_pdl_respect(self, candles: List[dict], direction: str) -> Tuple[bool, float]:
        """
        Check if price respects previous day high/low.
        
        Returns:
            (respected, distance_score)
        """
        if not candles:
            return False, 0.0
        
        current = candles[-1]
        current_date = datetime.fromtimestamp(current['timestamp'], tz=timezone.utc).date()
        
        if current_date not in self.previous_day_levels:
            self.update_daily_levels(candles)
            if current_date not in self.previous_day_levels:
                return True, 0.5  # Neutral if no data
        
        levels = self.previous_day_levels[current_date]
        current_price = current['close']
        
        # Check last 5 candles for level respect
        recent = candles[-5:]
        
        if direction == 'long':
            # Should have bounced off PDL
            touches_pdl = any(abs(c['low'] - levels.pdl) / levels.pdl < 0.001 for c in recent)
            above_pdl = current_price > levels.pdl
            
            if touches_pdl and above_pdl:
                distance_score = 0.9
            elif above_pdl:
                distance_score = 0.7
            else:
                distance_score = 0.3
            
            return above_pdl, distance_score
        
        else:  # short
            # Should have rejected from PDH
            touches_pdh = any(abs(c['high'] - levels.pdh) / levels.pdh < 0.001 for c in recent)
            below_pdh = current_price < levels.pdh
            
            if touches_pdh and below_pdh:
                distance_score = 0.9
            elif below_pdh:
                distance_score = 0.7
            else:
                distance_score = 0.3
            
            return below_pdh, distance_score

    # ============================================
    # 3. LIQUIDITY SWEEP DETECTION
    # ============================================
    
    def detect_liquidity_sweep(self, candles: List[dict]) -> Optional[LiquiditySweep]:
        """
        Detect liquidity sweep: false breakout followed by reversal.
        """
        if len(candles) < 15:
            return None
        
        recent = candles[-15:]
        lookback = recent[-10:-2]  # Candles before last 2
        last_two = recent[-2:]
        
        # Find recent high/low
        recent_high = max(c['high'] for c in lookback)
        recent_low = min(c['low'] for c in lookback)
        
        # Check for sweep of high (bearish sweep)
        sweep_candle = last_two[0]
        reversal_candle = last_two[1]
        
        # Bullish liquidity sweep (swept low, then reversed up)
        if (sweep_candle['low'] < recent_low and  # Swept below low
            sweep_candle['close'] > recent_low and  # But closed above
            reversal_candle['close'] > sweep_candle['close'] and  # Confirmed reversal
            reversal_candle['close'] > reversal_candle['open']):  # Bullish close
            
            strength = (reversal_candle['close'] - recent_low) / recent_low * 100
            
            return LiquiditySweep(
                timestamp=reversal_candle['timestamp'],
                sweep_type='low',
                sweep_price=sweep_candle['low'],
                rejection_price=reversal_candle['close'],
                strength=min(strength, 1.0)
            )
        
        # Bearish liquidity sweep (swept high, then reversed down)
        if (sweep_candle['high'] > recent_high and  # Swept above high
            sweep_candle['close'] < recent_high and  # But closed below
            reversal_candle['close'] < sweep_candle['close'] and  # Confirmed reversal
            reversal_candle['close'] < reversal_candle['open']):  # Bearish close
            
            strength = (recent_high - reversal_candle['close']) / recent_high * 100
            
            return LiquiditySweep(
                timestamp=reversal_candle['timestamp'],
                sweep_type='high',
                sweep_price=sweep_candle['high'],
                rejection_price=reversal_candle['close'],
                strength=min(strength, 1.0)
            )
        
        return None

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
        recent = candles[-5:]
        
        # Check if swept high (bearish signal)
        swept_high = any(c['high'] > asian_range.high for c in recent)
        if swept_high and current['close'] < asian_range.high:
            return True, 'high'
        
        # Check if swept low (bullish signal)
        swept_low = any(c['low'] < asian_range.low for c in recent)
        if swept_low and current['close'] > asian_range.low:
            return True, 'low'
        
        return False, ''

    # ============================================
    # 6. NEWS FILTER
    # ============================================
    
    def is_news_time(self, timestamp: int) -> Tuple[bool, str]:
        """
        Check if current time is within 30 min before/after high-impact news.
        
        Returns:
            (is_news_time, reason)
        """
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        current_hour = dt.hour
        current_minute = dt.minute
        current_time = current_hour + current_minute / 60.0
        
        # Check each news event
        for news_name, details in self.high_impact_news.items():
            news_hour = details['time']
            news_duration = details['duration']
            
            # Create avoidance window: 30 min before to 30 min after
            avoid_start = news_hour - 0.5
            avoid_end = news_hour + news_duration + 0.5
            
            if avoid_start <= current_time <= avoid_end:
                return True, f"{news_name} at {news_hour}:00 UTC"
        
        # Additional check for first Friday (NFP)
        if dt.weekday() == 4 and 7 <= dt.day <= 14:  # First Friday of month
            nfp_time = 13.5  # 1:30 PM UTC
            if abs(current_time - nfp_time) < 1.0:
                return True, "NFP (Non-Farm Payrolls)"
        
        return False, ''

    def can_trade_now(self, timestamp: int) -> Tuple[bool, str]:
        """
        Comprehensive check: Can we trade now?
        - Not during news
        - Not during low-liquidity periods
        
        Returns:
            (can_trade, reason_if_not)
        """
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        
        # Check news
        is_news, news_reason = self.is_news_time(timestamp)
        if is_news:
            return False, f"News event: {news_reason}"
        
        # Check day of week
        if dt.weekday() == 6:  # Sunday
            return False, "Sunday - market opening"
        
        if dt.weekday() == 4 and dt.hour >= 20:  # Friday evening
            return False, "Friday evening - low liquidity"
        
        # Check session (only London/NY)
        hour = dt.hour
        if not (8 <= hour < 22):  # Outside 8 AM - 10 PM UTC
            return False, "Outside London/NY sessions"
        
        return True, ''

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
