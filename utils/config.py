"""
Configuration Management
Handles bot configuration from environment and config files.
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, Optional


class Config:
    """Configuration manager."""

    # Default configuration
    DEFAULTS = {
        "account_balance": 10000.0,
        "risk_percent": 1.0,
        "symbols": ["EURUSD", "GBPUSD", "USDJPY"],
        "timeframe": "H1",
        "lookback_periods": 50,
        "min_rr_ratio": 1.5,
        "broker": "mt5",
        "demo_mode": True
    }

    def __init__(self, config_path: str = "config/config.json"):
        self.config_path = Path(config_path)
        self._config = self.DEFAULTS.copy()
        self.load()

    def load(self):
        """Load configuration from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    file_config = json.load(f)
                    self._config.update(file_config)
            except Exception as e:
                print(f"Error loading config: {e}")

    def save(self):
        """Save configuration to file."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(self._config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        env_key = f"FOREX_BOT_{key.upper()}"
        
        # Environment variable takes precedence
        if env_key in os.environ:
            return os.environ[env_key]
        
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        """Set configuration value."""
        self._config[key] = value

    def to_dict(self) -> Dict:
        """Get config as dictionary."""
        return self._config.copy()
