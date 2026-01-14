"""
Real-time Price Feed
Manages streaming price updates from forex brokers.
"""

from typing import Callable, Dict, List
from dataclasses import dataclass
from enum import Enum
import threading
import time


@dataclass
class TickData:
    """Represents a price tick."""
    symbol: str
    bid: float
    ask: float
    timestamp: int


class PriceFeed:
    """Real-time price feed from broker."""

    def __init__(self):
        self.subscriptions: Dict[str, List[Callable]] = {}
        self.running = False
        self.feed_thread = None

    def subscribe(self, symbol: str, callback: Callable[[TickData], None]):
        """
        Subscribe to price updates for a symbol.
        
        Args:
            symbol: Trading pair (e.g., "EURUSD")
            callback: Function to call with each tick
        """
        if symbol not in self.subscriptions:
            self.subscriptions[symbol] = []
        
        self.subscriptions[symbol].append(callback)

    def unsubscribe(self, symbol: str, callback: Callable):
        """Unsubscribe from price updates."""
        if symbol in self.subscriptions:
            self.subscriptions[symbol].remove(callback)

    def publish_tick(self, tick: TickData):
        """Publish a price tick to all subscribers."""
        if tick.symbol in self.subscriptions:
            for callback in self.subscriptions[tick.symbol]:
                try:
                    callback(tick)
                except Exception as e:
                    print(f"Error in callback: {e}")

    def start(self):
        """Start the price feed."""
        if not self.running:
            self.running = True
            self.feed_thread = threading.Thread(target=self._feed_loop, daemon=True)
            self.feed_thread.start()

    def stop(self):
        """Stop the price feed."""
        self.running = False

    def _feed_loop(self):
        """Main feed loop - should be overridden in subclass."""
        while self.running:
            time.sleep(1)
