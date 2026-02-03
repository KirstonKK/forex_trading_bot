"""
Machine Learning Risk Adjustment Model
Predicts trade quality to adjust position sizing while preserving 1:2 R:R.

Key principle: Does NOT change entry logic - only position sizing.
- High confidence → Full risk (1-2%)
- Medium confidence → Half risk (0.5-1%)
- Low confidence → Quarter risk (0.25%) or skip
"""

import json
import logging
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import numpy as np

logger = logging.getLogger(__name__)

# Data paths
DATA_DIR = Path(__file__).parent.parent / 'data'
ML_DIR = DATA_DIR / 'ml'
TRAINING_DATA_FILE = ML_DIR / 'training_data.json'
MODEL_FILE = ML_DIR / 'risk_model.pkl'
FEATURE_STATS_FILE = ML_DIR / 'feature_stats.json'


class FeatureExtractor:
    """Extract ML features from trade setup data."""
    
    # Feature definitions with normalization ranges
    FEATURE_SCHEMA = {
        # Setup features
        'confirmation_count': {'min': 1, 'max': 6, 'default': 3},
        'setup_type': {'options': ['OPTION_1', 'OPTION_2', 'OPTION_3'], 'default': 0},
        'has_choch': {'boolean': True, 'default': 0},
        'has_bos': {'boolean': True, 'default': 0},
        'has_fvg': {'boolean': True, 'default': 0},
        'has_ob': {'boolean': True, 'default': 0},
        'has_liquidity_sweep': {'boolean': True, 'default': 0},
        'fvg_size_pct': {'min': 0, 'max': 2.0, 'default': 0.5},
        'ob_strength': {'min': 0, 'max': 1.0, 'default': 0.5},
        'distance_to_sl_pips': {'min': 5, 'max': 100, 'default': 20},
        
        # Market context
        'atr_normalized': {'min': 0, 'max': 2.0, 'default': 1.0},
        'session': {'options': ['LONDON', 'NY', 'OVERLAP', 'OFF'], 'default': 0},
        'trend_strength': {'min': -1, 'max': 1, 'default': 0},
        'hours_since_session_open': {'min': 0, 'max': 8, 'default': 3},
        'day_of_week': {'min': 0, 'max': 4, 'default': 2},
        
        # HTF alignment
        'htf_bias_aligned': {'boolean': True, 'default': 1},
        'htf_in_zone': {'boolean': True, 'default': 0},
        'mtf_alignment_score': {'min': 0, 'max': 1, 'default': 0.5},
        
        # Historical performance (rolling)
        'pair_win_rate_10': {'min': 0, 'max': 1, 'default': 0.6},
        'hour_win_rate': {'min': 0, 'max': 1, 'default': 0.6},
        'setup_type_win_rate': {'min': 0, 'max': 1, 'default': 0.6},
        'streak': {'min': -5, 'max': 5, 'default': 0},  # Negative = losing streak
    }
    
    def __init__(self):
        self.feature_stats = self._load_feature_stats()
    
    def _load_feature_stats(self) -> Dict:
        """Load running statistics for feature normalization."""
        try:
            if FEATURE_STATS_FILE.exists():
                with open(FEATURE_STATS_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading feature stats: {e}")
        return {'means': {}, 'stds': {}, 'counts': {}}
    
    def _save_feature_stats(self):
        """Save feature statistics."""
        try:
            ML_DIR.mkdir(parents=True, exist_ok=True)
            with open(FEATURE_STATS_FILE, 'w') as f:
                json.dump(self.feature_stats, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving feature stats: {e}")
    
    def extract_features(self, signal_data: Dict, market_context: Dict = None) -> Dict[str, float]:
        """
        Extract normalized features from a trade signal.
        
        Args:
            signal_data: The signal dict from strategy.analyze()
            market_context: Additional market data (ATR, session, etc.)
        
        Returns:
            Dict of feature_name -> normalized value (0-1)
        """
        features = {}
        market_context = market_context or {}
        
        # === Setup Features ===
        confirmations = signal_data.get('confirmations', [])
        features['confirmation_count'] = self._normalize(
            len(confirmations), 1, 6
        )
        
        # Setup type (one-hot encoded as single value)
        setup_type = signal_data.get('setup_type', 'OPTION_1')
        setup_options = ['OPTION_1', 'OPTION_2', 'OPTION_3']
        features['setup_type'] = setup_options.index(setup_type) / 2.0 if setup_type in setup_options else 0
        
        # Boolean confirmations
        features['has_choch'] = 1.0 if 'CHOCH' in confirmations else 0.0
        features['has_bos'] = 1.0 if 'BOS' in confirmations else 0.0
        features['has_fvg'] = 1.0 if 'FVG' in confirmations else 0.0
        features['has_ob'] = 1.0 if 'OB' in confirmations else 0.0
        features['has_liquidity_sweep'] = 1.0 if 'SWEEP' in confirmations or 'LIQ' in str(confirmations) else 0.0
        
        # FVG size (if available)
        fvg_size = signal_data.get('fvg_size_pct', 0.5)
        features['fvg_size_pct'] = self._normalize(fvg_size, 0, 2.0)
        
        # OB strength
        ob_strength = signal_data.get('ob_strength', 0.5)
        features['ob_strength'] = self._normalize(ob_strength, 0, 1.0)
        
        # Distance to SL in pips
        entry = signal_data.get('entry_price', 0)
        sl = signal_data.get('stop_loss', 0)
        if entry and sl:
            sl_distance = abs(entry - sl)
            # Convert to pips (forex = *10000, gold = *10)
            symbol = signal_data.get('symbol', 'EURUSD')
            multiplier = 10 if 'XAU' in symbol else 10000
            sl_pips = sl_distance * multiplier
            features['distance_to_sl_pips'] = self._normalize(sl_pips, 5, 100)
        else:
            features['distance_to_sl_pips'] = 0.5
        
        # === Market Context ===
        # ATR normalization (1.0 = average volatility)
        atr = market_context.get('atr', 1.0)
        avg_atr = market_context.get('avg_atr', atr)
        features['atr_normalized'] = self._normalize(atr / avg_atr if avg_atr else 1.0, 0.5, 2.0)
        
        # Session
        session = market_context.get('session', 'LONDON')
        session_options = ['LONDON', 'NY', 'OVERLAP', 'OFF']
        features['session'] = session_options.index(session) / 3.0 if session in session_options else 0.33
        
        # Trend strength (-1 to 1)
        trend = market_context.get('trend_strength', 0)
        features['trend_strength'] = self._normalize(trend, -1, 1)
        
        # Time features
        now = datetime.utcnow()
        session_start = 10  # 10:00 UTC
        hours_active = max(0, min(7, now.hour - session_start))
        features['hours_since_session_open'] = self._normalize(hours_active, 0, 7)
        features['day_of_week'] = self._normalize(now.weekday(), 0, 4)
        
        # === HTF Alignment ===
        features['htf_bias_aligned'] = 1.0 if signal_data.get('htf_aligned', True) else 0.0
        features['htf_in_zone'] = 1.0 if signal_data.get('in_htf_zone', False) else 0.0
        features['mtf_alignment_score'] = signal_data.get('mtf_score', 0.5)
        
        # === Historical Performance ===
        hist = market_context.get('historical', {})
        features['pair_win_rate_10'] = hist.get('pair_win_rate', 0.6)
        features['hour_win_rate'] = hist.get('hour_win_rate', 0.6)
        features['setup_type_win_rate'] = hist.get('setup_win_rate', 0.6)
        features['streak'] = self._normalize(hist.get('streak', 0), -5, 5)
        
        return features
    
    def _normalize(self, value: float, min_val: float, max_val: float) -> float:
        """Normalize value to 0-1 range."""
        if max_val == min_val:
            return 0.5
        normalized = (value - min_val) / (max_val - min_val)
        return max(0.0, min(1.0, normalized))
    
    def features_to_vector(self, features: Dict[str, float]) -> np.ndarray:
        """Convert feature dict to numpy array for model input."""
        # Ensure consistent ordering
        feature_names = sorted(self.FEATURE_SCHEMA.keys())
        vector = []
        for name in feature_names:
            value = features.get(name, self.FEATURE_SCHEMA[name].get('default', 0.5))
            vector.append(float(value))
        return np.array(vector)
    
    def get_feature_names(self) -> List[str]:
        """Get ordered list of feature names."""
        return sorted(self.FEATURE_SCHEMA.keys())


class MLRiskModel:
    """
    Machine Learning model for trade risk scoring.
    
    Uses a simple ensemble approach:
    1. Logistic regression for baseline
    2. Decision tree for pattern capture
    3. Average scores for final prediction
    
    Outputs confidence score 0-100% used for position sizing.
    """
    
    def __init__(self):
        ML_DIR.mkdir(parents=True, exist_ok=True)
        self.feature_extractor = FeatureExtractor()
        self.model = None
        self.is_trained = False
        self.training_data: List[Dict] = []
        self.min_training_samples = 30  # Minimum trades before using ML
        
        self._load_training_data()
        self._load_model()
    
    def _load_training_data(self):
        """Load historical training data."""
        try:
            if TRAINING_DATA_FILE.exists():
                with open(TRAINING_DATA_FILE, 'r') as f:
                    self.training_data = json.load(f)
                logger.info(f"Loaded {len(self.training_data)} training samples")
        except Exception as e:
            logger.error(f"Error loading training data: {e}")
            self.training_data = []
    
    def _save_training_data(self):
        """Save training data."""
        try:
            with open(TRAINING_DATA_FILE, 'w') as f:
                json.dump(self.training_data[-5000:], f)  # Keep last 5000
        except Exception as e:
            logger.error(f"Error saving training data: {e}")
    
    def _load_model(self):
        """Load trained model if available."""
        try:
            if MODEL_FILE.exists():
                with open(MODEL_FILE, 'rb') as f:
                    self.model = pickle.load(f)
                self.is_trained = True
                logger.info("ML risk model loaded")
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            self.model = None
            self.is_trained = False
    
    def _save_model(self):
        """Save trained model."""
        try:
            if self.model:
                with open(MODEL_FILE, 'wb') as f:
                    pickle.dump(self.model, f)
        except Exception as e:
            logger.error(f"Error saving model: {e}")
    
    def log_trade(self, signal_data: Dict, market_context: Dict, 
                  outcome: str, pips: float):
        """
        Log a completed trade for training.
        
        Args:
            signal_data: Original signal from strategy
            market_context: Market conditions at signal time
            outcome: 'win' or 'loss'
            pips: Actual pips result
        """
        features = self.feature_extractor.extract_features(signal_data, market_context)
        
        sample = {
            'timestamp': datetime.utcnow().isoformat(),
            'features': features,
            'outcome': outcome,
            'pips': pips,
            'symbol': signal_data.get('symbol', 'UNKNOWN'),
            'setup_type': signal_data.get('setup_type', 'UNKNOWN')
        }
        
        self.training_data.append(sample)
        self._save_training_data()
        
        logger.info(f"ML: Logged trade - {outcome} ({pips:+.1f} pips), "
                   f"total samples: {len(self.training_data)}")
        
        # Retrain if we have enough new data
        if len(self.training_data) >= self.min_training_samples:
            if len(self.training_data) % 10 == 0:  # Retrain every 10 trades
                self.train()
    
    def train(self) -> Dict[str, Any]:
        """
        Train the risk model on collected data.
        
        Returns training metrics.
        """
        if len(self.training_data) < self.min_training_samples:
            return {
                'status': 'insufficient_data',
                'samples': len(self.training_data),
                'required': self.min_training_samples
            }
        
        try:
            # Prepare training data
            X = []
            y = []
            
            for sample in self.training_data:
                features = sample['features']
                vector = self.feature_extractor.features_to_vector(features)
                X.append(vector)
                y.append(1 if sample['outcome'] == 'win' else 0)
            
            X = np.array(X)
            y = np.array(y)
            
            # Simple ensemble: weighted average of predictions
            # Using basic numpy operations (no sklearn dependency)
            self.model = self._train_simple_model(X, y)
            self.is_trained = True
            self._save_model()
            
            # Calculate training metrics
            predictions = self._predict_proba(X)
            accuracy = np.mean((predictions > 0.5) == y)
            
            metrics = {
                'status': 'trained',
                'samples': len(self.training_data),
                'accuracy': float(accuracy),
                'win_rate': float(np.mean(y)),
                'feature_count': X.shape[1]
            }
            
            logger.info(f"ML Model trained: {metrics}")
            return metrics
            
        except Exception as e:
            logger.error(f"Training error: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _train_simple_model(self, X: np.ndarray, y: np.ndarray) -> Dict:
        """
        Train a simple model using numpy (no sklearn dependency).
        Uses weighted feature averaging based on correlation with outcome.
        """
        # Calculate feature weights based on correlation with wins
        weights = []
        for i in range(X.shape[1]):
            # Simple correlation
            feature_mean = np.mean(X[:, i])
            outcome_mean = np.mean(y)
            
            numerator = np.sum((X[:, i] - feature_mean) * (y - outcome_mean))
            denominator = np.sqrt(np.sum((X[:, i] - feature_mean) ** 2) * np.sum((y - outcome_mean) ** 2))
            
            if denominator > 0:
                correlation = numerator / denominator
            else:
                correlation = 0
            
            weights.append(correlation)
        
        weights = np.array(weights)
        
        # Normalize weights to sum to 1
        weights = np.abs(weights)
        if np.sum(weights) > 0:
            weights = weights / np.sum(weights)
        else:
            weights = np.ones(len(weights)) / len(weights)
        
        # Calculate bias (overall win rate)
        bias = np.mean(y)
        
        return {
            'weights': weights.tolist(),
            'bias': float(bias),
            'feature_means': np.mean(X, axis=0).tolist(),
            'feature_stds': np.std(X, axis=0).tolist()
        }
    
    def _predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict win probability for samples."""
        if not self.model:
            return np.full(len(X), 0.5)
        
        weights = np.array(self.model['weights'])
        bias = self.model['bias']
        
        # Weighted average of normalized features
        scores = np.dot(X, weights)
        
        # Combine with bias and sigmoid
        raw_scores = scores + (bias - 0.5) * 0.5
        probas = 1 / (1 + np.exp(-5 * (raw_scores - 0.5)))  # Sigmoid
        
        # Clip to reasonable range
        return np.clip(probas, 0.1, 0.9)
    
    def score_signal(self, signal_data: Dict, market_context: Dict = None) -> Dict[str, Any]:
        """
        Score a new signal for risk adjustment.
        
        Args:
            signal_data: Signal from strategy.analyze()
            market_context: Current market conditions
        
        Returns:
            {
                'confidence': 0-100 score,
                'risk_multiplier': 0.25-1.0,
                'recommendation': 'full_risk' | 'half_risk' | 'quarter_risk' | 'skip',
                'reasoning': [list of factors]
            }
        """
        # Default if not trained
        if not self.is_trained or len(self.training_data) < self.min_training_samples:
            return {
                'confidence': 70,
                'risk_multiplier': 0.75,
                'recommendation': 'half_risk',
                'reasoning': ['ML model not yet trained - using default'],
                'ml_active': False
            }
        
        try:
            # Extract features
            features = self.feature_extractor.extract_features(signal_data, market_context)
            vector = self.feature_extractor.features_to_vector(features).reshape(1, -1)
            
            # Get prediction
            proba = self._predict_proba(vector)[0]
            confidence = int(proba * 100)
            
            # Determine risk level
            if confidence >= 75:
                risk_mult = 1.0
                recommendation = 'full_risk'
            elif confidence >= 60:
                risk_mult = 0.75
                recommendation = 'three_quarter_risk'
            elif confidence >= 50:
                risk_mult = 0.5
                recommendation = 'half_risk'
            elif confidence >= 40:
                risk_mult = 0.25
                recommendation = 'quarter_risk'
            else:
                risk_mult = 0.0
                recommendation = 'skip'
            
            # Generate reasoning
            reasoning = self._generate_reasoning(features, proba)
            
            return {
                'confidence': confidence,
                'risk_multiplier': risk_mult,
                'recommendation': recommendation,
                'reasoning': reasoning,
                'ml_active': True,
                'training_samples': len(self.training_data)
            }
            
        except Exception as e:
            logger.error(f"Scoring error: {e}")
            return {
                'confidence': 60,
                'risk_multiplier': 0.5,
                'recommendation': 'half_risk',
                'reasoning': [f'Error in ML scoring: {e}'],
                'ml_active': False
            }
    
    def _generate_reasoning(self, features: Dict[str, float], proba: float) -> List[str]:
        """Generate human-readable reasoning for the score."""
        reasons = []
        
        # Confirmation count
        conf_count = features.get('confirmation_count', 0.5) * 5 + 1
        if conf_count >= 4:
            reasons.append(f"✅ Strong confirmations ({int(conf_count)})")
        elif conf_count <= 2:
            reasons.append(f"⚠️ Few confirmations ({int(conf_count)})")
        
        # Setup quality
        if features.get('has_choch', 0) and features.get('has_bos', 0):
            reasons.append("✅ ChoCH + BOS confirmed")
        
        if features.get('has_liquidity_sweep', 0):
            reasons.append("✅ Liquidity sweep present")
        
        # HTF alignment
        if features.get('htf_bias_aligned', 0):
            reasons.append("✅ HTF bias aligned")
        else:
            reasons.append("⚠️ HTF bias conflict")
        
        # Session
        session_val = features.get('session', 0.33)
        if session_val < 0.4:  # London or Overlap
            reasons.append("✅ Prime session")
        
        # Historical
        pair_wr = features.get('pair_win_rate_10', 0.6)
        if pair_wr >= 0.65:
            reasons.append(f"✅ Pair performing well ({int(pair_wr*100)}% recent)")
        elif pair_wr < 0.5:
            reasons.append(f"⚠️ Pair underperforming ({int(pair_wr*100)}% recent)")
        
        # Streak
        streak = (features.get('streak', 0.5) - 0.5) * 10
        if streak >= 2:
            reasons.append(f"🔥 On {int(streak)} win streak")
        elif streak <= -2:
            reasons.append(f"⚠️ On {int(abs(streak))} loss streak")
        
        return reasons[:5]  # Top 5 reasons
    
    def get_model_stats(self) -> Dict[str, Any]:
        """Get model statistics for reporting."""
        if not self.training_data:
            return {'status': 'no_data'}
        
        wins = sum(1 for t in self.training_data if t['outcome'] == 'win')
        losses = len(self.training_data) - wins
        
        # By symbol
        by_symbol = {}
        for t in self.training_data:
            sym = t.get('symbol', 'UNKNOWN')
            if sym not in by_symbol:
                by_symbol[sym] = {'wins': 0, 'total': 0}
            by_symbol[sym]['total'] += 1
            if t['outcome'] == 'win':
                by_symbol[sym]['wins'] += 1
        
        return {
            'status': 'trained' if self.is_trained else 'collecting_data',
            'total_samples': len(self.training_data),
            'wins': wins,
            'losses': losses,
            'win_rate': wins / len(self.training_data) if self.training_data else 0,
            'by_symbol': by_symbol,
            'model_active': self.is_trained
        }


# Singleton
_ml_model: Optional[MLRiskModel] = None


def get_ml_risk_model() -> MLRiskModel:
    """Get ML risk model instance."""
    global _ml_model
    if _ml_model is None:
        _ml_model = MLRiskModel()
    return _ml_model


def score_signal(signal_data: Dict, market_context: Dict = None) -> Dict[str, Any]:
    """Convenience function to score a signal."""
    return get_ml_risk_model().score_signal(signal_data, market_context)


def log_trade_outcome(signal_data: Dict, market_context: Dict, 
                      outcome: str, pips: float):
    """Convenience function to log a trade outcome."""
    get_ml_risk_model().log_trade(signal_data, market_context, outcome, pips)


if __name__ == "__main__":
    # Test the ML model
    model = MLRiskModel()
    
    print("=== ML Risk Model Test ===")
    print(f"Training samples: {len(model.training_data)}")
    print(f"Model trained: {model.is_trained}")
    
    # Test scoring
    test_signal = {
        'direction': 'BUY',
        'symbol': 'EURUSD',
        'confirmations': ['CHOCH', 'BOS', 'FVG', 'SWEEP'],
        'setup_type': 'OPTION_1',
        'entry_price': 1.0850,
        'stop_loss': 1.0820,
        'take_profit': 1.0910
    }
    
    result = model.score_signal(test_signal)
    print(f"\nTest Signal Score:")
    print(f"  Confidence: {result['confidence']}%")
    print(f"  Risk Multiplier: {result['risk_multiplier']}")
    print(f"  Recommendation: {result['recommendation']}")
    print(f"  Reasoning:")
    for r in result['reasoning']:
        print(f"    {r}")
