"""
Logging Utility
Structured logging for the trading bot.
"""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional


class Logger:
    """Logging configuration and utility."""

    _instance: Optional['Logger'] = None
    _logger: Optional[logging.Logger] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_logger()
        return cls._instance

    def _init_logger(self):
        """Initialize the logger."""
        log_path = Path("logs")
        log_path.mkdir(exist_ok=True)
        
        self._logger = logging.getLogger("forex_bot")
        self._logger.setLevel(logging.DEBUG)
        
        # File handler
        file_handler = logging.handlers.RotatingFileHandler(
            log_path / "bot.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self._logger.addHandler(file_handler)
        self._logger.addHandler(console_handler)

    @staticmethod
    def get_logger() -> logging.Logger:
        """Get the logger instance."""
        instance = Logger()
        return instance._logger

    @staticmethod
    def debug(msg: str, *args, **kwargs):
        """Log debug message."""
        Logger.get_logger().debug(msg, *args, **kwargs)

    @staticmethod
    def info(msg: str, *args, **kwargs):
        """Log info message."""
        Logger.get_logger().info(msg, *args, **kwargs)

    @staticmethod
    def warning(msg: str, *args, **kwargs):
        """Log warning message."""
        Logger.get_logger().warning(msg, *args, **kwargs)

    @staticmethod
    def error(msg: str, *args, **kwargs):
        """Log error message."""
        Logger.get_logger().error(msg, *args, **kwargs)

    @staticmethod
    def critical(msg: str, *args, **kwargs):
        """Log critical message."""
        Logger.get_logger().critical(msg, *args, **kwargs)
