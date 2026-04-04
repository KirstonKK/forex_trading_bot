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

try:
    from xgboost import XGBClassifier
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBClassifier = None
    XGBOOST_AVAILABLE = False

logger = logging.getLogger(__name__)

# Data paths
DATA_DIR = Path(__file__).parent.parent / 'data'
ML_DIR = DATA_DIR / 'ml'
TRAINING_DATA_FILE = ML_DIR / 'training_data.json'
MODEL_FILE = ML_DIR / 'risk_model.pkl'
FEATURE_STATS_FILE = ML_DIR / 'feature_stats.json'


class FeatureExtractor:
    """Extract ML features from trade setup data."""
    
    # All known setup types (ordered — index / max used for encoding)
    SETUP_TYPES = [
        'OPTION_1', 'OPTION_2', 'OPTION_3',
        'OPTION_4', 'LIQ_SWEEP_ENGULF',        # US30 primary
        'OPTION_5', 'OPTION_6',
        'OPTION_7', 'BREAKER_BLOCK',
        'OPTION_8', 'ORB_BREAKOUT',             # US30 opening range
    ]

    # Feature definitions with normalization ranges
    FEATURE_SCHEMA = {
        # Setup features
        'confirmation_count': {'min': 1, 'max': 6, 'default': 3},
        'setup_type': {'min': 0, 'max': 1, 'default': 0},
        'has_choch': {'boolean': True, 'default': 0},
        'has_bos': {'boolean': True, 'default': 0},
        'has_fvg': {'boolean': True, 'default': 0},
        'has_ob': {'boolean': True, 'default': 0},
        'has_liquidity_sweep': {'boolean': True, 'default': 0},
        'fvg_size_pct': {'min': 0, 'max': 2.0, 'default': 0.5},
        'ob_strength': {'min': 0, 'max': 1.0, 'default': 0.5},
        'distance_to_sl_pips': {'min': 5, 'max': 500, 'default': 20},

        # Market context
        'atr_normalized': {'min': 0, 'max': 2.0, 'default': 1.0},
        'session': {'min': 0, 'max': 1, 'default': 0},
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

        # ── US30 / ORB-specific features ──────────────────────────────────────
        # These are 0 for all forex signals (no penalty — tree models handle sparsity).
        'is_us30': {'boolean': True, 'default': 0},
        'is_orb_setup': {'boolean': True, 'default': 0},
        # ORB range size in points (normalized 0-1 over 0–500 pt range)
        'orb_range_pts': {'min': 0, 'max': 500, 'default': 0},
        # How far price broke beyond the ORB boundary before our entry (0-200 pts)
        'orb_breakout_dist_pts': {'min': 0, 'max': 200, 'default': 0},
        # Overnight gap size in points (|today open − yesterday close|)
        'gap_size_pts': {'min': 0, 'max': 300, 'default': 0},
        # NYSE open proximity: minutes elapsed since 13:30 UTC (0 = right at open)
        'mins_since_nyse_open': {'min': 0, 'max': 90, 'default': 45},
        # 4H trend strength specifically for US30 (reused trend_strength for forex)
        'us30_4h_trend': {'min': -1, 'max': 1, 'default': 0},
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
        features['confirmation_count'] = self._normalize(len(confirmations), 1, 6)

        # Setup type — encoded as position in SETUP_TYPES list (0-1).
        # Handles all known option names including US30 aliases.
        setup_type = signal_data.get('setup_type', 'OPTION_1')
        max_idx = max(len(self.SETUP_TYPES) - 1, 1)
        if setup_type in self.SETUP_TYPES:
            features['setup_type'] = self.SETUP_TYPES.index(setup_type) / max_idx
        else:
            features['setup_type'] = 0.0

        # Boolean confirmations
        confirmations_str = str(confirmations).upper()
        features['has_choch'] = 1.0 if 'CHOCH' in confirmations_str else 0.0
        features['has_bos'] = 1.0 if 'BOS' in confirmations_str else 0.0
        features['has_fvg'] = 1.0 if 'FVG' in confirmations_str else 0.0
        features['has_ob'] = 1.0 if any(x in confirmations_str for x in ('OB', 'ORDER_BLOCK')) else 0.0
        features['has_liquidity_sweep'] = 1.0 if any(x in confirmations_str for x in ('SWEEP', 'LIQ')) else 0.0

        # FVG size (if available)
        fvg_size = signal_data.get('fvg_size_pct', 0.5)
        features['fvg_size_pct'] = self._normalize(fvg_size, 0, 2.0)

        # OB strength
        ob_strength = signal_data.get('ob_strength', 0.5)
        features['ob_strength'] = self._normalize(ob_strength, 0, 1.0)

        # Distance to SL — use points for US30, pips for forex
        symbol = signal_data.get('symbol', 'EURUSD')
        entry = signal_data.get('entry_price', 0)
        sl = signal_data.get('stop_loss', 0)
        _is_us30 = 'US30' in symbol.upper() or 'US_30' in symbol.upper()
        if entry and sl:
            sl_distance = abs(entry - sl)
            if _is_us30:
                sl_units = sl_distance  # already in points
            elif 'XAU' in symbol.upper():
                sl_units = sl_distance * 10
            else:
                sl_units = sl_distance * 10000  # forex pips
            features['distance_to_sl_pips'] = self._normalize(sl_units, 5, 500)
        else:
            features['distance_to_sl_pips'] = 0.5

        # === Market Context ===
        # ATR normalization (1.0 = average volatility)
        atr = market_context.get('atr', 1.0)
        avg_atr = market_context.get('avg_atr', atr)
        features['atr_normalized'] = self._normalize(atr / avg_atr if avg_atr else 1.0, 0.5, 2.0)

        # Session (forex: LONDON/NY/OVERLAP/OFF; US30: NYSE_OPEN or same)
        session = market_context.get('session', 'LONDON')
        session_options = ['LONDON', 'NYSE_OPEN', 'NY', 'OVERLAP', 'OFF']
        if session in session_options:
            features['session'] = session_options.index(session) / (len(session_options) - 1)
        else:
            features['session'] = 0.33

        # Trend strength (-1 to 1)
        trend = market_context.get('trend_strength', 0)
        features['trend_strength'] = self._normalize(trend, -1, 1)

        # Time features
        now = datetime.utcnow()
        session_start = market_context.get('session_open_hour', 10)  # 13 for US30, 10 for forex
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

        # === US30 / ORB-specific Features ===
        _is_orb = setup_type in ('OPTION_8', 'ORB_BREAKOUT')
        features['is_us30'] = 1.0 if _is_us30 else 0.0
        features['is_orb_setup'] = 1.0 if _is_orb else 0.0

        if _is_us30:
            # ORB range size in points (high - low of first 30min)
            orb_range = market_context.get('orb_range_pts', signal_data.get('orb_range_pts', 0))
            features['orb_range_pts'] = self._normalize(orb_range, 0, 500)

            # How far breakout extended beyond the ORB boundary
            orb_break = market_context.get('orb_breakout_dist_pts',
                                           signal_data.get('orb_breakout_dist_pts', 0))
            features['orb_breakout_dist_pts'] = self._normalize(orb_break, 0, 200)

            # Overnight gap size (|today open − yesterday close|)
            gap = market_context.get('gap_size_pts', signal_data.get('gap_size_pts', 0))
            features['gap_size_pts'] = self._normalize(gap, 0, 300)

            # Minutes elapsed since NYSE open (13:30 UTC)
            nyse_open_minutes = now.hour * 60 + now.minute - (13 * 60 + 30)
            mins_since = max(0, min(90, nyse_open_minutes))
            features['mins_since_nyse_open'] = self._normalize(mins_since, 0, 90)

            # 4H trend (separate from forex trend_strength so model can distinguish)
            features['us30_4h_trend'] = self._normalize(
                market_context.get('us30_4h_trend', trend), -1, 1
            )
        else:
            # Zero out US30-only features for forex signals
            features['orb_range_pts'] = 0.0
            features['orb_breakout_dist_pts'] = 0.0
            features['gap_size_pts'] = 0.0
            features['mins_since_nyse_open'] = 0.0
            features['us30_4h_trend'] = 0.0

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
    
    Uses XGBoost for non-linear feature interactions and robust ranking.
    
    Outputs confidence score 0-100% used for position sizing.
    """
    
    def __init__(self):
        ML_DIR.mkdir(parents=True, exist_ok=True)
        self.feature_extractor = FeatureExtractor()
        self.model = None
        self.is_trained = False
        self.training_data: List[Dict] = []
        self.min_training_samples = 20  # Minimum trades before using ML (lowered from 30)
        
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
                if isinstance(self.model, dict) and self.model.get('model_type') in ('xgboost', 'simple'):
                    self.is_trained = True
                    logger.info(f"ML risk model loaded ({self.model.get('model_type')})")
                elif isinstance(self.model, dict) and 'weights' in self.model:
                    self.model = {
                        'model_type': 'simple',
                        'weights': self.model.get('weights', []),
                        'bias': self.model.get('bias', 0.5),
                        'score_mean': self.model.get('score_mean', 0.5),
                        'score_std': self.model.get('score_std', 0.1),
                        'win_score_mean': self.model.get('win_score_mean', 0.55),
                        'loss_score_mean': self.model.get('loss_score_mean', 0.45),
                        'feature_names': self.feature_extractor.get_feature_names(),
                    }
                    self.is_trained = True
                    logger.info("ML risk model loaded (legacy simple model)")
                else:
                    self.is_trained = False
                    logger.warning("ML model file format not recognized")
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
            
            if not XGBOOST_AVAILABLE:
                return {
                    'status': 'error',
                    'message': 'xgboost is required but not installed. Install dependencies from requirements.txt.'
                }

            self.model = self._train_xgboost_model(X, y)
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
                'feature_count': X.shape[1],
                'model_type': self.model.get('model_type', 'unknown')
            }
            
            logger.info(f"ML Model trained: {metrics}")
            return metrics
            
        except Exception as e:
            logger.error(f"Training error: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _train_xgboost_model(self, X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
        """Train an XGBoost binary classifier and persist full model metadata."""
        positives = int(np.sum(y == 1))
        negatives = int(np.sum(y == 0))
        scale_pos_weight = float(negatives / max(positives, 1)) if positives > 0 else 1.0

        estimator = XGBClassifier(
            n_estimators=250,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            objective='binary:logistic',
            eval_metric='logloss',
            random_state=42,
            n_jobs=1,
            reg_lambda=1.0,
            min_child_weight=2,
            scale_pos_weight=scale_pos_weight,
        )
        estimator.fit(X, y)

        train_proba = estimator.predict_proba(X)[:, 1]

        return {
            'model_type': 'xgboost',
            'estimator': estimator,
            'feature_names': self.feature_extractor.get_feature_names(),
            'class_balance': {
                'wins': positives,
                'losses': negatives,
            },
            'train_proba_mean': float(np.mean(train_proba)),
            'train_proba_std': float(np.std(train_proba)),
            'trained_at': datetime.utcnow().isoformat(),
        }
    
    def _predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict win probability for samples across supported model types."""
        if not self.model:
            return np.full(len(X), 0.5)

        model_type = self.model.get('model_type', 'simple') if isinstance(self.model, dict) else 'simple'

        if model_type == 'xgboost':
            estimator = self.model.get('estimator')
            if estimator is None:
                return np.full(len(X), 0.5)
            probas = estimator.predict_proba(X)[:, 1]
            return np.clip(probas, 0.10, 0.90)

        if model_type == 'simple':
            weights = np.array(self.model.get('weights', []), dtype=float)
            if weights.size == 0:
                return np.full(len(X), 0.5)

            scores = np.dot(X, weights)
            score_mean = self.model.get('score_mean', 0.5)
            win_mean = self.model.get('win_score_mean', score_mean + 0.05)
            loss_mean = self.model.get('loss_score_mean', score_mean - 0.05)

            spread = max(win_mean - loss_mean, 0.01)
            midpoint = (win_mean + loss_mean) / 2

            z_scores = (scores - midpoint) / spread
            probas = 0.5 + z_scores * 0.25
            probas = 1 / (1 + np.exp(-4 * (probas - 0.5)))
            return np.clip(probas, 0.10, 0.90)

        return np.full(len(X), 0.5)
    
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
                'confidence': 50,
                'risk_multiplier': 0.5,
                'recommendation': 'half_risk',
                'reasoning': ['ML model not yet trained - using cautious default'],
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
