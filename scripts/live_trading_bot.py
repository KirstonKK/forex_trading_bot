"""
Live Trading Bot - MetaTrader5 Edition

Real-time SMC strategy execution on MT5.
Connects to MT5 account, fetches live data, analyzes patterns, and executes trades.

Usage:
    python3 live_trading_bot.py

Environment Variables:
    MT5_LOGIN: Account login number
    MT5_PASSWORD: Account password
    MT5_SERVER: Server name (e.g., 'OANDA_Global-Demo-1')
"""

import os
import logging
from datetime import datetime
from connectors.mt5_connector import MT5Connector
from core.smc_strategy import SMCStrategy
from core.enhanced_risk_manager import EnhancedRiskManager
from database.journal import TradeJournal
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LiveTradingBot:
    """
    Live trading bot using MetaTrader5.
    
    Polls market data, detects SMC signals, and executes trades with risk management.
    """
    
    def __init__(self, login: int, password: str, server: str, 
                 symbols: list = None, poll_interval: int = 300):
        """
        Initialize live trading bot.
        
        Args:
            login: MT5 account login
            password: MT5 account password
            server: MT5 server name
            symbols: List of symbols to trade (default: EURUSD, GBPUSD, XAUUSD)
            poll_interval: Seconds between data fetches (default: 300 = 5 min)
        """
        self.login = login
        self.password = password
        self.server = server
        self.symbols = symbols or ['EURUSD', 'GBPUSD', 'XAUUSD']
        self.poll_interval = poll_interval
        
        # Initialize MT5 connection
        logger.info("Initializing MT5 connection...")
        self.mt5 = MT5Connector(login, password, server)
        
        # Initialize strategy and risk management
        self.strategy = SMCStrategy()
        
        account_balance = self.mt5.get_account_balance()
        self.risk_manager = EnhancedRiskManager(
            account_balance=account_balance,
            risk_per_trade=0.01,  # 1%
            daily_loss_limit=0.015,  # 1.5%
            weekly_loss_limit=0.03   # 3%
        )
        
        # Initialize trade journal
        self.journal = TradeJournal(db_path='data/live_journal.db')
        
        # Track open positions (max 1 per symbol)
        self.open_positions = {}
        
        logger.info(f"Bot initialized. Account balance: ${account_balance:.2f}")
        logger.info(f"Trading symbols: {self.symbols}")
        logger.info(f"Poll interval: {self.poll_interval}s")
    
    def fetch_latest_candles(self, symbol: str, timeframe: str = 'M5', 
                            count: int = 100) -> dict:
        """
        Fetch latest candlestick data.
        
        Args:
            symbol: Symbol name
            timeframe: Timeframe (M5, M15, H1, etc)
            count: Number of candles
        
        Returns:
            Candle data dict
        """
        try:
            candles = self.mt5.get_candles(symbol, timeframe, count)
            logger.debug(f"Fetched {len(candles['close'])} candles for {symbol}")
            return candles
        except Exception as e:
            logger.error(f"Error fetching candles for {symbol}: {e}")
            return None
    
    def analyze_symbol(self, symbol: str) -> dict:
        """
        Analyze symbol for SMC signals.
        
        Args:
            symbol: Symbol to analyze
        
        Returns:
            Signal dict if found, None otherwise
        """
        try:
            # Fetch data
            candles = self.fetch_latest_candles(symbol, timeframe='M5', count=100)
            if not candles or not candles['close']:
                return None
            
            # Analyze with SMC strategy
            signal = self.strategy.analyze(candles)
            
            if signal:
                logger.info(f"Signal detected for {symbol}: {signal['direction']} "
                           f"at {signal['entry_price']:.5f}, "
                           f"SL: {signal['stop_loss']:.5f}, "
                           f"TP: {signal['take_profit']:.5f}")
            
            return signal
        
        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            return None
    
    def execute_trade(self, symbol: str, signal: dict) -> bool:
        """
        Execute trade based on signal.
        
        Args:
            symbol: Symbol to trade
            signal: Signal dict with direction, entry, SL, TP
        
        Returns:
            True if trade executed, False otherwise
        """
        try:
            # Check if already have position
            if symbol in self.open_positions:
                logger.warning(f"Already have open position for {symbol}, skipping")
                return False
            
            # Validate trade with risk manager
            current_balance = self.mt5.get_account_balance()
            is_valid = self.risk_manager.validate_trade(
                symbol=symbol,
                entry_price=signal['entry_price'],
                stop_loss=signal['stop_loss'],
                take_profit=signal['take_profit'],
                current_balance=current_balance
            )
            
            if not is_valid:
                logger.warning(f"Trade validation failed for {symbol}")
                return False
            
            # Calculate position size
            position_risk = self.risk_manager.calculate_position_size(
                entry_price=signal['entry_price'],
                stop_loss=signal['stop_loss'],
                current_balance=current_balance
            )
            
            # Get symbol info for contract size
            symbol_info = self.mt5.get_symbol_info(symbol)
            contract_size = symbol_info['contract_size']
            point = symbol_info['point']
            
            # Calculate volume (risk in dollars / point value)
            point_value = contract_size * point
            volume = max(0.01, position_risk / point_value)
            
            logger.info(f"Position size: ${position_risk:.2f}, Volume: {volume:.2f} lots")
            
            # Place order
            order_type = 'BUY' if signal['direction'] == 'LONG' else 'SELL'
            
            order_ticket = self.mt5.create_order(
                symbol=symbol,
                volume=volume,
                order_type=order_type,
                stop_loss=signal['stop_loss'],
                take_profit=signal['take_profit']
            )
            
            if not order_ticket:
                logger.error(f"Order placement failed for {symbol}")
                return False
            
            # Record in journal
            self.journal.log_trade(
                symbol=symbol,
                direction=signal['direction'],
                entry_price=signal['entry_price'],
                stop_loss=signal['stop_loss'],
                take_profit=signal['take_profit'],
                position_size=volume,
                entry_pattern=signal.get('pattern', 'SMC'),
                bos_strength=signal.get('bos_strength', 0),
                signal_strength=signal.get('signal_strength', 0),
                status='open'
            )
            
            # Track position
            self.open_positions[symbol] = {
                'ticket': order_ticket,
                'entry_price': signal['entry_price'],
                'stop_loss': signal['stop_loss'],
                'take_profit': signal['take_profit'],
                'volume': volume,
                'entry_time': datetime.now()
            }
            
            logger.info(f"Trade executed: {order_type} {volume:.2f} {symbol}")
            return True
        
        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            return False
    
    def check_positions(self):
        """
        Monitor and update open positions.
        Check for closed trades and clean up.
        """
        try:
            open_trades = self.mt5.get_open_trades()
            
            # Update position tracking
            symbols_in_trades = {trade['symbol'] for trade in open_trades}
            
            # Remove closed positions from tracking
            for symbol in list(self.open_positions.keys()):
                if symbol not in symbols_in_trades:
                    logger.info(f"Position closed: {symbol}")
                    del self.open_positions[symbol]
            
            # Display current positions
            if open_trades:
                print("\n" + "="*60)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Open Positions:")
                for trade in open_trades:
                    pnl = f"${trade['profit']:.2f}"
                    print(f"  {trade['symbol']}: {trade['type']} "
                          f"{trade['volume']} @ {trade['open_price']:.5f} "
                          f"({pnl})")
                print("="*60 + "\n")
            
            # Display balance
            balance = self.mt5.get_account_balance()
            print(f"Account Balance: ${balance:.2f}")
        
        except Exception as e:
            logger.error(f"Error checking positions: {e}")
    
    def run(self):
        """
        Main bot loop: fetch data, analyze, execute trades, monitor positions.
        """
        logger.info("Starting live trading bot...")
        print("\n" + "="*60)
        print("LIVE TRADING BOT - MT5 EDITION")
        print("="*60)
        print(f"Symbols: {self.symbols}")
        print(f"Poll Interval: {self.poll_interval}s")
        print("Press Ctrl+C to stop")
        print("="*60 + "\n")
        
        try:
            iteration = 0
            while True:
                iteration += 1
                timestamp = datetime.now().strftime('%H:%M:%S')
                
                logger.info(f"--- Iteration {iteration} ({timestamp}) ---")
                
                # Check existing positions
                self.check_positions()
                
                # Analyze each symbol
                for symbol in self.symbols:
                    logger.info(f"Analyzing {symbol}...")
                    signal = self.analyze_symbol(symbol)
                    
                    if signal and symbol not in self.open_positions:
                        logger.info(f"Executing trade for {symbol}")
                        self.execute_trade(symbol, signal)
                
                # Wait for next poll
                logger.info(f"Next poll in {self.poll_interval}s")
                time.sleep(self.poll_interval)
        
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            print("\n" + "="*60)
            print("Bot stopped by user")
            print("="*60)
        
        except Exception as e:
            logger.error(f"Fatal error: {e}")
        
        finally:
            # Cleanup
            self.mt5.disconnect()
            logger.info("MT5 disconnected")


def get_mt5_credentials():
    """Load MT5 credentials from environment variables."""
    login = os.getenv('MT5_LOGIN')
    password = os.getenv('MT5_PASSWORD')
    server = os.getenv('MT5_SERVER')
    
    if not all([login, password, server]):
        raise ValueError(
            "Missing MT5 credentials. Set environment variables:\n"
            "  export MT5_LOGIN=your_login\n"
            "  export MT5_PASSWORD=your_password\n"
            "  export MT5_SERVER=your_server"
        )
    
    return int(login), password, server


def main():
    """Main entry point."""
    try:
        # Get credentials
        login, password, server = get_mt5_credentials()
        
        # Create and run bot
        bot = LiveTradingBot(
            login=login,
            password=password,
            server=server,
            symbols=['EURUSD', 'GBPUSD', 'XAUUSD'],
            poll_interval=300  # 5 minutes
        )
        
        bot.run()
    
    except Exception as e:
        logger.error(f"Error: {e}")
        print(f"\n❌ Error: {e}")
        exit(1)


if __name__ == '__main__':
    main()

