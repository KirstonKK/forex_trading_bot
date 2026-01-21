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
        self.trades_today = 0
        self.current_date = None
    
    def determine_htf_trend(self, candles: List[dict], timeframe: int = 240) -> TrendDirection:
        """Determine HTF trend (4H or 1H)."""
        if len(candles) < 50:
            return TrendDirection.RANGING
        
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
        """Find HTF zones (4H or 1H supply/demand)."""
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
        """Find order blocks on specified timeframe."""
        candles_tf = self.filters.get_timeframe_data(candles, timeframe)
        if len(candles_tf) < 20:
            return []
        
        order_blocks = []
        for i in range(len(candles_tf) - 10, len(candles_tf) - 1):
            if i < 2:
                continue
            
            prev = candles_tf[i - 1]
            curr = candles_tf[i]
            next_c = candles_tf[i + 1]
            
            # Bullish OB: strong up move after this candle
            if (curr['close'] > curr['open'] and
                next_c['close'] > curr['close'] * 1.002):
                
                strength = (curr['close'] - curr['open']) / curr['open']
                ob = OrderBlock(
                    high=curr['open'],
                    low=curr['low'],
                    timestamp=curr['timestamp'],
                    direction='bullish',
                    timeframe=f"{timeframe}M",
                    strength=strength
                )
                order_blocks.append(ob)
            
            # Bearish OB: strong down move after this candle
            elif (curr['close'] < curr['open'] and
                  next_c['close'] < curr['close'] * 0.998):
                
                strength = (curr['open'] - curr['close']) / curr['close']
                ob = OrderBlock(
                    high=curr['high'],
                    low=curr['open'],
                    timestamp=curr['timestamp'],
                    direction='bearish',
                    timeframe=f"{timeframe}M",
                    strength=strength
                )
                order_blocks.append(ob)
        
        return sorted(order_blocks, key=lambda x: x.strength, reverse=True)[:5]
    
    def find_fvgs(self, candles: List[dict]) -> List[FVG]:
        """Find Fair Value Gaps on 5M."""
        candles_5m = self.filters.get_timeframe_data(candles, 5)
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
        """Check Break of Structure."""
        if len(candles) < 15:
            return False
        
        recent = candles[-15:]
        current_price = candles[-1]['close']
        
        if direction == 'long':
            recent_high = max(c['high'] for c in recent[:-2])
            return current_price > recent_high * 1.0005  # 0.05% break
        else:
            recent_low = min(c['low'] for c in recent[:-2])
            return current_price < recent_low * 0.9995
    
    def check_choch(self, candles: List[dict], direction: str) -> bool:
        """Check Change of Character."""
        if len(candles) < 10:
            return False
        
        recent = candles[-10:]
        
        if direction == 'long':
            # Looking for shift to higher lows
            lows = [c['low'] for c in recent[-5:]]
            return len(lows) >= 3 and lows[-1] > lows[-2] > lows[-3]
        else:
            # Looking for shift to lower highs
            highs = [c['high'] for c in recent[-5:]]
            return len(highs) >= 3 and highs[-1] < highs[-2] < highs[-3]
    
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
        Option 1: HTF Bias + Liquidity Sweep + BoS
        Requirements:
        - Clear HTF trend (4H or 1H) ✅
        - Liquidity sweep ✅
        - BoS in direction of HTF ✅
        """
        confirmations = []
        
        # 1. HTF Trend
        htf_trend_4h = self.determine_htf_trend(candles, 240)
        htf_trend_1h = self.determine_htf_trend(candles, 60)
        
        htf_trend = htf_trend_4h if htf_trend_4h != TrendDirection.RANGING else htf_trend_1h
        
        if htf_trend == TrendDirection.RANGING:
            return None
        
        confirmations.append("HTF_BIAS")
        direction = 'long' if htf_trend == TrendDirection.BULLISH else 'short'
        
        # 2. Liquidity Sweep
        has_sweep, sweep_type = self.check_liquidity_sweep(candles, symbol)
        if not has_sweep:
            return None
        
        # Ensure sweep aligns with direction
        if direction == 'long' and sweep_type != 'low':
            return None
        if direction == 'short' and sweep_type != 'high':
            return None
        
        confirmations.append("LIQUIDITY_SWEEP")
        
        # 3. BoS
        has_bos = self.check_bos(candles, direction)
        if not has_bos:
            return None
        
        confirmations.append("BOS")
        
        return {
            'setup_type': SetupType.OPTION_1,
            'direction': direction,
            'confirmations': confirmations,
            'htf_trend': htf_trend,
            'has_liquidity_sweep': True,
            'has_bos': True,
            'asian_sweep': sweep_type in ['low', 'high'],
            'order_block': None,
            'fvg': None,
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
    
    def try_option_3(self, candles: List[dict], symbol: str) -> Optional[Dict]:
        """
        Option 3: OB + FVG + Fib 79%
        Requirements:
        - 5M OB ✅
        - FVG overlapping the OB ✅
        - 79% Fib retracement ✅
        """
        confirmations = []
        
        # 1. Find 5M OBs
        order_blocks_5m = self.find_order_blocks(candles, 5)
        if not order_blocks_5m:
            return None
        
        ob = order_blocks_5m[0]  # Best OB by strength
        confirmations.append("OB_5M")
        direction = 'long' if ob.direction == 'bullish' else 'short'
        
        # 2. Find FVGs
        fvgs = self.find_fvgs(candles)
        overlapping_fvg = self.check_ob_fvg_overlap(ob, fvgs)
        
        if not overlapping_fvg:
            return None
        
        confirmations.append("FVG")
        
        # 3. Check 79% Fib
        ob_mid = (ob.high + ob.low) / 2
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
            'order_block': ob,
            'fvg': overlapping_fvg,
            'htf_zone': None,
            'has_fib_confluence': True
        }
    
    def calculate_sl_tp(self, entry: float, setup_data: Dict, candles: List[dict], 
                        symbol: str) -> Tuple[Optional[float], Optional[float], float]:
        """Calculate SL/TP based on setup type."""
        direction = setup_data['direction']
        pip_value = 0.10 if symbol == 'XAUUSD' else 0.0001
        
        # Determine SL based on setup
        if setup_data['order_block']:
            ob = setup_data['order_block']
            if direction == 'long':
                stop_loss = ob.low * 0.998
            else:
                stop_loss = ob.high * 1.002
        elif setup_data['htf_zone']:
            zone = setup_data['htf_zone']
            if direction == 'long':
                stop_loss = zone.low * 0.998
            else:
                stop_loss = zone.high * 1.002
        else:
            # Use recent swing
            recent = candles[-20:]
            if direction == 'long':
                stop_loss = min(c['low'] for c in recent) * 0.998
            else:
                stop_loss = max(c['high'] for c in recent) * 1.002
        
        sl_distance = abs(entry - stop_loss)
        sl_pips = sl_distance / pip_value
        
        # Validate SL range (30-150 pips)
        if sl_pips < 30 or sl_pips > 150:
            return None, None, 0
        
        # Calculate TP (aim for 1:3 minimum)
        if direction == 'long':
            take_profit = entry + (sl_distance * 3.0)
        else:
            take_profit = entry - (sl_distance * 3.0)
        
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        rr_ratio = reward / risk if risk > 0 else 0
        
        if rr_ratio < 2.5:
            return None, None, 0
        
        return stop_loss, take_profit, rr_ratio
    
    def determine_risk_percentage(self, confirmation_count: int) -> float:
        """
        Risk Management:
        - 3 confirmations = full risk (1.0%)
        - 2 confirmations = half risk (0.5%)
        - 1 confirmation = no trade
        """
        if confirmation_count >= 3:
            return 1.0
        elif confirmation_count == 2:
            return 0.5
        else:
            return 0.0
    
    def can_take_trade(self, timestamp: int) -> bool:
        """Check daily limits (max 2 trades/day)."""
        current_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
        
        if self.current_date != current_date:
            self.current_date = current_date
            self.trades_today = 0
        
        if self.trades_today >= 2:
            return False
        
        can_trade, _ = self.filters.can_trade_now(timestamp)
        return can_trade
    
    def analyze(self, candles: List[dict], symbol: str = 'EURUSD') -> Optional[Dict]:
        """
        Main analysis - Try all 3 options in order of priority.
        
        Priority for EU/GU: Option 1 > Option 2 > Option 3
        Priority for Gold: Option 2 > Option 1 > Option 3
        """
        if len(candles) < 100 or not self.can_take_trade(candles[-1]['timestamp']):
            return None
        
        # Determine priority based on symbol
        if symbol == 'XAUUSD':
            options = [self.try_option_2, self.try_option_1, self.try_option_3]
        else:  # EU, GU
            options = [self.try_option_1, self.try_option_2, self.try_option_3]
        
        setup_data = None
        for option_func in options:
            setup_data = option_func(candles, symbol)
            if setup_data:
                break
        
        if not setup_data:
            return None
        
        # Check confirmation count
        confirmation_count = len(setup_data['confirmations'])
        if confirmation_count < 2:
            return None  # Need at least 2 confirmations
        
        # Calculate risk percentage
        risk_percentage = self.determine_risk_percentage(confirmation_count)
        
        # Calculate SL/TP
        entry_price = candles[-1]['close']
        stop_loss, take_profit, rr_ratio = self.calculate_sl_tp(
            entry_price, setup_data, candles, symbol
        )
        
        if stop_loss is None:
            return None
        
        # Calculate confidence
        confidence = 0.60 + (confirmation_count * 0.10)
        if rr_ratio >= 4.0:
            confidence += 0.05
        if setup_data['htf_trend'] and setup_data['htf_trend'] != TrendDirection.RANGING:
            confidence += 0.05
        
        confidence = min(confidence, 0.95)
        
        self.trades_today += 1
        
        return {
            'timestamp': candles[-1]['timestamp'],
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


# Compatibility wrapper for existing code
class ProfessionalStrategy(FlexibleICTStrategy):
    """Wrapper for backward compatibility."""
    pass
