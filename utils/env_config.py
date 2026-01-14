"""
Environment configuration for live trading.
"""

import os
from pathlib import Path


def load_env():
    """Load environment variables from .env file if it exists."""
    env_file = Path(__file__).parent / ".env"
    
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()


def get_mt5_credentials():
    """Get MT5 credentials from environment."""
    load_env()
    
    login = os.getenv("MT5_LOGIN")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")
    
    if not login or not password or not server:
        raise ValueError(
            "Missing MT5 credentials. Set MT5_LOGIN, MT5_PASSWORD, and MT5_SERVER "
            "as environment variables or in .env file"
        )
    
    return int(login), password, server
