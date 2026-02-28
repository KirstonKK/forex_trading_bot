"""
TradingView Webhook Server
Receives real-time market data from TradingView and runs your ICT/SMC strategy.
NO BROKER CONNECTION - Pure analysis and logging.

How it works:
1. TradingView monitors market 24/7 with real exchange data
2. Sends webhook with current price data every bar close
3. Bot runs your enhanced SMC strategy on the data
4. Logs trading signals (no actual trades executed)
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime, timezone
import logging
import json
import requests
from typing import Dict, List

# Import strategy only (no broker connectors)
from core.flexible_ict_strategy import FlexibleICTStrategy
from core.enhanced_risk_manager import EnhancedRiskManager
from integrations.news_filter import is_reduced_liquidity_day

# Import PulseGraph advisory integration
try:
    from integrations.pulsegraph import ForexSentimentAdvisor
    PULSEGRAPH_AVAILABLE = True
except ImportError:
    PULSEGRAPH_AVAILABLE = False
    ForexSentimentAdvisor = None

# Import Telegram integration
try:
    from integrations.telegram_bot import get_telegram_notifier, init_telegram
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    get_telegram_notifier = None

# Import Daily Report tracker
try:
    from integrations.daily_report import get_report_tracker
    REPORT_TRACKER_AVAILABLE = True
except ImportError:
    REPORT_TRACKER_AVAILABLE = False
    get_report_tracker = None

# Import Trade Performance Tracker
try:
    from integrations.trade_tracker import get_trade_tracker
    TRADE_TRACKER_AVAILABLE = True
except ImportError:
    TRADE_TRACKER_AVAILABLE = False
    get_trade_tracker = None

# Import News Filter for upcoming events
try:
    from integrations.news_filter import get_news_filter
    NEWS_FILTER_AVAILABLE = True
except ImportError:
    NEWS_FILTER_AVAILABLE = False
    get_news_filter = None

# Import Weekly Reporter
try:
    from integrations.weekly_report import get_weekly_reporter, should_send_weekly_report
    WEEKLY_REPORTER_AVAILABLE = True
except ImportError:
    WEEKLY_REPORTER_AVAILABLE = False
    get_weekly_reporter = None
    should_send_weekly_report = None

# Import A/B Testing Framework
try:
    from integrations.ab_testing import get_ab_framework
    AB_TESTING_AVAILABLE = True
except ImportError:
    AB_TESTING_AVAILABLE = False
    get_ab_framework = None

# Import ML Risk Model
try:
    from machine_learning.ml_risk_model import get_ml_risk_model, score_signal as ml_score_signal
    ML_RISK_AVAILABLE = True
except ImportError:
    ML_RISK_AVAILABLE = False
    get_ml_risk_model = None
    ml_score_signal = None

# Import Trades Database for persistent signal storage
try:
    from database.trades import TradesDatabase
    trades_db = TradesDatabase(db_path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'trading.db'))
    DB_AVAILABLE = True
except ImportError:
    trades_db = None
    DB_AVAILABLE = False

# Import Signal Journal for weekly performance tracking
try:
    from integrations.signal_journal import get_signal_journal
    signal_journal = get_signal_journal(db=trades_db) if DB_AVAILABLE else None
    JOURNAL_AVAILABLE = bool(signal_journal)
except ImportError:
    signal_journal = None
    JOURNAL_AVAILABLE = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/webhook.log'),
        logging.StreamHandler()
    ]
)

# Constants
MSG_FAILED_TO_SEND = 'Failed to send'
MSG_ML_NOT_AVAILABLE = 'ML Risk Model not available'
logger = logging.getLogger(__name__)

# Resolve absolute paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, 'static')

# Initialize Flask app
app = Flask(__name__, static_folder=STATIC_DIR)

# Configuration
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET')
if not WEBHOOK_SECRET or WEBHOOK_SECRET == 'your_secret_key_here':
    logger.warning("WARNING: Using default webhook secret. Set WEBHOOK_SECRET environment variable for production!")
    WEBHOOK_SECRET = 'your_secret_key_here'

ACCOUNT_BALANCE = 10000.0

# Telegram configuration
TELEGRAM_BOT_TOKEN = '8001169647:AAESVk1NjD2ppFUHVDoPq_OamyGHx3gBUU0'
TELEGRAM_CHAT_ID = '117216462'  # Personal chat
TELEGRAM_GROUP_ID = '-5005853931'  # Trading Admin group

# Initialize Telegram notifiers (personal + group)
telegram_notifier = None
telegram_group_notifier = None

if TELEGRAM_AVAILABLE:
    telegram_notifier = init_telegram(bot_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID)
    # Create second notifier for group
    from integrations.telegram_bot import TelegramNotifier
    telegram_group_notifier = TelegramNotifier(bot_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_GROUP_ID)
    logger.info("✅ Telegram notifications enabled (personal + group)")
else:
    telegram_notifier = None

# Data persistence paths
DATA_DIR = os.path.join(BASE_DIR, 'data')
MARKET_DATA_FILE = os.path.join(DATA_DIR, 'market_data.json')
SIGNALS_FILE = os.path.join(DATA_DIR, 'active_signals.json')

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

def save_market_data():
    """Save market data to file for persistence."""
    try:
        with open(MARKET_DATA_FILE, 'w') as f:
            json.dump(market_data, f)
        logger.debug("Market data saved to disk")
    except Exception as e:
        logger.error(f"Failed to save market data: {e}")

def load_market_data():
    """Load market data from file on startup."""
    global market_data
    try:
        if os.path.exists(MARKET_DATA_FILE):
            with open(MARKET_DATA_FILE, 'r') as f:
                market_data = json.load(f)
            # Count candles loaded
            for symbol, data in market_data.items():
                counts = {tf: len(data.get(tf, {}).get('close', [])) for tf in ['4H', '1H', '15M', '5M']}
                logger.info(f"Loaded {symbol} data: {counts}")
            logger.info("Market data restored from disk")
    except Exception as e:
        logger.warning(f"Could not load market data: {e}")
        market_data = {}

def save_signals():
    """Save active signals to file for persistence."""
    try:
        with open(SIGNALS_FILE, 'w') as f:
            json.dump(active_signals, f)
    except Exception as e:
        logger.error(f"Failed to save signals: {e}")

def load_signals():
    """Load active signals from file on startup."""
    global active_signals, signal_counter
    try:
        if os.path.exists(SIGNALS_FILE):
            with open(SIGNALS_FILE, 'r') as f:
                active_signals = json.load(f)
            # Update signal counter to avoid ID collisions
            # Signal IDs are like EUR_USD_1_1770900978 (symbol_counter_timestamp)
            if active_signals:
                counters = []
                for s in active_signals.values():
                    parts = s['id'].split('_')
                    # Counter is second-to-last part (before timestamp)
                    if len(parts) >= 4:
                        try:
                            counters.append(int(parts[-2]))
                        except (ValueError, IndexError):
                            pass
                if counters:
                    signal_counter = max(counters) + 1
            # Prune old signals (older than 7 days)
            prune_old_signals()
            logger.info(f"Loaded {len(active_signals)} signals from disk")
    except Exception as e:
        logger.warning(f"Could not load signals: {e}")
        active_signals = {}

def prune_old_signals():
    """
    Clean up old signals:
    - Pending signals older than 24 hours → mark 'expired' (setups go stale)
    - Anything older than 30 days → remove entirely to prevent unbounded growth
    """
    global active_signals
    now = datetime.now(timezone.utc)
    to_expire = []
    to_remove = []
    
    for sig_id, sig in active_signals.items():
        try:
            sig_time = sig.get('detected_at') or sig.get('timestamp')
            if isinstance(sig_time, str):
                sig_dt = datetime.fromisoformat(sig_time.replace('Z', '+00:00'))
            elif isinstance(sig_time, (int, float)):
                sig_dt = datetime.fromtimestamp(sig_time, tz=timezone.utc)
            else:
                continue
            # Make timezone-aware if not already
            if sig_dt.tzinfo is None:
                sig_dt = sig_dt.replace(tzinfo=timezone.utc)
            
            age_hours = (now - sig_dt).total_seconds() / 3600
            
            # Pending signals > 24h → expired (setup is stale, market has moved)
            if sig.get('status') == 'pending' and age_hours > 24:
                to_expire.append(sig_id)
            # Anything > 30 days → remove from disk entirely
            elif (now - sig_dt).days > 30:
                to_remove.append(sig_id)
        except Exception:
            pass
    
    for sig_id in to_expire:
        active_signals[sig_id]['status'] = 'expired'
        active_signals[sig_id]['expired_at'] = now.isoformat()
        # Also remove from trade tracker if present
        if TRADE_TRACKER_AVAILABLE and get_trade_tracker:
            tracker = get_trade_tracker()
            if sig_id in tracker.active_trades:
                del tracker.active_trades[sig_id]
                tracker._save_active_trades()
    
    for sig_id in to_remove:
        del active_signals[sig_id]
    
    if to_expire or to_remove:
        save_signals()
    if to_expire:
        logger.info(f"⏰ Expired {len(to_expire)} stale pending signals (>24h old)")
    if to_remove:
        logger.info(f"🗑️ Pruned {len(to_remove)} old signals (>30 days)")

# Store market data in memory
market_data = {}

# Store active signals (persist until executed or cancelled)
active_signals = {}  # {signal_id: signal_data}
signal_counter = 0

# Load persisted data on startup
load_market_data()
load_signals()

# Sync RECENT pending signals into TradeTracker for TP/SL monitoring.
# Only sync signals < 4 hours old. The verifier will fetch real price
# history from yfinance and immediately resolve any that already hit SL/TP.
# Signals older than 4h are too stale — expire them instead.
if TRADE_TRACKER_AVAILABLE and get_trade_tracker:
    tracker = get_trade_tracker()
    synced = 0
    verified_resolved = 0
    expired = 0
    skipped = 0
    now_ts = datetime.now(timezone.utc)
    for sig_id, sig in list(active_signals.items()):
        if sig.get('status') != 'pending':
            continue
        if not (sig.get('entry_price') and sig.get('stop_loss') and sig.get('take_profit')):
            continue
        # Check signal age
        detected = sig.get('detected_at', '')
        try:
            if isinstance(detected, str) and detected:
                sig_dt = datetime.fromisoformat(detected.replace('Z', '+00:00'))
                if sig_dt.tzinfo is None:
                    sig_dt = sig_dt.replace(tzinfo=timezone.utc)
                age_minutes = (now_ts - sig_dt).total_seconds() / 60
                if age_minutes > 240:  # > 4 hours
                    active_signals[sig_id]['status'] = 'expired'
                    expired += 1
                    continue
        except Exception:
            skipped += 1
            continue
        
        # add_trade now verifies against real price history
        trade_id, resolution = tracker.add_trade(sig, sig.get('symbol', ''), signal_id=sig_id)
        
        if resolution:
            # Trade was already resolved via yfinance verification
            outcome = resolution['status']
            active_signals[sig_id]['status'] = outcome
            active_signals[sig_id]['exit_price'] = resolution.get('exit_price')
            active_signals[sig_id]['exit_time'] = resolution.get('exit_time')
            active_signals[sig_id]['pips_result'] = resolution.get('pips_result')
            active_signals[sig_id]['rr_achieved'] = resolution.get('rr_achieved')
            if not resolution.get('entry_filled', True):
                active_signals[sig_id]['entry_filled'] = False
            verified_resolved += 1
        else:
            synced += 1
    
    if synced:
        logger.info(f"📊 Synced {synced} pending signals to TradeTracker (verified still active)")
    if verified_resolved:
        logger.info(f"🔍 Verified & resolved {verified_resolved} signals on startup (SL/TP already hit)")
    if expired:
        logger.info(f"⏰ Expired {expired} signals older than 4 hours")
    if skipped:
        logger.info(f"⏭️ Skipped {skipped} signals (bad timestamp)")
    if verified_resolved or expired:
        save_signals()

def add_signal_to_history(signal, symbol):
    """Add a signal that persists until executed or cancelled."""
    global signal_counter
    
    # Check for duplicate - same symbol, direction, setup_type, and similar entry price
    entry_price = signal.get('entry', signal.get('entry_price', 0))
    direction = signal.get('direction', signal.get('type', ''))
    setup_type = signal.get('setup_type', '')
    
    for existing in active_signals.values():
        if existing['status'] != 'pending':
            continue
        if existing['symbol'] != symbol:
            continue
        if existing.get('direction', existing.get('type', '')) != direction:
            continue
        if existing.get('setup_type', '') != setup_type:
            continue
        # Check if entry price is within 0.01% (essentially the same)
        existing_entry = existing.get('entry', existing.get('entry_price', 0))
        if existing_entry and abs(entry_price - existing_entry) / existing_entry < 0.0001:
            logger.info(f"⚠️ Duplicate signal ignored for {symbol} - already have pending {setup_type} {direction}")
            return None
    
    signal_counter += 1
    signal_id = f"{symbol}_{signal_counter}_{int(datetime.now().timestamp())}"
    
    signal_entry = {
        'id': signal_id,
        'timestamp': signal.get('timestamp', int(datetime.now().timestamp())),
        'detected_at': datetime.now().isoformat(),
        'symbol': symbol,
        'status': 'pending',  # pending, executed, cancelled, expired
        **signal
    }
    active_signals[signal_id] = signal_entry
    save_signals()  # Persist to disk
    logger.info(f"📌 Signal saved: {signal_id}")
    return signal_id

def mark_signal_executed(signal_id):
    """Mark a signal as executed in both active_signals and DB."""
    if signal_id in active_signals:
        sig = active_signals[signal_id]
        sig['status'] = 'executed'
        sig['executed_at'] = datetime.now(timezone.utc).isoformat()
        save_signals()
        
        # Also update in SQLite database
        if DB_AVAILABLE and trades_db:
            try:
                trades_db.update_signal_status(
                    symbol=sig.get('symbol', ''),
                    entry_price=sig.get('entry', sig.get('entry_price', 0)),
                    executed=True,
                    trade_id=signal_id
                )
            except Exception as e:
                logger.error(f"DB update failed for executed signal: {e}")
        
        logger.info(f"✅ Signal executed: {signal_id}")
        return True
    return False

def cancel_signal(signal_id):
    """Cancel a pending signal in both active_signals and DB."""
    if signal_id in active_signals:
        sig = active_signals[signal_id]
        sig['status'] = 'cancelled'
        sig['cancelled_at'] = datetime.now(timezone.utc).isoformat()
        save_signals()
        
        # Also update in SQLite database
        if DB_AVAILABLE and trades_db:
            try:
                trades_db.update_signal_status(
                    symbol=sig.get('symbol', ''),
                    entry_price=sig.get('entry', sig.get('entry_price', 0)),
                    executed=False
                )
            except Exception as e:
                logger.error(f"DB update failed for cancelled signal: {e}")
        
        logger.info(f"❌ Signal cancelled: {signal_id}")
        return True
    return False

def get_pending_signals():
    """Get all pending (not yet executed) signals."""
    return [s for s in active_signals.values() if s['status'] == 'pending']

def convert_to_candles_list(columnar_data):
    """Convert columnar market data to list of candle dicts for strategy."""
    if not columnar_data or not columnar_data.get('time'):
        return []
    
    candles = []
    for i in range(len(columnar_data['time'])):
        candle = {
            'timestamp': columnar_data['time'][i],  # Strategy expects 'timestamp'
            'time': columnar_data['time'][i],
            'open': columnar_data['open'][i],
            'high': columnar_data['high'][i],
            'low': columnar_data['low'][i],
            'close': columnar_data['close'][i],
            'volume': columnar_data['volume'][i]
        }
        candles.append(candle)
    return candles

# Initialize strategy
strategy = FlexibleICTStrategy()

# Initialize risk manager
risk_manager = EnhancedRiskManager(
    account_balance=ACCOUNT_BALANCE,
    risk_per_trade=1.0,
    max_daily_loss=4.0,
    max_trades_per_day=2
)

# Initialize PulseGraph advisor (advisory only - does not affect trades)
sentiment_advisor = None
if PULSEGRAPH_AVAILABLE:
    try:
        sentiment_advisor = ForexSentimentAdvisor()
        success, msg = sentiment_advisor.initialize()
        logger.info(f"PulseGraph Advisory: {msg}")
    except Exception as e:
        logger.warning(f"PulseGraph advisor not available: {e}")
        sentiment_advisor = None
else:
    logger.info("PulseGraph not installed - advisory sentiment disabled")


@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Receive market data from TradingView and analyze with your strategy.
    
    Expected JSON from TradingView:
    {
        "secret": "your_secret_key_here",
        "symbol": "EURUSD",
        "timeframe": "5M",
        "time": 1234567890,
        "open": 1.1234,
        "high": 1.1245,
        "low": 1.1220,
        "close": 1.1240,
        "volume": 1000
    }
    """
    try:
        # Get JSON data
        data = request.get_json()
        
        if not data:
            logger.error("No JSON data received")
            return jsonify({'error': 'No data provided'}), 400
        
        logger.info(f"Market data received: {data.get('symbol')} @ {data.get('close')}")
        
        # Verify secret
        if data.get('secret') != WEBHOOK_SECRET:
            logger.error("Invalid webhook secret")
            return jsonify({'error': 'Invalid secret'}), 401
        
        # Extract candle data
        symbol = data.get('symbol', '').replace('/', '_')  # Convert EURUSD to EUR_USD
        if len(symbol) == 6:
            symbol = f"{symbol[:3]}_{symbol[3:]}"
        
        timeframe = data.get('timeframe', '5M')
        
        # Store candle data - 4H, 1H, 15M, 5M
        if symbol not in market_data:
            market_data[symbol] = {
                '4H': {'time': [], 'open': [], 'high': [], 'low': [], 'close': [], 'volume': []},
                '1H': {'time': [], 'open': [], 'high': [], 'low': [], 'close': [], 'volume': []},
                '15M': {'time': [], 'open': [], 'high': [], 'low': [], 'close': [], 'volume': []},
                '5M': {'time': [], 'open': [], 'high': [], 'low': [], 'close': [], 'volume': []}
            }
        
        # Add new candle
        if timeframe in market_data[symbol]:
            candles = market_data[symbol][timeframe]
            candles['time'].append(int(data.get('time', datetime.now().timestamp())))
            candles['open'].append(float(data.get('open', 0)))
            candles['high'].append(float(data.get('high', 0)))
            candles['low'].append(float(data.get('low', 0)))
            candles['close'].append(float(data.get('close', 0)))
            candles['volume'].append(int(data.get('volume', 0)))
            
            # Track candles analyzed (only for 5M which is our entry timeframe)
            if timeframe == '5M' and REPORT_TRACKER_AVAILABLE and get_report_tracker:
                try:
                    tracker = get_report_tracker()
                    tracker.record_stats('candles_analyzed')
                except Exception:
                    pass
            
            # Keep last 100 candles only
            for key in candles:
                if len(candles[key]) > 100:
                    candles[key] = candles[key][-100:]
        
        # Save market data periodically (every 10th candle to reduce disk I/O)
        total_candles = sum(len(market_data[symbol].get(tf, {}).get('close', [])) for tf in ['5M'])
        if total_candles % 10 == 0:
            save_market_data()
        
        # ── AUTO-RESOLVE: Check if any pending signals hit TP or SL ──
        # The tracker now does TWO-LAYER verification:
        # 1. Quick check with incoming candle high/low
        # 2. Full yfinance history walk when quick check finds a hit OR every ~30 min
        # No trade is EVER resolved without yfinance verification.
        candle_high = float(data.get('high', 0))
        candle_low = float(data.get('low', 0))
        candle_close = float(data.get('close', 0))
        if candle_close > 0 and TRADE_TRACKER_AVAILABLE and get_trade_tracker:
            try:
                tracker = get_trade_tracker()
                resolved = tracker.update_trades(symbol, candle_close, candle_high=candle_high, candle_low=candle_low)
                
                for trade in resolved:
                    # Sync back to active_signals dict
                    sig_id = trade.get('signal_id', '')
                    outcome = trade['status']  # 'win', 'loss', or 'expired'
                    
                    if sig_id in active_signals:
                        active_signals[sig_id]['status'] = outcome
                        active_signals[sig_id]['exit_price'] = trade.get('exit_price')
                        active_signals[sig_id]['exit_time'] = trade.get('exit_time')
                        active_signals[sig_id]['pips_result'] = trade.get('pips_result')
                        active_signals[sig_id]['rr_achieved'] = trade.get('rr_achieved')
                        if not trade.get('entry_filled', True):
                            active_signals[sig_id]['entry_filled'] = False
                        save_signals()
                    
                    # Handle expired (entry never filled)
                    if outcome == 'expired':
                        logger.info(f"⏰ {sig_id}: Entry never reached — sell/buy limit expired")
                        tg_text = (
                            f"⏰ <b>SIGNAL EXPIRED: {symbol}</b>\n"
                            f"Entry {trade.get('entry_price', 0):.5f} never reached\n"
                            f"Limit order was never filled — cancelling."
                        )
                        if telegram_bot:
                            try:
                                telegram_bot.send_message(tg_text)
                            except Exception:
                                pass
                        continue
                    
                    # Log + Telegram notification
                    pips = trade.get('pips_result', 0)
                    rr = trade.get('rr_achieved', 0)
                    direction = trade.get('direction', '?')
                    setup = trade.get('setup_type', '?')
                    entry = trade.get('entry_price', 0)
                    exit_p = trade.get('exit_price', 0)
                    verified = trade.get('verified', False)
                    hit_time = trade.get('hit_candle_time', '')
                    candles_checked = trade.get('candles_checked', 0)
                    
                    if outcome == 'win':
                        emoji = "✅"
                        msg = f"🎯 TP HIT — +{pips:.1f} pips (RR {rr:.1f})"
                    else:
                        emoji = "❌"
                        msg = f"🛑 SL HIT — {pips:.1f} pips"
                        # Record losing zone so strategy won't re-enter same price area
                        try:
                            strategy.record_loss(symbol, entry, direction,
                                                 int(datetime.now(timezone.utc).timestamp()))
                            logger.info(f"📝 Recorded losing zone: {symbol} {direction} @ {entry:.5f}")
                        except Exception as e:
                            logger.warning(f"Could not record losing zone: {e}")
                    
                    # ===== ML FEEDBACK LOOP (2026-02-28) =====
                    # Log resolved trade outcome to ML model for training data collection
                    if ML_RISK_AVAILABLE and get_ml_risk_model:
                        try:
                            ml_model = get_ml_risk_model()
                            # Reconstruct signal data from trade record
                            signal_data = {
                                'setup_type': setup,
                                'direction': direction,
                                'confirmations': trade.get('confirmations', []),
                                'confidence': trade.get('confidence', 0.7),
                            }
                            # Build market context
                            trade_hour = 12  # Default
                            try:
                                exit_time = trade.get('exit_time', '')
                                if exit_time:
                                    trade_hour = datetime.fromisoformat(exit_time.replace('Z', '+00:00')).hour
                            except Exception:
                                pass
                            market_context = {
                                'session': 'LONDON' if 8 <= trade_hour < 12 else ('NY' if 12 <= trade_hour < 17 else 'OFF'),
                                'hour': trade_hour,
                                'symbol': symbol,
                            }
                            ml_model.log_trade_outcome(signal_data, market_context, outcome, pips)
                            logger.info(f"🤖 ML logged: {outcome} ({pips:+.1f} pips) for {setup}")
                        except Exception as e:
                            logger.warning(f"ML feedback error: {e}")
                    
                    # ===== A/B TESTING FEEDBACK (2026-02-28) =====
                    # Record outcome for all A/B variants that would have taken this signal
                    if AB_TESTING_AVAILABLE and get_ab_framework:
                        try:
                            ab_framework = get_ab_framework()
                            # Get stored variant results for this signal
                            sig = active_signals.get(sig_id, {})
                            variant_results = sig.get('ab_variant_results', {})
                            if variant_results:
                                ab_framework.record_signal_result(variant_results, outcome, pips)
                                logger.info(f"🔬 A/B recorded: {outcome} for {len([v for v in variant_results.values() if v])} variants")
                        except Exception as e:
                            logger.warning(f"A/B testing feedback error: {e}")
                    
                    verify_tag = "🔍 VERIFIED" if verified else "⚠️ UNVERIFIED"
                    
                    tg_text = (
                        f"{emoji} <b>TRADE {outcome.upper()}: {symbol}</b>\n"
                        f"Setup: {setup} | {direction.upper()}\n"
                        f"Entry: {entry:.5f} → Exit: {exit_p:.5f}\n"
                        f"{msg}\n"
                        f"{verify_tag} against {candles_checked} candles"
                    )
                    if hit_time:
                        tg_text += f"\nHit candle: {hit_time}"
                    
                    logger.info(f"{emoji} RESOLVED ({verify_tag}): {sig_id} | {msg}")
                    
                    if telegram_notifier:
                        try:
                            telegram_notifier.send_message(tg_text)
                        except Exception as e:
                            logger.error(f"Telegram notify error: {e}")
                    if telegram_group_notifier:
                        try:
                            telegram_group_notifier.send_message(tg_text)
                        except Exception as e:
                            logger.error(f"Telegram group notify error: {e}")
            except Exception as e:
                logger.error(f"Auto-resolve error: {e}")
        
        # Check if we have enough data to analyze (need all 4 timeframes)
        if (len(market_data[symbol].get('4H', {}).get('close', [])) >= 50 and
            len(market_data[symbol].get('1H', {}).get('close', [])) >= 50 and
            len(market_data[symbol].get('15M', {}).get('close', [])) >= 50 and
            len(market_data[symbol].get('5M', {}).get('close', [])) >= 50):
            
            # ── Bank holiday gate: skip signal generation on low-liquidity days ──
            is_holiday, holiday_name = is_reduced_liquidity_day()
            if is_holiday:
                logger.info(f"🏦 {holiday_name} — skipping analysis for {symbol}")
                return jsonify({
                    'status': 'holiday_skip',
                    'message': holiday_name,
                    'symbol': symbol
                }), 200
            
            # Run strategy analysis
            current_price = data.get('close', 0)
            
            # Convert ALL timeframes to candle lists for MTF analysis
            mtf_data = {
                '4H': convert_to_candles_list(market_data[symbol]['4H']),
                '1H': convert_to_candles_list(market_data[symbol]['1H']),
                '15M': convert_to_candles_list(market_data[symbol]['15M']),
                '5M': convert_to_candles_list(market_data[symbol]['5M'])
            }
            
            # Build all_market_data for SMT divergence (Option 5 needs correlated pair data)
            all_market = {}
            for sym_key, sym_data in market_data.items():
                if all(tf in sym_data and len(sym_data[tf].get('close', [])) >= 20 for tf in ['5M', '1H']):
                    all_market[sym_key] = {
                        '5M': convert_to_candles_list(sym_data['5M']),
                        '1H': convert_to_candles_list(sym_data['1H']),
                    }
            strategy.set_all_market_data(all_market)
            
            # Use new flexible strategy with 3 setup options and MTF data
            signal = strategy.analyze(mtf_data['5M'], symbol=symbol, mtf_data=mtf_data)
            
            if signal:
                setup_name = signal.get('setup_type', 'UNKNOWN')
                confirmations = signal.get('confirmations', [])
                risk_pct = signal.get('risk_percentage', 0) * 100
                
                # === ML RISK SCORING ===
                ml_score = None
                if ML_RISK_AVAILABLE and ml_score_signal:
                    try:
                        # Build market context for ML
                        current_hour = datetime.now(timezone.utc).hour
                        if 10 <= current_hour < 14:
                            session = 'LONDON'
                        elif 14 <= current_hour < 17:
                            session = 'NY'
                        else:
                            session = 'OFF'
                        
                        market_context = {
                            'session': session,
                            'atr': 1.0,  # Would calculate from candles
                            'avg_atr': 1.0,
                            'trend_strength': 0.5,  # Would calculate from HTF
                            'historical': {
                                'pair_win_rate': 0.6,
                                'hour_win_rate': 0.6,
                                'setup_win_rate': 0.6,
                                'streak': 0
                            }
                        }
                        ml_score = ml_score_signal(signal, market_context)
                        
                        # Add ML info to signal
                        signal['ml_confidence'] = ml_score.get('confidence', 70)
                        signal['ml_risk_multiplier'] = ml_score.get('risk_multiplier', 1.0)
                        signal['ml_recommendation'] = ml_score.get('recommendation', 'full_risk')
                        signal['ml_reasoning'] = ml_score.get('reasoning', [])
                        
                        # Adjust risk based on ML score
                        adjusted_risk = risk_pct * ml_score.get('risk_multiplier', 1.0)
                        signal['adjusted_risk_pct'] = adjusted_risk
                        
                        logger.info(f"   🤖 ML Score: {ml_score.get('confidence', 0)}% → {ml_score.get('recommendation', 'N/A')}")
                        
                    except Exception as e:
                        logger.error(f"ML scoring error: {e}")
                
                logger.info(f"\n🎯 SIGNAL DETECTED FOR {symbol}!")
                logger.info(f"   Setup: {setup_name}")
                logger.info(f"   Confirmations: {', '.join(confirmations)} ({len(confirmations)}/3)")
                logger.info(f"   Type: {signal.get('direction', 'UNKNOWN')}")
                logger.info(f"   Entry: {signal.get('entry_price', 0):.5f}")
                logger.info(f"   Stop Loss: {signal.get('stop_loss', 0):.5f}")
                logger.info(f"   Take Profit: {signal.get('take_profit', 0):.5f}")
                logger.info(f"   Risk/Reward: 1:{signal.get('risk_reward', 0):.2f}")
                logger.info(f"   Risk Size: {risk_pct:.1f}% (Full={len(confirmations)>=3})")
                logger.info(f"   Confidence: {signal.get('confidence', 0):.2f}")
                
                # Add futures note for gold
                if 'XAU' in symbol:
                    signal['price_note'] = "Futures price - spot typically ~$30-40 lower"
                    logger.info("   ⚠️ Note: Futures price - spot typically ~$30-40 lower")
                
                # Normalize signal structure for frontend
                signal['type'] = signal['direction']
                signal['entry'] = signal['entry_price']
                
                # ===== A/B TESTING EVALUATION (2026-02-28) =====
                # Evaluate which variants would have taken this signal
                # Store results with the signal for later outcome recording
                ab_variant_results = {}
                if AB_TESTING_AVAILABLE and get_ab_framework:
                    try:
                        ab_framework = get_ab_framework()
                        # Determine if signal has ChoCH and 15M confirmation
                        has_choch = signal.get('has_choch', False) or 'CHOCH' in confirmations
                        has_15m_confirm = True  # If we got here, 15M confirmed (it's a filter)
                        confidence = signal.get('confidence', 0.7)
                        
                        ab_variant_results = ab_framework.evaluate_setup(
                            choch_found=has_choch,
                            confirmation_15m=has_15m_confirm,
                            confidence=confidence
                        )
                        signal['ab_variant_results'] = ab_variant_results
                        logger.info(f"🔬 A/B: {sum(ab_variant_results.values())}/{len(ab_variant_results)} variants matched")
                    except Exception as e:
                        logger.warning(f"A/B evaluation error: {e}")
                
                # Store signal in history for dashboard
                new_signal_id = add_signal_to_history(signal, symbol)
                
                # ── Register with TradeTracker for automatic TP/SL monitoring ──
                # Brand-new signals: skip_verification=True (signal is < 1 candle old,
                # no history to verify yet — verification kicks in on subsequent updates)
                if new_signal_id and TRADE_TRACKER_AVAILABLE and get_trade_tracker:
                    try:
                        tracker = get_trade_tracker()
                        _tid, _res = tracker.add_trade(signal, symbol, signal_id=new_signal_id,
                                                       skip_verification=True)
                    except Exception as e:
                        logger.error(f"TradeTracker registration error: {e}")
                
                # Record signal for daily report
                if REPORT_TRACKER_AVAILABLE and get_report_tracker:
                    try:
                        tracker = get_report_tracker()
                        tracker.record_signal(signal, symbol)
                    except Exception as e:
                        logger.error(f"Report tracker error: {e}")
                
                # Send Telegram notification (personal + group)
                if telegram_notifier:
                    try:
                        telegram_notifier.notify_signal(signal, symbol)
                    except Exception as e:
                        logger.error(f"Telegram personal notification failed: {e}")
                
                if telegram_group_notifier:
                    try:
                        telegram_group_notifier.notify_signal(signal, symbol)
                    except Exception as e:
                        logger.error(f"Telegram group notification failed: {e}")
                
                # Save signal to SQLite database
                if DB_AVAILABLE and trades_db:
                    try:
                        signal_for_db = {
                            'symbol': symbol,
                            'direction': signal.get('direction', 'UNKNOWN'),
                            'entry_price': signal.get('entry_price', 0),
                            'stop_loss': signal.get('stop_loss', 0),
                            'take_profit': signal.get('take_profit', 0),
                            'confidence': signal.get('confidence', 0),
                            'setup_type': signal.get('setup_type', ''),
                            'risk_reward': signal.get('risk_reward', 0),
                            'confirmations': signal.get('confirmations', []),
                            'executed': False,
                            'trade_id': None
                        }
                        trades_db.save_signal(signal_for_db)
                        logger.info(f"💾 Signal saved to database for {symbol}")
                    except Exception as e:
                        logger.error(f"DB save failed: {e}")
                
                return jsonify({
                    'status': 'signal_detected',
                    'signal': signal,
                    'message': f'{signal["direction"]} signal for {symbol}'
                }), 200
            else:
                # Record rejection reasons for daily report
                if REPORT_TRACKER_AVAILABLE and get_report_tracker:
                    try:
                        tracker = get_report_tracker()
                        # Get rejection reasons from strategy
                        reasons = strategy.get_last_rejection_reasons() if hasattr(strategy, 'get_last_rejection_reasons') else ['No valid ICT setup']
                        tracker.record_rejection(symbol, reasons)
                        tracker.record_stats('setups_checked')
                        
                        # Track valid sweeps and BoS detected
                        if hasattr(strategy, 'get_last_analysis_stats'):
                            stats = strategy.get_last_analysis_stats()
                            if stats.get('sweep_found'):
                                tracker.record_stats('valid_sweeps')
                            if stats.get('bos_found'):
                                tracker.record_stats('valid_bos')
                    except Exception as e:
                        logger.debug(f"Report tracker error: {e}")
                
                return jsonify({
                    'status': 'no_signal',
                    'message': f'No setup for {symbol} at {current_price:.5f}'
                }), 200
        else:
            return jsonify({
                'status': 'collecting_data',
                'message': f'Need more data for {symbol}',
                'candles': {
                    '4H': len(market_data[symbol].get('4H', {}).get('close', [])),
                    '1H': len(market_data[symbol].get('1H', {}).get('close', [])),
                    '5M': len(market_data[symbol].get('5M', {}).get('close', []))
                }
            }), 200
            
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/')
def dashboard():
    """Serve the trading dashboard."""
    return send_from_directory(STATIC_DIR, 'dashboard.html')


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    is_holiday, holiday_name = is_reduced_liquidity_day()
    return jsonify({
        'status': 'running',
        'mode': 'analysis_only',
        'bank_holiday': holiday_name if is_holiday else None,
        'trading_active': not is_holiday,
        'symbols_tracked': list(market_data.keys()),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/data', methods=['GET'])
def get_data():
    """Get stored market data."""
    symbol = request.args.get('symbol', None)
    if symbol:
        return jsonify({
            'status': 'success',
            'symbol': symbol,
            'data': market_data.get(symbol, {})
        })
    else:
        return jsonify({
            'status': 'success',
            'symbols': list(market_data.keys()),
            'data': market_data
        })


# Minimum candle requirements per timeframe (realistic for live trading)
MIN_CANDLES = {
    '4H': 10,   # 40 hours of data
    '1H': 20,   # 20 hours of data  
    '15M': 30,  # 7.5 hours of data
    '5M': 50    # ~4 hours of data
}

@app.route('/signals', methods=['GET'])
def get_signals():
    """Get latest signal status for all tracked symbols.
    
    READ-ONLY: Does NOT call strategy.analyze() to avoid side effects.
    Analysis only runs from webhook POST when new candle data arrives.
    """
    signals = {}
    
    # Get pending signals from active_signals (already analyzed)
    pending = get_pending_signals()
    for sig in pending:
        sym = sig.get('symbol', '')
        signals[sym] = {
            'status': 'pending',
            'signal_id': sig.get('id'),
            'direction': sig.get('direction', sig.get('type', 'UNKNOWN')),
            'type': sig.get('direction', sig.get('type', 'UNKNOWN')),
            'entry': sig.get('entry', sig.get('entry_price', 0)),
            'entry_price': sig.get('entry', sig.get('entry_price', 0)),
            'stop_loss': sig.get('stop_loss', 0),
            'take_profit': sig.get('take_profit', 0),
            'setup_type': sig.get('setup_type', ''),
            'confidence': sig.get('confidence', 0),
            'risk_reward': sig.get('risk_reward', 0),
            'confirmations': sig.get('confirmations', []),
            'detected_at': sig.get('detected_at', ''),
        }
    
    # For symbols with no pending signal, show "no_setup" status
    for symbol in market_data:
        if symbol not in signals:
            has_data = all(
                len(market_data[symbol].get(tf, {}).get('close', [])) >= MIN_CANDLES.get(tf, 50)
                for tf in ['4H', '1H', '15M', '5M']
            )
            signals[symbol] = {'status': 'no_setup' if has_data else 'insufficient_data'}
    
    return jsonify({
        'status': 'success',
        'signals': signals
    })


@app.route('/signals/history', methods=['GET'])
def get_signal_history():
    """Get all signals (pending and executed) for dashboard."""
    pending = get_pending_signals()
    all_signals = list(active_signals.values())
    
    # Count signals detected TODAY (any status: pending, win, loss, cancelled)
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_count = 0
    for sig in all_signals:
        detected = sig.get('detected_at', '')
        if detected and detected[:10] == today_str:
            today_count += 1
    
    return jsonify({
        'status': 'success',
        'pending_count': len(pending),
        'today_count': today_count,
        'total_count': len(all_signals),
        'pending': pending,
        'all': all_signals
    })


@app.route('/signals/execute/<signal_id>', methods=['POST'])
def execute_signal(signal_id):
    """Mark a signal as executed (trade taken)."""
    if mark_signal_executed(signal_id):
        return jsonify({'status': 'success', 'message': f'Signal {signal_id} marked as executed'})
    return jsonify({'status': 'error', 'message': 'Signal not found'}), 404


@app.route('/signals/cancel/<signal_id>', methods=['POST'])
def cancel_signal_endpoint(signal_id):
    """Cancel a pending signal."""
    if cancel_signal(signal_id):
        return jsonify({'status': 'success', 'message': f'Signal {signal_id} cancelled'})
    return jsonify({'status': 'error', 'message': 'Signal not found'}), 404


@app.route('/signals/stats', methods=['GET'])
def get_signal_stats_endpoint():
    """Get signal statistics from database."""
    if DB_AVAILABLE and trades_db:
        stats = trades_db.get_signal_stats()
        return jsonify({'status': 'success', 'stats': stats})
    return jsonify({'status': 'error', 'message': 'Database not available'}), 500


# ===== TRADING JOURNAL ENDPOINTS =====

@app.route('/journal/check', methods=['POST'])
def journal_check_outcomes():
    """Check all pending signals for TP/SL outcomes. Call this before generating the weekly report."""
    if not JOURNAL_AVAILABLE:
        return jsonify({'status': 'error', 'message': 'Signal journal not available'}), 500
    
    try:
        results = signal_journal.resolve_all_pending()
        return jsonify({'status': 'success', 'results': results})
    except Exception as e:
        logger.error(f"Journal check error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/journal/weekly', methods=['GET', 'POST'])
def journal_weekly_report():
    """
    GET: View weekly report as JSON
    POST: Resolve outcomes + generate report + send to Telegram
    """
    if not JOURNAL_AVAILABLE:
        return jsonify({'status': 'error', 'message': 'Signal journal not available'}), 500
    
    week_offset = int(request.args.get('week', 0))  # 0=current, -1=last week
    
    try:
        if request.method == 'POST':
            # First resolve all pending outcomes
            resolve_results = signal_journal.resolve_all_pending()
            logger.info(f"📓 Resolved outcomes: {resolve_results}")
        
        # Generate report
        report = signal_journal.generate_weekly_report(week_offset=week_offset)
        
        if request.method == 'POST' and report.get('total_signals', 0) > 0:
            # Format and send to Telegram
            telegram_text = signal_journal.format_telegram_report(report)
            
            sent = False
            if telegram_notifier:
                sent = telegram_notifier.send_message(telegram_text, parse_mode='HTML')
            if telegram_group_notifier:
                telegram_group_notifier.send_message(telegram_text, parse_mode='HTML')
            
            report['telegram_sent'] = sent
            report['resolve_results'] = resolve_results
        
        # Remove full signal list from JSON response (too verbose)
        report_summary = {k: v for k, v in report.items() if k != 'signals'}
        return jsonify({'status': 'success', 'report': report_summary})
    
    except Exception as e:
        logger.error(f"Weekly report error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/report/daily', methods=['GET', 'POST'])
def get_daily_report():
    """Get or send daily trading report."""
    if not REPORT_TRACKER_AVAILABLE or not get_report_tracker:
        return jsonify({'status': 'error', 'message': 'Report tracker not available'}), 500
    
    tracker = get_report_tracker()
    report_data = tracker.get_report_data()
    
    # If POST, send to Telegram (personal + group)
    if request.method == 'POST':
        success = False
        if telegram_notifier:
            success = telegram_notifier.send_daily_report(report_data)
        if telegram_group_notifier:
            telegram_group_notifier.send_daily_report(report_data)
        return jsonify({
            'status': 'success' if success else 'error',
            'message': 'Report sent to Telegram' if success else MSG_FAILED_TO_SEND,
            'report': report_data
        })
    
    # GET just returns the data
    return jsonify({
        'status': 'success',
        'report': report_data
    })


@app.route('/performance', methods=['GET'])
def get_performance():
    """Get trade performance statistics for dashboard."""
    result = {
        'status': 'success',
        'overall': {},
        'by_pair': {},
        'by_session': {},
        'recent_trades': [],
        'equity_curve': [],
        'news_events': []
    }
    
    # Trade tracker stats
    if TRADE_TRACKER_AVAILABLE and get_trade_tracker:
        try:
            tracker = get_trade_tracker()
            stats = tracker.get_performance_stats()
            # get_performance_stats() returns flat dict with total_trades, wins, etc.
            result['overall'] = {
                'total_trades': stats.get('total_trades', 0),
                'wins': stats.get('wins', 0),
                'losses': stats.get('losses', 0),
                'win_rate': stats.get('win_rate', 0.0),
                'total_pips': stats.get('total_pips', 0.0),
                'avg_win': stats.get('avg_win', 0.0),
                'avg_loss': stats.get('avg_loss', 0.0),
                'profit_factor': stats.get('profit_factor', 0.0),
                'active_trades': tracker.get_active_count(),
            }
            result['by_pair'] = stats.get('by_pair', {})
            result['by_setup'] = stats.get('by_setup', {})
            result['recent_trades'] = tracker.history[-10:][::-1]  # Last 10, newest first
        except Exception as e:
            logger.error(f"Trade tracker error: {e}")
            result['overall'] = {'error': str(e)}
    else:
        result['overall'] = {
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0.0,
            'total_pips': 0.0,
            'message': 'Trade tracker not configured'
        }
    
    # News events
    if NEWS_FILTER_AVAILABLE and get_news_filter:
        try:
            nf = get_news_filter()
            result['news_events'] = nf.get_upcoming_events(24)
            is_blackout, reason = nf.is_news_blackout()
            result['news_blackout'] = is_blackout
            result['news_blackout_reason'] = reason
        except Exception as e:
            logger.error(f"News filter error: {e}")
            result['news_events'] = []
    
    return jsonify(result)


@app.route('/report/weekly', methods=['GET', 'POST'])
def get_weekly_report():
    """Get or send weekly performance report."""
    if not WEEKLY_REPORTER_AVAILABLE or not get_weekly_reporter:
        return jsonify({'status': 'error', 'message': 'Weekly reporter not available'}), 500
    
    reporter = get_weekly_reporter()
    
    # If POST, send to Telegram
    if request.method == 'POST':
        report_text = reporter.format_telegram_report()
        success = False
        
        if telegram_notifier:
            success = telegram_notifier.send_message(report_text)
        if telegram_group_notifier:
            telegram_group_notifier.send_message(report_text)
        
        # Archive the report
        reporter.save_weekly_archive()
        
        return jsonify({
            'status': 'success' if success else 'error',
            'message': 'Weekly report sent to Telegram' if success else MSG_FAILED_TO_SEND,
            'report': reporter.get_weekly_stats()
        })
    
    # GET returns the data
    return jsonify({
        'status': 'success',
        'report': reporter.get_weekly_stats(),
        'formatted': reporter.format_telegram_report()
    })


@app.route('/abtest', methods=['GET', 'POST'])
def get_ab_test():
    """Get A/B test comparison or send report."""
    if not AB_TESTING_AVAILABLE or not get_ab_framework:
        return jsonify({'status': 'error', 'message': 'A/B Testing not available'}), 500
    
    framework = get_ab_framework()
    
    # If POST with action=reset, reset tests
    if request.method == 'POST':
        action = request.json.get('action', '') if request.is_json else request.args.get('action', '')
        
        if action == 'reset':
            framework.reset_tests()
            return jsonify({'status': 'success', 'message': 'A/B tests reset'})
        
        # Otherwise send report to Telegram
        report_text = framework.format_telegram_report()
        success = False
        
        if telegram_notifier:
            success = telegram_notifier.send_message(report_text)
        
        return jsonify({
            'status': 'success' if success else 'error',
            'message': 'A/B report sent to Telegram' if success else MSG_FAILED_TO_SEND
        })
    
    # GET returns comparison
    return jsonify({
        'status': 'success',
        'comparison': framework.get_comparison_report(),
        'formatted': framework.format_telegram_report()
    })


@app.route('/ml/stats', methods=['GET'])
def get_ml_stats():
    """Get ML risk model statistics."""
    if not ML_RISK_AVAILABLE or not get_ml_risk_model:
        return jsonify({'status': 'error', 'message': MSG_ML_NOT_AVAILABLE}), 500
    
    model = get_ml_risk_model()
    stats = model.get_model_stats()
    
    return jsonify({
        'status': 'success',
        'stats': stats
    })


@app.route('/ml/train', methods=['POST'])
def train_ml_model():
    """Manually trigger ML model training."""
    if not ML_RISK_AVAILABLE or not get_ml_risk_model:
        return jsonify({'status': 'error', 'message': MSG_ML_NOT_AVAILABLE}), 500
    
    model = get_ml_risk_model()
    result = model.train()
    
    # Notify via Telegram
    if telegram_notifier and result.get('status') == 'trained':
        telegram_notifier.send_message(
            f"🤖 *ML Model Trained*\n\n"
            f"Samples: {result.get('samples', 0)}\n"
            f"Accuracy: {result.get('accuracy', 0)*100:.1f}%\n"
            f"Win Rate: {result.get('win_rate', 0)*100:.1f}%"
        )
    
    return jsonify({
        'status': 'success',
        'result': result
    })


@app.route('/ml/log', methods=['POST'])
def log_ml_trade():
    """Log a trade outcome for ML training."""
    if not ML_RISK_AVAILABLE or not get_ml_risk_model:
        return jsonify({'status': 'error', 'message': MSG_ML_NOT_AVAILABLE}), 500
    
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'No data provided'}), 400
    
    signal_data = data.get('signal', {})
    market_context = data.get('market_context', {})
    outcome = data.get('outcome', 'loss')  # 'win' or 'loss'
    pips = data.get('pips', 0)
    
    model = get_ml_risk_model()
    model.log_trade(signal_data, market_context, outcome, pips)
    
    return jsonify({
        'status': 'success',
        'message': f'Trade logged: {outcome} ({pips:+.1f} pips)',
        'total_samples': len(model.training_data)
    })


@app.route('/debug', methods=['GET'])
def debug_analysis():
    """Debug endpoint to see why each option is failing."""
    debug_info = {}
    for symbol, data in market_data.items():
        try:
            data_4h = data.get('4H', {})
            data_1h = data.get('1H', {})
            data_15m = data.get('15M', {})
            data_5m = data.get('5M', {})
            
            candle_counts = {
                '4H': len(data_4h.get('close', [])),
                '1H': len(data_1h.get('close', [])),
                '15M': len(data_15m.get('close', [])),
                '5M': len(data_5m.get('close', []))
            }
            
            # Check each timeframe against its minimum requirement
            has_enough_data = all(
                candle_counts[tf] >= MIN_CANDLES[tf] for tf in MIN_CANDLES
            )
            
            if has_enough_data:
                mtf_data = {
                    '4H': convert_to_candles_list(data_4h),
                    '1H': convert_to_candles_list(data_1h),
                    '15M': convert_to_candles_list(data_15m),
                    '5M': convert_to_candles_list(data_5m)
                }
                
                strategy.set_mtf_data(mtf_data)
                base_candles = mtf_data['5M']
                
                # Check each component
                htf_trend_4h = strategy.determine_htf_trend(base_candles, 240)
                htf_trend_1h = strategy.determine_htf_trend(base_candles, 60)
                has_sweep, sweep_type = strategy.check_liquidity_sweep(base_candles, symbol)
                has_bos_long = strategy.check_bos(base_candles, 'long')
                has_bos_short = strategy.check_bos(base_candles, 'short')
                has_choch_long = strategy.check_choch(base_candles, 'long')
                has_choch_short = strategy.check_choch(base_candles, 'short')
                htf_zones_4h = strategy.find_htf_zones(base_candles, 240)
                htf_zones_1h = strategy.find_htf_zones(base_candles, 60)
                order_blocks = strategy.find_order_blocks(base_candles, 5)
                fvgs = strategy.find_fvgs(base_candles)
                
                debug_info[symbol] = {
                    'candle_counts': candle_counts,
                    'htf_trend_4h': htf_trend_4h.value,
                    'htf_trend_1h': htf_trend_1h.value,
                    'has_liquidity_sweep': has_sweep,
                    'sweep_type': sweep_type,
                    'has_bos_long': has_bos_long,
                    'has_bos_short': has_bos_short,
                    'has_choch_long': has_choch_long,
                    'has_choch_short': has_choch_short,
                    'htf_zones_4h_count': len(htf_zones_4h),
                    'htf_zones_1h_count': len(htf_zones_1h),
                    'order_blocks_count': len(order_blocks),
                    'fvgs_count': len(fvgs),
                    'can_trade': strategy.can_take_trade(base_candles[-1]['timestamp']),
                    'current_session': strategy.filters.get_current_session(base_candles[-1]['timestamp'])
                }
            else:
                debug_info[symbol] = {'status': 'insufficient_data', 'candle_counts': candle_counts}
        except Exception as e:
            debug_info[symbol] = {'error': str(e)}
    
    return jsonify(debug_info)


# ============================================================
# PulseGraph Advisory Endpoints (ADVISORY ONLY - no trade impact)
# ============================================================

@app.route('/advisory/sentiment', methods=['GET'])
def get_advisory_sentiment():
    """
    Get market sentiment advisory for forex pairs.
    ADVISORY ONLY - Does NOT affect trade decisions.
    """
    if not sentiment_advisor:
        return jsonify({
            'status': 'unavailable',
            'message': 'Sentiment advisor not configured (Neo4j/OpenAI not available)',
            'pairs': {}
        }), 200
    
    try:
        pair = request.args.get('pair', None)
        
        if pair:
            # Get advisory for specific pair
            signal = sentiment_advisor.get_advisory(pair)
            return jsonify({
                'status': 'success',
                'advisory_note': 'This is ADVISORY ONLY - does not affect trade decisions',
                'pair': signal.to_dict()
            })
        else:
            # Get full market context
            context = sentiment_advisor.get_market_context()
            return jsonify({
                'status': 'success',
                'advisory_note': 'This is ADVISORY ONLY - does not affect trade decisions',
                'context': context.to_dict()
            })
    except Exception as e:
        logger.error(f"Advisory sentiment error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/advisory/html', methods=['GET'])
def get_advisory_html():
    """Get HTML formatted advisory for dashboard."""
    if not sentiment_advisor:
        return """
        <div class="market-sentiment">
            <h3>📊 Market Sentiment Advisory</h3>
            <p class="advisory-note">⚠️ Not configured (Neo4j not available)</p>
            <p>Run with Neo4j and OpenAI for sentiment analysis.</p>
        </div>
        """
    
    try:
        return sentiment_advisor.format_for_dashboard()
    except Exception as e:
        logger.error(f"Advisory HTML error: {e}")
        return f"""
        <div class="market-sentiment">
            <h3>📊 Market Sentiment Advisory</h3>
            <p class="advisory-note">⚠️ Error: {e}</p>
        </div>
        """


@app.route('/advisory/events', methods=['GET'])
def get_upcoming_events():
    """Get upcoming economic events affecting forex pairs."""
    if not sentiment_advisor or not sentiment_advisor.graph.is_available:
        return jsonify({
            'status': 'unavailable',
            'message': 'Event calendar not available (Neo4j not configured)',
            'events': []
        }), 200
    
    try:
        hours = int(request.args.get('hours', 24))
        currency = request.args.get('currency', None)
        
        events = sentiment_advisor.graph.get_upcoming_events(
            currency=currency, 
            hours_ahead=hours
        )
        
        return jsonify({
            'status': 'success',
            'events': [
                {
                    'id': e.id,
                    'title': e.title,
                    'currency': e.currency,
                    'impact': e.impact.value,
                    'scheduled_at': e.scheduled_at.isoformat(),
                    'forecast': e.forecast,
                    'previous': e.previous
                }
                for e in events
            ]
        })
    except Exception as e:
        logger.error(f"Events error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


if __name__ == '__main__':
    PORT = 5000
    
    print("\n" + "="*70)
    print("TRADINGVIEW STRATEGY ANALYZER")
    print("="*70)
    print("Mode: ANALYSIS ONLY (No broker, no real trades)")
    print("Webhook Secret: " + ("*" * 8) + " (configured)" if WEBHOOK_SECRET and WEBHOOK_SECRET != 'your_secret_key_here' else "WARNING: Using default secret!")
    print(f"PulseGraph Advisory: {'ENABLED' if sentiment_advisor else 'DISABLED (Neo4j not available)'}")
    print(f"\nServer starting on http://localhost:{PORT}")
    print("\nEndpoints:")
    print("  POST /webhook         - Receive TradingView market data")
    print("  GET  /health          - Health check")
    print("  GET  /data            - View collected market data")
    print("  GET  /signals         - Check current strategy signals")
    print("  GET  /advisory/sentiment - Market sentiment (ADVISORY ONLY)")
    print("  GET  /advisory/html   - Sentiment HTML for dashboard")
    print("  GET  /advisory/events - Upcoming economic events")
    print("\nTo connect TradingView:")
    print("  1. Install ngrok: brew install ngrok")
    print(f"  2. Run: ngrok http {PORT}")
    print("  3. Copy HTTPS URL (e.g., https://abc123.ngrok.io)")
    print("  4. In TradingView, create alert with webhook:")
    print("     https://abc123.ngrok.io/webhook")
    print("\n📊 Your strategy will analyze real TradingView data")
    print("   Signals will be logged (no trades executed)")
    print("="*70 + "\n")
    
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
    # Start daily report scheduler in background
    import threading
    import time as time_module
    from datetime import datetime as dt
    
    def daily_report_scheduler():
        """Background thread to send daily reports at end of session."""
        # Initialize to today to prevent immediate report on restart
        from datetime import datetime as dt_inner
        now_dt = dt_inner.now(timezone.utc)
        last_report_date = now_dt.date()
        last_weekly_date = now_dt.date() if now_dt.weekday() == 6 else None
        last_journal_date = now_dt.date() if now_dt.weekday() == 4 and now_dt.hour >= 22 else None
        
        # Track session alerts (prevent duplicates)
        last_session_start_date = now_dt.date() if 10 <= now_dt.hour < 17 else None
        last_session_end_date = now_dt.date() if now_dt.hour >= 17 else None
        
        # Wait 2 minutes before first check to allow startup
        time_module.sleep(120)
        
        while True:
            try:
                now = dt.now(timezone.utc)
                today = now.date()
                
                # === SESSION START ALERT (10:00 UTC) ===
                # Only on weekdays (Mon-Fri) and if not already sent today
                if now.hour == 10 and now.minute < 30 and now.weekday() < 5:
                    if last_session_start_date != today:
                        session_msg = (
                            "🟢 <b>Trading Session Started</b>\n\n"
                            f"⏰ {now.strftime('%H:%M')} UTC | {now.strftime('%A')}\n"
                            f"📊 Session: 10:00 - 17:00 UTC\n"
                            f"🎯 Pairs: EUR/USD, GBP/USD\n\n"
                            "<i>Actively scanning for ICT setups...</i>"
                        )
                        if telegram_notifier:
                            telegram_notifier.send_message(session_msg)
                        if telegram_group_notifier:
                            telegram_group_notifier.send_message(session_msg)
                        logger.info("🟢 Session start alert sent")
                        last_session_start_date = today
                
                # === SESSION END ALERT (17:00 UTC) ===
                # Only on weekdays and if not already sent today
                if now.hour == 17 and now.minute < 30 and now.weekday() < 5:
                    if last_session_end_date != today:
                        # Get session stats
                        session_stats_msg = ""
                        if REPORT_TRACKER_AVAILABLE and get_report_tracker:
                            tracker = get_report_tracker()
                            report = tracker.get_report_data()
                            stats = report.get('session_stats', {})
                            signals = report.get('signals_generated', [])
                            session_stats_msg = (
                                f"\n📈 <b>Session Summary:</b>\n"
                                f"   Signals: {len(signals)}\n"
                                f"   Candles: {stats.get('candles_analyzed', 0)}\n"
                                f"   Setups: {stats.get('setups_checked', 0)}\n"
                            )
                        
                        end_msg = (
                            "🔴 <b>Trading Session Ended</b>\n\n"
                            f"⏰ {now.strftime('%H:%M')} UTC | {now.strftime('%A')}"
                            f"{session_stats_msg}\n"
                            "<i>Monitoring mode until next session...</i>"
                        )
                        if telegram_notifier:
                            telegram_notifier.send_message(end_msg)
                        if telegram_group_notifier:
                            telegram_group_notifier.send_message(end_msg)
                        logger.info("🔴 Session end alert sent")
                        last_session_end_date = today
                
                # === WEEKLY PERFORMANCE REPORT (Friday 22:00 UTC) ===
                # Sent after NY close, consolidates the entire week
                if now.weekday() == 4 and now.hour >= 22 and last_weekly_date != today:
                    if WEEKLY_REPORTER_AVAILABLE and get_weekly_reporter:
                        reporter = get_weekly_reporter()
                        weekly_text = reporter.format_telegram_report()
                        
                        # Send to personal
                        if telegram_notifier:
                            telegram_notifier.send_message(weekly_text)
                        # Send to group
                        if telegram_group_notifier:
                            telegram_group_notifier.send_message(weekly_text)
                        
                        # Archive the report
                        reporter.save_weekly_archive()
                        logger.info("📊 Weekly report sent to Telegram (personal + group)")
                        last_weekly_date = today
                
                # === WEEKLY TRADING JOURNAL (Friday 22:00 UTC) ===
                # Send after NY close, before weekend
                if now.weekday() == 4 and now.hour >= 22 and last_journal_date != today:
                    if JOURNAL_AVAILABLE and signal_journal:
                        try:
                            # Resolve all pending outcomes first
                            resolve_results = signal_journal.resolve_all_pending()
                            logger.info(f"📓 Journal: resolved {resolve_results.get('resolved', 0)} outcomes")
                            
                            # Generate and send weekly report
                            report = signal_journal.generate_weekly_report(week_offset=0)
                            if report.get('total_signals', 0) > 0:
                                journal_text = signal_journal.format_telegram_report(report)
                                
                                # Send to personal
                                if telegram_notifier:
                                    telegram_notifier.send_message(journal_text, parse_mode='HTML')
                                # Send to group
                                if telegram_group_notifier:
                                    telegram_group_notifier.send_message(journal_text, parse_mode='HTML')
                                
                                logger.info(f"📓 Weekly trading journal sent (WR: {report['win_rate']:.1f}%, Pips: {report['total_pips']:+.1f})")
                            else:
                                logger.info("📓 Weekly journal: no signals to report")
                            
                            last_journal_date = today
                        except Exception as e:
                            logger.error(f"Weekly journal error: {e}")
                
                # Check every 30 minutes
                time_module.sleep(1800)
                
            except Exception as e:
                logger.error(f"Daily report scheduler error: {e}")
                time_module.sleep(300)  # Wait 5 min on error
    
    # Start scheduler thread
    if REPORT_TRACKER_AVAILABLE and telegram_notifier:
        scheduler_thread = threading.Thread(target=daily_report_scheduler, daemon=True)
        scheduler_thread.start()
        logger.info("📅 Daily report scheduler started")
    
    # ============================================
    # TELEGRAM COMMAND HANDLER
    # Allows you to control the bot via Telegram
    # ============================================
    
    def telegram_command_handler():
        """Poll for Telegram commands and respond."""
        import time as time_module
        
        last_update_id = 0
        ADMIN_USER_ID = '117216462'  # Your Telegram USER ID (not chat ID)
        
        logger.info("🤖 Telegram command handler started")
        
        # Startup message disabled to avoid spam on restarts
        # Use /help command instead
        
        while True:
            try:
                # Get updates from Telegram
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
                params = {'offset': last_update_id + 1, 'timeout': 30}
                
                response = requests.get(url, params=params, timeout=35)
                data = response.json()
                
                if not data.get('ok'):
                    time_module.sleep(5)
                    continue
                
                for update in data.get('result', []):
                    last_update_id = update['update_id']
                    
                    message = update.get('message', {})
                    chat_id = str(message.get('chat', {}).get('id', ''))
                    user_id = str(message.get('from', {}).get('id', ''))
                    text = message.get('text', '').strip().lower()
                    
                    # Only respond to YOUR commands (works in personal chat AND group)
                    if user_id != ADMIN_USER_ID:
                        continue
                    
                    # Determine where to send the response
                    # If command came from group, reply to group
                    # If command came from personal chat, reply to personal
                    response_chat_id = chat_id
                    
                    # Process commands
                    response_text = None
                    
                    if text == '/status' or text == '/start':
                        # Get current prices
                        prices = []
                        for sym in ['EURUSD', 'GBPUSD', 'XAUUSD']:
                            if sym in market_data and market_data[sym].get('5M', {}).get('close'):
                                price = market_data[sym]['5M']['close'][-1]
                                prices.append(f"  {sym}: {price:.5f}" if sym != 'XAUUSD' else f"  {sym}: {price:.2f}")
                        
                        prices_text = "\n".join(prices) if prices else "  Collecting data..."
                        
                        response_text = (
                            "🤖 <b>Jarvis Status</b>\n\n"
                            f"🟢 Bot is RUNNING\n"
                            f"📈 Strategy: ICT/SMC (1:2 R:R)\n"
                            f"⏰ Session: 10:00-17:00 UTC\n\n"
                            f"<b>Current Prices:</b>\n{prices_text}"
                        )
                    
                    elif text == '/report':
                        # Send weekly performance report on demand
                        if WEEKLY_REPORTER_AVAILABLE and get_weekly_reporter:
                            reporter = get_weekly_reporter()
                            weekly_text = reporter.format_telegram_report()
                            if telegram_notifier:
                                telegram_notifier.send_message(weekly_text)
                            if telegram_group_notifier:
                                telegram_group_notifier.send_message(weekly_text)
                            response_text = "📊 Weekly report sent!"
                        else:
                            response_text = "❌ Weekly reporter not available"
                    
                    elif text == '/pairs':
                        response_text = (
                            "📊 <b>Tracked Pairs</b>\n\n"
                            "• EURUSD (6E=F futures)\n"
                            "• GBPUSD (6B=F futures)\n"
                            "• XAUUSD (GC=F gold futures)\n\n"
                            "⚠️ Gold shows futures price (~$30-40 above spot)"
                        )
                    
                    elif text == '/session':
                        now = datetime.now(timezone.utc)
                        session_end = now.replace(hour=17, minute=0, second=0)
                        
                        if 10 <= now.hour < 17 and now.weekday() < 4:
                            status = "🟢 IN SESSION"
                            remaining = session_end - now
                            hours_left = remaining.seconds // 3600
                            mins_left = (remaining.seconds % 3600) // 60
                            time_info = f"Ends in {hours_left}h {mins_left}m"
                        else:
                            status = "🔴 OUTSIDE SESSION"
                            if now.weekday() >= 4:
                                time_info = "Weekend - no trading"
                            elif now.hour >= 17:
                                time_info = "Resumes tomorrow 10:00 UTC"
                            else:
                                time_info = f"Starts at 10:00 UTC ({10 - now.hour}h away)"
                        
                        response_text = (
                            f"⏰ <b>Session Info</b>\n\n"
                            f"Status: {status}\n"
                            f"Time: {now.strftime('%H:%M')} UTC\n"
                            f"Day: {now.strftime('%A')}\n\n"
                            f"{time_info}\n\n"
                            f"📅 Trading Hours: 10:00-17:00 UTC\n"
                            f"📅 Days: Mon-Thu only"
                        )
                    
                    elif text == '/stats':
                        if REPORT_TRACKER_AVAILABLE and get_report_tracker:
                            tracker = get_report_tracker()
                            report = tracker.get_report_data()
                            stats = report.get('session_stats', {})
                            rejections = report.get('rejections_summary', {})
                            signals = report.get('signals_generated', [])
                            
                            # Top rejection reasons
                            top_rejections = sorted(rejections.items(), key=lambda x: x[1], reverse=True)[:3]
                            rej_text = "\n".join([f"  • {r[0]}: {r[1]}" for r in top_rejections]) or "  None"
                            
                            # Format active time
                            hours = stats.get('hours_active', 0)
                            mins = stats.get('minutes_active', 0)
                            if hours > 0:
                                time_active = f"{hours}h {mins}m"
                            else:
                                time_active = f"{mins}m"
                            
                            response_text = (
                                f"📊 <b>Today's Statistics</b>\n\n"
                                f"<b>Signals:</b> {len(signals)}\n"
                                f"<b>Candles Analyzed:</b> {stats.get('candles_analyzed', 0)}\n"
                                f"<b>Setups Checked:</b> {stats.get('setups_checked', 0)}\n"
                                f"<b>Active Time:</b> {time_active}\n\n"
                                f"<b>Top Rejections:</b>\n{rej_text}"
                            )
                        else:
                            response_text = "❌ Stats not available"
                    
                    elif text == '/help':
                        response_text = (
                            "🤖 <b>Jarvis Commands</b>\n\n"
                            "/status - Bot status & prices\n"
                            "/report - Weekly performance report\n"
                            "/stats - Today's statistics\n"
                            "/ml - ML model stats\n"
                            "/abtest - A/B test comparison\n"
                            "/pairs - Tracked pairs\n"
                            "/session - Session times\n"
                            "/help - This help message"
                        )
                    
                    elif text == '/ml':
                        # Send ML model stats
                        if ML_RISK_AVAILABLE and get_ml_risk_model:
                            model = get_ml_risk_model()
                            stats = model.get_model_stats()
                            
                            status_emoji = "🟢" if stats.get('model_active') else "🟡"
                            
                            ml_text = (
                                f"🤖 <b>ML Risk Model</b>\n\n"
                                f"Status: {status_emoji} {stats.get('status', 'unknown').replace('_', ' ').title()}\n"
                                f"Training Samples: {stats.get('total_samples', 0)}\n"
                                f"Wins: {stats.get('wins', 0)} | Losses: {stats.get('losses', 0)}\n"
                                f"Win Rate: {stats.get('win_rate', 0)*100:.1f}%\n\n"
                            )
                            
                            # By symbol
                            by_sym = stats.get('by_symbol', {})
                            if by_sym:
                                ml_text += "<b>By Symbol:</b>\n"
                                for sym, data in by_sym.items():
                                    wr = data['wins'] / data['total'] * 100 if data['total'] > 0 else 0
                                    ml_text += f"  {sym}: {wr:.0f}% ({data['total']} trades)\n"
                            
                            if telegram_notifier:
                                telegram_notifier.send_message(ml_text)
                            response_text = "🤖 ML stats sent!"
                        else:
                            response_text = f"❌ {MSG_ML_NOT_AVAILABLE}"
                    
                    elif text == '/weekly':
                        # Send weekly report
                        if WEEKLY_REPORTER_AVAILABLE and get_weekly_reporter:
                            reporter = get_weekly_reporter()
                            weekly_text = reporter.format_telegram_report()
                            if telegram_notifier:
                                telegram_notifier.send_message(weekly_text)
                            if telegram_group_notifier:
                                telegram_group_notifier.send_message(weekly_text)
                            response_text = "📊 Weekly report sent!"
                        else:
                            response_text = "❌ Weekly reporter not available"
                    
                    elif text == '/abtest':
                        # Send A/B test comparison
                        if AB_TESTING_AVAILABLE and get_ab_framework:
                            framework = get_ab_framework()
                            ab_text = framework.format_telegram_report()
                            if telegram_notifier:
                                telegram_notifier.send_message(ab_text)
                            response_text = "🔬 A/B test report sent!"
                        else:
                            response_text = "❌ A/B Testing not available"
                    
                    # Send response to wherever the command came from
                    if response_text:
                        try:
                            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                            payload = {
                                'chat_id': response_chat_id,
                                'text': response_text,
                                'parse_mode': 'HTML'
                            }
                            requests.post(url, json=payload, timeout=10)
                        except Exception as e:
                            logger.error(f"Failed to send command response: {e}")
                
                time_module.sleep(1)  # Small delay between polls
                
            except Exception as e:
                logger.error(f"Telegram command handler error: {e}")
                time_module.sleep(10)
    
    # Start Telegram command handler thread
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        command_thread = threading.Thread(target=telegram_command_handler, daemon=True)
        command_thread.start()
        logger.info("🤖 Telegram command handler started")
    
    # Run server
    app.run(host='0.0.0.0', port=PORT, debug=False)
