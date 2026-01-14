"""
LSTM Price Predictor
Deep learning model for sequence prediction and price forecasting.
"""

from typing import List, Tuple, Optional
import numpy as np
from pathlib import Path


class LSTMPricePredictor:
    """LSTM model for time series price prediction."""

    def __init__(self, model_path: str = "machine_learning/models/lstm_price.h5"):
        self.model_path = Path(model_path)
        self.model = None
        self.trained = False
        self.sequence_length = 60  # Use 60 candles for prediction
        self.feature_count = 6  # OHLCV + volume
        self.load_model()

    def build_model(self):
        """Build LSTM architecture."""
        try:
            from tensorflow import keras
            from tensorflow.keras import layers
            
            model = keras.Sequential([
                layers.LSTM(64, return_sequences=True, input_shape=(self.sequence_length, self.feature_count)),
                layers.Dropout(0.2),
                layers.LSTM(32, return_sequences=False),
                layers.Dropout(0.2),
                layers.Dense(16, activation='relu'),
                layers.Dense(1, activation='linear')  # Predict next close price
            ])
            
            model.compile(optimizer='adam', loss='mse', metrics=['mae'])
            self.model = model
            return True
        except ImportError:
            print("tensorflow/keras not installed")
            return False

    def prepare_sequences(
        self,
        prices: List[float],
        labels: Optional[List[float]] = None
    ) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """
        Prepare price sequences for LSTM training.
        
        Args:
            prices: List of price points (OHLCV as flattened array)
            labels: Target values (next price), optional
            
        Returns:
            Tuple of (X sequences, y labels)
        """
        X = []
        y = [] if labels else None
        
        for i in range(len(prices) - self.sequence_length):
            X.append(prices[i:i + self.sequence_length])
            if labels:
                y.append(labels[i + self.sequence_length])
        
        X = np.array(X)
        if labels:
            y = np.array(y)
        
        return X, y

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 50,
        batch_size: int = 32
    ) -> bool:
        """
        Train the LSTM model.
        
        Args:
            X: Input sequences (n_sequences, sequence_length, features)
            y: Target values
            epochs: Number of training epochs
            batch_size: Batch size
            
        Returns:
            True if training successful
        """
        try:
            if self.model is None:
                if not self.build_model():
                    return False
            
            # Validate input shape
            if len(X.shape) != 3:
                print(f"Expected 3D input, got {len(X.shape)}D")
                return False
            
            self.model.fit(
                X, y,
                epochs=epochs,
                batch_size=batch_size,
                validation_split=0.2,
                verbose=0
            )
            
            self.trained = True
            self.save_model()
            return True
        except Exception as e:
            print(f"Training error: {e}")
            return False

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Make predictions.
        
        Args:
            X: Input sequences
            
        Returns:
            Predicted values
        """
        if not self.trained or self.model is None:
            return np.array([])
        
        try:
            return self.model.predict(X, verbose=0)
        except Exception as e:
            print(f"Prediction error: {e}")
            return np.array([])

    def predict_next_price(self, sequence: np.ndarray) -> float:
        """Predict next price from a sequence."""
        if not self.trained or self.model is None:
            return 0.0
        
        try:
            pred = self.model.predict(sequence.reshape(1, self.sequence_length, self.feature_count), verbose=0)
            return float(pred[0][0])
        except Exception:
            return 0.0

    def save_model(self) -> bool:
        """Save model to disk."""
        if not self.trained or self.model is None:
            return False
        
        try:
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            self.model.save(str(self.model_path))
            return True
        except Exception as e:
            print(f"Error saving model: {e}")
            return False

    def load_model(self) -> bool:
        """Load model from disk."""
        if not self.model_path.exists():
            return False
        
        try:
            from tensorflow import keras
            self.model = keras.models.load_model(str(self.model_path))
            self.trained = True
            return True
        except Exception:
            return False
