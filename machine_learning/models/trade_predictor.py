"""
LightGBM Trade Outcome Predictor
Learns from trade history to predict win/loss and profit outcomes.
"""

from typing import List, Dict, Tuple, Optional
import numpy as np
from pathlib import Path


class TradeOutcomePredictor:
    """LightGBM model for predicting trade outcomes."""

    def __init__(self, model_path: str = "machine_learning/models/trade_predictor.pkl"):
        self.model_path = Path(model_path)
        self.model = None
        self.feature_names = [
            'entry_price', 'stop_loss', 'take_profit', 'risk_reward_ratio',
            'entry_volume', 'spread_at_entry', 'pattern_type', 'pattern_strength',
            'volatility_at_entry', 'trend_direction', 'market_regime',
            'hour_of_day', 'day_of_week'
        ]
        self.trained = False
        self.load_model()

    def train(self, X: np.ndarray, y: np.ndarray) -> bool:
        """
        Train the model on historical trade data.
        
        Args:
            X: Feature matrix (n_trades, n_features)
            y: Target vector (win=1, loss=0)
            
        Returns:
            True if training successful
        """
        try:
            import lightgbm as lgb
            
            if len(X) < 10:
                print("Not enough trades for training (need at least 10)")
                return False
            
            # Create dataset
            train_data = lgb.Dataset(
                X,
                label=y,
                feature_names=self.feature_names
            )
            
            # Train model
            params = {
                'objective': 'binary',
                'metric': 'binary_logloss',
                'num_leaves': 31,
                'learning_rate': 0.05,
                'verbose': -1
            }
            
            self.model = lgb.train(
                params,
                train_data,
                num_boost_round=100
            )
            
            self.trained = True
            self.save_model()
            
            return True
        except ImportError:
            print("lightgbm not installed. Install with: pip install lightgbm")
            return False
        except Exception as e:
            print(f"Training error: {e}")
            return False

    def predict(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Predict trade outcomes.
        
        Args:
            X: Feature matrix
            
        Returns:
            Tuple of (predictions, probabilities)
        """
        if not self.trained or self.model is None:
            return np.array([]), np.array([])
        
        try:
            probabilities = self.model.predict(X)
            predictions = (probabilities >= 0.5).astype(int)
            return predictions, probabilities
        except Exception as e:
            print(f"Prediction error: {e}")
            return np.array([]), np.array([])

    def predict_single(self, features: np.ndarray) -> Tuple[int, float]:
        """Predict outcome for a single trade."""
        preds, probs = self.predict(features.reshape(1, -1))
        if len(preds) > 0:
            return int(preds[0]), float(probs[0])
        return 0, 0.5

    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance scores."""
        if not self.trained or self.model is None:
            return {}
        
        try:
            importance = self.model.feature_importance()
            return dict(zip(self.feature_names, importance))
        except Exception:
            return {}

    def save_model(self) -> bool:
        """Save model to disk."""
        if not self.trained or self.model is None:
            return False
        
        try:
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            self.model.save_model(str(self.model_path))
            return True
        except Exception as e:
            print(f"Error saving model: {e}")
            return False

    def load_model(self) -> bool:
        """Load model from disk."""
        if not self.model_path.exists():
            return False
        
        try:
            import lightgbm as lgb
            self.model = lgb.Booster(model_file=str(self.model_path))
            self.trained = True
            return True
        except Exception:
            return False
