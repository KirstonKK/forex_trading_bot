"""
Main Trading Bot - SMC Strategy
Implements Smart Money Concepts trading strategy with strict risk management.
"""

from typing import List, Dict, Optional
from datetime import datetime
import time

from core.smc_strategy import SMCAnalyzer, SMCEntrySignal
from core.enhanced_risk_manager import EnhancedRiskManager, TradingSession
from core.trade_executor import TradeExecutor, ActiveTrade
from connectors.forex_api import ForexConnector, MT5Connector
from connectors.price_feed import PriceFeed, TickData
from database.trades import TradesDatabase
from database.journal import TradeJournal
from utils.config import Config
from utils.logger import Logger


class ForexTradingBot:
    """Main trading bot orchestrator using SMC strategy."""

    def __init__(self, broker: ForexConnector, config: Optional[Config] = None):
        """
        Initialize the trading bot.
        
        Args:
            broker: Forex broker connector (MT5, etc.)
            config: Configuration object
        """
        self.broker = broker
        self.config = config or Config()
        self.logger = Logger.get_logger()
        
        # Core SMC strategy components
        self.analyzer = SMCAnalyzer()
        self.risk_manager = EnhancedRiskManager(
            account_balance=self.config.get("account_balance", 10000.0),
            risk_per_trade=self.config.get("risk_percent", 1.0),
            max_daily_loss=1.5,
            max_weekly_loss=3.0,
            max_trades_per_day=2,
            allowed_sessions=[TradingSession.LONDON, TradingSession.NEW_YORK]
        )
        self.executor = TradeExecutor()
        
        # Data storage
        self.database = TradesDatabase()
        self.journal = TradeJournal()
        self.price_feed = PriceFeed()
        
        # State
        self.running = False
        self.symbols = self.config.get("symbols", ["EURUSD", "GBPUSD", "XAUUSD"])
        
        self.logger.info(f"ForexTradingBot initialized with {len(self.symbols)} symbols")
        self.logger.info(f"Risk per trade: {self.risk_manager.risk_per_trade}%")
        self.logger.info(f"Max daily loss: {self.risk_manager.max_daily_loss}%")
        self.logger.info(f"Sessions: {[s.value for s in self.risk_manager.allowed_sessions]}")

    def connect(self) -> bool:
        """Connect to broker."""
        if not self.broker.connect():
            self.logger.error("Failed to connect to broker")
            return False
        
        self.logger.info(f"Connected to {self.broker.broker_type.value} broker")
        return True

    def disconnect(self):
        """Disconnect from broker."""
        self.price_feed.stop()
        self.broker.disconnect()
        self.logger.info("Disconnected from broker")

    def analyze_symbol(self, symbol: str) -> Optional[SMCEntrySignal]:
        """
        Analyze a symbol for SMC entry signals.
        
        Args:
            symbol: Trading pair (e.g., "EURUSD")
            
        Returns:
            SMC entry signal if found, None otherwise
        """
        timeframe = self.config.get("timeframe", "H1")
        bars = self.config.get("lookback_periods", 50)
        
        # Fetch historical data
        candles = self.broker.get_historical_data(symbol, timeframe, bars)
        
        if not candles:
            self.logger.warning(f"No candles for {symbol}")
            return None
        
        # Convert to dict format for analyzer
        candle_dicts = [
            {
                'timestamp': c.timestamp,
                'open': c.open,
                'high': c.high,
                'low': c.low,
                'close': c.close,
                'volume': c.volume
            }
            for c in candles
        ]
        
        # Analyze with SMC methodology
        signal = self.analyzer.analyze(candle_dicts)
        
        if signal:
            self.logger.info(f"SMC Signal found in {symbol}: {signal.entry_zone_type.value}")
        
        return signal

    def process_signal(self, symbol: str, signal: SMCEntrySignal) -> Optional[ActiveTrade]:
        """
        Process an entry signal and execute trade if valid.
        
        Args:
            symbol: Trading pair
            signal: SMC entry signal
            
        Returns:
            Active trade if executed, None otherwise
        """
        # Check if can trade
        can_trade_checks = self.risk_manager.can_open_trade()
        
        if not all(can_trade_checks.values()):
            reasons = [k for k, v in can_trade_checks.items() if not v]
            self.logger.warning(f"Cannot open trade in {symbol}: {reasons}")
            return None
        
        # Get current price
        symbol_data = self.broker.get_symbol(symbol)
        if not symbol_data:
            self.logger.warning(f"Cannot get price for {symbol}")
            return None
        
        # Validate RR ratio
        if signal.risk_reward_ratio < 2.0:
            self.logger.warning(f"RR ratio too low: {signal.risk_reward_ratio:.2f}")
            return None
        
        # Calculate position size
        position_size = self.risk_manager.calculate_position_size(
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            symbol=symbol
        )
        
        if position_size <= 0:
            self.logger.warning(f"Invalid position size for {symbol}")
            return None
        
        # Validate trade
        validation = self.risk_manager.validate_trade(
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            target_price=signal.target_price
        )
        
        if not all(validation.values()):
            self.logger.warning(f"Trade validation failed in {symbol}")
            return None
        
        # Execute trade
        trade = self.executor.open_trade(
            symbol=symbol,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            target_price=signal.target_price,
            quantity=position_size
        )
        
        # Log to journal
        session = self.risk_manager.get_active_session()
        self._save_to_journal(trade, signal, session)
        
        self.logger.info(
            f"Trade opened: {symbol} @ {signal.entry_price:.5f} "
            f"SL: {signal.stop_loss:.5f} TP: {signal.target_price:.5f} "
            f"RR: {signal.risk_reward_ratio:.2f} Zone: {signal.entry_zone_type.value}"
        )
        
        return trade

    def check_active_trades(self):
        """Check active trades against current prices."""
        for trade_id, trade in list(self.executor.active_trades.items()):
            symbol_data = self.broker.get_symbol(trade.symbol)
            if not symbol_data:
                continue
            
            current_price = symbol_data.bid
            
            # Check stop loss
            if trade.stop_loss_order and current_price <= trade.stop_loss_order.price:
                self.executor.hit_stop_loss(trade_id)
                self.logger.info(f"Trade {trade_id} hit stop loss")
                continue
            
            # Check take profit
            if trade.take_profit_order and current_price >= trade.take_profit_order.price:
                self.executor.hit_take_profit(trade_id)
                self.logger.info(f"Trade {trade_id} hit take profit")

    def scan_and_trade(self):
        """Main trading loop - scan symbols for SMC signals."""
        while self.running:
            try:
                for symbol in self.symbols:
                    # Analyze symbol for SMC signals
                    signal = self.analyze_symbol(symbol)
                    
                    # Process signal if found
                    if signal and signal.strength >= 0.6:
                        trade = self.process_signal(symbol, signal)
                
                # Check active trades
                self.check_active_trades()
                
                # Brief pause before next scan
                time.sleep(60)
            
            except Exception as e:
                self.logger.error(f"Error in trading loop: {e}")
                time.sleep(60)

    def _save_to_journal(self, trade: ActiveTrade, signal: SMCEntrySignal, session):
        """Save trade details to journal."""
        trade_data = {
            'id': trade.trade_id,
            'symbol': trade.symbol,
            'session': session.value if session else 'unknown',
            'entry_time': trade.entry_time.isoformat(),
            'entry_price': trade.entry_order.price,
            'stop_loss': trade.stop_loss_order.price,
            'take_profit': trade.take_profit_order.price,
            'quantity': trade.entry_order.quantity,
            'status': 'open',
            'entry_zone_type': signal.entry_zone_type.value,
            'bos_strength': signal.bos.strength,
            'pullback_confidence': signal.pullback_zone.confidence,
            'signal_strength': signal.strength,
            'risk_reward_ratio': signal.risk_reward_ratio,
            'risk_amount': trade.entry_order.quantity * abs(signal.entry_price - signal.stop_loss),
            'reward_amount': trade.entry_order.quantity * abs(signal.target_price - signal.entry_price),
            'account_balance_at_entry': self.risk_manager.account_balance
        }
        self.journal.log_trade(trade_data)

    def get_stats(self) -> Dict:
        """Get trading statistics."""
        stats = self.executor.get_trade_stats()
        account_info = self.broker.get_account_info()
        
        return {
            **stats,
            'account_balance': account_info.get('balance', 0),
            'account_equity': account_info.get('equity', 0),
            'active_trades': len(self.executor.active_trades),
            'margin_used': account_info.get('margin', 0)
        }

    def run(self):
        """Start the trading bot."""
        if not self.connect():
            return
        
        self.running = True
        self.logger.info("Trading bot started")
        
        try:
            self.scan_and_trade()
        except KeyboardInterrupt:
            self.logger.info("Trading bot stopped by user")
        finally:
            self.running = False
            self.disconnect()

    def start_demo(self):
        """Start in demo/backtest mode without real broker."""
        self.running = True
        self.logger.info("Demo mode started")
        self.logger.info(f"Risk management: {self.risk_manager.get_risk_summary()}")
        
        # Demo: just analyze symbols without executing
        for symbol in self.symbols:
            signal = self.analyze_symbol(symbol)
            if signal:
                self.logger.info(
                    f"Demo: SMC signal in {symbol} - "
                    f"Zone: {signal.entry_zone_type.value}, "
                    f"RR: {signal.risk_reward_ratio:.2f}"
                )


if __name__ == "__main__":
    # Example usage
    config = Config()
    
    # Demo mode (no real broker)
    if config.get("demo_mode", True):
        bot = ForexTradingBot(
            broker=MT5Connector(0, "", ""),  # Dummy values
            config=config
        )
        bot.start_demo()
    else:
        # Real trading with MT5
        bot = ForexTradingBot(
            broker=MT5Connector(
                login=int(config.get("mt5_login")),
                password=config.get("mt5_password"),
                server=config.get("mt5_server", "ICMarketsSC-Demo")
            ),
            config=config
        )
        bot.run()
