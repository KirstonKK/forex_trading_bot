"""
ML Feature Engineering
Extracts features from trade data and time series for model training.
"""

from typing import List, Dict, Tuple
import numpy as np
from dataclasses import dataclass


@dataclass
class TradeFeatures:
    """Features extracted from a trade for ML."""
    # Trade-specific features
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float
    entry_volume: float
    spread_at_entry: float
    
    # Pattern features
    pattern_type: str  # order_block, fvg, structure_break
    pattern_strength: float
    
    # Market context
    volatility_at_entry: float
    trend_direction: int  # -1, 0, 1 (down, neutral, up)
    market_regime: str  # trending, ranging, volatile
    
    # Time features
    hour_of_day: int
    day_of_week: int
    
    # Target (what we want to predict)
    trade_outcome: float  # 1.0 for win, 0.0 for loss, or actual pnl %
    

class FeatureExtractor:
    """Extracts ML features from trading data."""

    @staticmethod
    def extract_trade_features(
        trade: Dict,
        candles: List[Dict],
        pattern_type: str
    ) -> TradeFeatures:
        """
        Extract features from a completed trade.
        
        Args:
            trade: Trade data with entry/exit prices
            candles: OHLCV candles around trade time
            pattern_type: Type of pattern that triggered the trade
            
        Returns:
            TradeFeatures object
        """
        entry_price = trade['entry_price']
        stop_loss = trade['stop_loss']
        take_profit = trade['take_profit']
        exit_price = trade.get('exit_price', entry_price)
        
        # Risk:Reward ratio
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        rr_ratio = reward / risk if risk > 0 else 0
        
        # Trade outcome
        pnl = exit_price - entry_price
        trade_outcome = 1.0 if pnl > 0 else 0.0
        
        # Volatility at entry (ATR approximation)
        if candles:
            highs = [c['high'] for c in candles[-14:]]
            lows = [c['low'] for c in candles[-14:]]
            volatility = np.mean([h - l for h, l in zip(highs, lows)])
        else:
            volatility = 0.0
        
        # Trend direction
        if len(candles) >= 2:
            recent_close = candles[-1]['close']
            prev_close = candles[-2]['close']
            if recent_close > prev_close:
                trend_direction = 1
            elif recent_close < prev_close:
                trend_direction = -1
            else:
                trend_direction = 0
        else:
            trend_direction = 0
        
        # Time features (simplified - would parse from entry_time in production)
        hour_of_day = 12  # Default, would parse from entry_time
        day_of_week = 2   # Default, would parse from entry_time
        
        # Spread and spread at entry (approximation)
        spread_at_entry = 0.0002  # Default, would get from broker data
        entry_volume = trade.get('quantity', 1000)
        
        # Market regime (simplified)
        if volatility > np.mean([c['high'] - c['low'] for c in candles[-50:]]) * 1.5:
            market_regime = "volatile"
        elif len(candles) >= 20:
            # Check if trending or ranging
            highs_20 = [c['high'] for c in candles[-20:]]
            lows_20 = [c['low'] for c in candles[-20:]]
            high_trend = highs_20[-1] > np.mean(highs_20[:-1])
            low_trend = lows_20[-1] > np.mean(lows_20[:-1])
            market_regime = "trending" if high_trend or low_trend else "ranging"
        else:
            market_regime = "ranging"
        
        return TradeFeatures(
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward_ratio=rr_ratio,
            entry_volume=entry_volume,
            spread_at_entry=spread_at_entry,
            pattern_type=pattern_type,
            pattern_strength=1.0,  # Would be calculated from pattern data
            volatility_at_entry=volatility,
            trend_direction=trend_direction,
            market_regime=market_regime,
            hour_of_day=hour_of_day,
            day_of_week=day_of_week,
            trade_outcome=trade_outcome
        )

    @staticmethod
    def features_to_array(features: TradeFeatures) -> np.ndarray:
        """Convert TradeFeatures to numpy array for ML model."""
        # Categorical encoding
        pattern_encoding = {
            'order_block': 0,
            'fvg': 1,
            'structure_break': 2
        }
        regime_encoding = {
            'trending': 0,
            'ranging': 1,
            'volatile': 2
        }
        
        return np.array([
            features.entry_price,
            features.stop_loss,
            features.take_profit,
            features.risk_reward_ratio,
            features.entry_volume,
            features.spread_at_entry,
            pattern_encoding.get(features.pattern_type, 0),
            features.pattern_strength,
            features.volatility_at_entry,
            features.trend_direction,
            regime_encoding.get(features.market_regime, 0),
            features.hour_of_day,
            features.day_of_week
        ])

    @staticmethod
    def batch_features_to_dataframe(features_list: List[TradeFeatures]):
        """Convert list of features to pandas DataFrame for training."""
        try:
            import pandas as pd
            
            data = []
            for features in features_list:
                data.append({
                    'entry_price': features.entry_price,
                    'stop_loss': features.stop_loss,
                    'take_profit': features.take_profit,
                    'risk_reward_ratio': features.risk_reward_ratio,
                    'entry_volume': features.entry_volume,
                    'spread_at_entry': features.spread_at_entry,
                    'pattern_type': features.pattern_type,
                    'pattern_strength': features.pattern_strength,
                    'volatility_at_entry': features.volatility_at_entry,
                    'trend_direction': features.trend_direction,
                    'market_regime': features.market_regime,
                    'hour_of_day': features.hour_of_day,
                    'day_of_week': features.day_of_week,
                    'outcome': features.trade_outcome
                })
            
            return pd.DataFrame(data)
        except ImportError:
            print("pandas not installed")
            return None
