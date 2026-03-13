"""
Trade Performance Tracker
Monitors actual signal performance and calculates real win rates.
Automatically resolves signals when price hits TP or SL.

CRITICAL: All trade resolutions are VERIFIED against real yfinance price
history. We never trust a single candle — we fetch the full history from
signal detection time to now and walk through candles chronologically to
determine what was hit first.
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / 'data'
TRADES_FILE = DATA_DIR / 'active_trades.json'
HISTORY_FILE = DATA_DIR / 'trade_history.json'

# yfinance ticker mapping (CME futures)
YFINANCE_TICKER_MAP = {
    'EUR_USD': '6E=F',
    'GBP_USD': '6B=F',
    'XAU_USD': 'GC=F',
    'EURUSD': '6E=F',
    'GBPUSD': '6B=F',
    'XAUUSD': 'GC=F',
}

# Spot-futures spread buffer.
# We verify against CME futures (6E=F, 6B=F, GC=F) but user trades spot
# on Exness. Futures carry a premium over spot that varies throughout
# the day. On Feb 18, 2026 futures hit 6.5 pips above SL while spot
# on Exness never touched it — so 2 pips was way too small.
# Buffer = minimum distance BEYOND SL/TP the futures price must reach
# before we consider it a real hit on spot.
# Reduced 2026-03-13: 8 pips was too large — GBP SL at 12 pips from entry
# was hit on broker but bot couldn't detect it (needed price 8 pips beyond SL).
# Futures-spot divergence for forex is typically 1-3 pips, not 8.
SPREAD_BUFFER = {
    'EUR_USD': 0.00020,  # 2 pips — typical futures-spot divergence
    'GBP_USD': 0.00020,  # 2 pips — was 8, caused missed SL detection
    'XAU_USD': 3.00,     # 30 pips ($3.00) — Gold futures vs spot ~$30-40 gap
    'EURUSD': 0.00020,
    'GBPUSD': 0.00020,
    'XAUUSD': 3.00,
}

# Cache yfinance import
_yf = None

def _get_yfinance():
    """Lazy-load yfinance to avoid import cost on every candle."""
    global _yf
    if _yf is None:
        try:
            import yfinance as yf
            _yf = yf
        except ImportError:
            logger.error("yfinance not installed — price verification disabled")
    return _yf


def _calculate_pips(price_diff: float, symbol: str) -> float:
    """
    Calculate pips from a price difference.
    Forex pairs: 1 pip = 0.0001 (10,000 multiplier)
    Gold (XAU):  1 pip = 0.10   (10 multiplier)
    """
    if 'XAU' in symbol or 'GOLD' in symbol:
        return price_diff * 10  # Gold: $0.10 = 1 pip
    return price_diff * 10000   # Forex: 0.0001 = 1 pip


def fetch_price_history(symbol: str, start_time: datetime, end_time: datetime = None,
                        interval: str = '5m') -> Optional[Any]:
    """
    Fetch real price candles from yfinance between start_time and end_time.
    
    Returns a DataFrame with columns: Open, High, Low, Close (or None on failure).
    """
    yf = _get_yfinance()
    if yf is None:
        return None
    
    ticker_symbol = YFINANCE_TICKER_MAP.get(symbol)
    if not ticker_symbol:
        logger.warning(f"No yfinance ticker for {symbol}")
        return None
    
    if end_time is None:
        end_time = datetime.now(timezone.utc)
    
    # Ensure timezone-aware
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    
    # yfinance 5m data limited to ~60 days
    try:
        ticker = yf.Ticker(ticker_symbol)
        # Add buffer: start 1 candle before signal, end 1 candle after now
        fetch_start = start_time - timedelta(minutes=10)
        fetch_end = end_time + timedelta(minutes=10)
        
        df = ticker.history(start=fetch_start, end=fetch_end, interval=interval)
        
        if df is None or df.empty:
            logger.warning(f"No price data returned for {ticker_symbol} ({start_time} → {end_time})")
            return None
        
        # Filter to only candles AFTER signal entry time
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize('UTC')
        else:
            df.index = df.index.tz_convert('UTC')
        
        df = df[df.index >= start_time]
        
        if df.empty:
            logger.warning(f"No candles after signal time {start_time} for {ticker_symbol}")
            return None
        
        logger.info(f"📈 Fetched {len(df)} candles for {symbol} ({start_time.strftime('%H:%M')} → {end_time.strftime('%H:%M')} UTC)")
        return df
        
    except Exception as e:
        logger.error(f"Failed to fetch price history for {symbol}: {e}")
        return None


def verify_trade_against_history(trade_or_dict, symbol: str = None) -> Optional[Dict[str, Any]]:
    """
    THE CRITICAL VERIFICATION FUNCTION.
    
    Fetches real price data from signal detection time to now,
    walks through candles chronologically, and determines what
    was hit FIRST — SL or TP.
    
    Args:
        trade_or_dict: Trade dataclass or signal dict
        symbol: Override symbol (used when passing raw signal dict)
    
    Returns:
        None if no resolution found (trade still active), or dict:
        {
            'outcome': 'win' | 'loss',
            'exit_price': float,
            'exit_time': str (ISO),
            'hit_candle_time': str (ISO),
            'candles_checked': int,
            'verified': True
        }
    """
    # Extract trade parameters
    if isinstance(trade_or_dict, Trade):
        sym = trade_or_dict.symbol
        direction = trade_or_dict.direction
        entry_price = trade_or_dict.entry_price
        stop_loss = trade_or_dict.stop_loss
        take_profit = trade_or_dict.take_profit
        entry_time_str = trade_or_dict.entry_time
    else:
        sym = symbol or trade_or_dict.get('symbol', '')
        direction = trade_or_dict.get('direction', 'long')
        entry_price = trade_or_dict.get('entry_price', trade_or_dict.get('entry', 0))
        stop_loss = trade_or_dict.get('stop_loss', 0)
        take_profit = trade_or_dict.get('take_profit', 0)
        entry_time_str = trade_or_dict.get('entry_time', trade_or_dict.get('detected_at', ''))
    
    if not all([sym, entry_price, stop_loss, take_profit, entry_time_str]):
        logger.warning(f"Incomplete trade data for verification: {sym}")
        return None
    
    # Parse entry time
    try:
        if isinstance(entry_time_str, str):
            entry_dt = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
        else:
            entry_dt = entry_time_str
        if entry_dt.tzinfo is None:
            entry_dt = entry_dt.replace(tzinfo=timezone.utc)
    except Exception as e:
        logger.error(f"Failed to parse entry time '{entry_time_str}': {e}")
        return None
    
    # Fetch price history
    df = fetch_price_history(sym, entry_dt)
    if df is None:
        logger.warning(f"Cannot verify {sym} — no price history available")
        return None
    
    # Spread buffer: futures can tick beyond spot, so require price to
    # exceed SL/TP by at least this much before confirming a hit.
    buffer = SPREAD_BUFFER.get(sym, 0.00020)
    
    # Walk through candles chronologically
    # PHASE 1: Verify entry was filled (sell limit / buy limit logic)
    # For SHORT: price must rise TO or ABOVE entry (sell limit triggers)
    # For LONG: price must drop TO or BELOW entry (buy limit triggers)
    # If entry was never reached, the limit order never filled.
    entry_filled = False
    entry_fill_idx = 0
    
    candles_checked = 0
    for idx, (candle_time, row) in enumerate(df.iterrows()):
        candles_checked += 1
        high = row['High']
        low = row['Low']
        
        if direction in ('long', 'buy'):
            # Buy limit fills when price drops TO or BELOW entry
            if low <= entry_price:
                entry_filled = True
                entry_fill_idx = idx
                break
        else:  # short / sell
            # Sell limit fills when price rises TO or ABOVE entry
            if high >= entry_price:
                entry_filled = True
                entry_fill_idx = idx
                break
    
    if not entry_filled:
        # Entry was never reached — limit order never triggered
        # Check if enough time has passed to consider it expired
        time_since_signal = (datetime.now(timezone.utc) - entry_dt).total_seconds()
        if time_since_signal > 24 * 3600:  # 24 hours without fill = expired
            logger.info(
                f"⏰ EXPIRED — {sym} entry at {entry_price:.5f} never reached "
                f"after {candles_checked} candles ({time_since_signal/3600:.1f}h). Limit order cancelled."
            )
            return {
                'outcome': 'expired',
                'exit_price': entry_price,
                'exit_time': datetime.now(timezone.utc).isoformat(),
                'hit_candle_time': 'never_filled',
                'candles_checked': candles_checked,
                'verified': True,
                'entry_filled': False,
            }
        else:
            logger.debug(
                f"⏳ {sym} entry at {entry_price:.5f} not yet reached — "
                f"limit order pending ({candles_checked} candles checked)"
            )
            return None  # Still waiting for fill
    
    logger.debug(f"✅ {sym} entry filled on candle {entry_fill_idx} — now checking TP/SL")
    
    # PHASE 2: Walk from entry fill candle onward, checking TP/SL
    candles_checked = 0
    for candle_time, row in list(df.iterrows())[entry_fill_idx:]:
        candles_checked += 1
        high = row['High']
        low = row['Low']
        
        hit_tp = False
        hit_sl = False
        
        if direction in ('long', 'buy'):
            hit_tp = high >= (take_profit - buffer)   # TP: generous (futures may undershoot)
            hit_sl = low <= (stop_loss - buffer)       # SL: strict (must clearly breach)
        else:  # short / sell
            hit_tp = low <= (take_profit + buffer)     # TP: generous
            hit_sl = high >= (stop_loss + buffer)      # SL: strict (must clearly breach)
        
        # Same candle: SL takes priority (conservative)
        if hit_sl:
            return {
                'outcome': 'loss',
                'exit_price': stop_loss,
                'exit_time': candle_time.isoformat(),
                'hit_candle_time': candle_time.isoformat(),
                'candles_checked': candles_checked,
                'verified': True,
                'entry_filled': True,
            }
        elif hit_tp:
            return {
                'outcome': 'win',
                'exit_price': take_profit,
                'exit_time': candle_time.isoformat(),
                'hit_candle_time': candle_time.isoformat(),
                'candles_checked': candles_checked,
                'verified': True,
                'entry_filled': True,
            }
    
    # Neither TP nor SL hit yet
    logger.debug(f"Verified {candles_checked} candles for {sym} — trade still active")
    return None


@dataclass
class Trade:
    """Active trade being monitored."""
    signal_id: str
    symbol: str
    direction: str  # 'long' or 'short'
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_time: str
    setup_type: str
    confidence: float
    
    # Performance tracking
    status: str = 'active'  # 'active', 'win', 'loss', 'breakeven'
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    pips_result: Optional[float] = None
    rr_achieved: Optional[float] = None


class TradeTracker:
    """Track and analyze trade performance."""
    
    def __init__(self, on_resolve_callback=None):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.active_trades: Dict[str, Trade] = self._load_active_trades()
        self.history: List[Dict] = self._load_history()
        self._verifier_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._verifier_interval_seconds = int(os.environ.get('TRADE_VERIFY_INTERVAL_SECONDS', '300'))
        self._on_resolve_callback = on_resolve_callback
        self._start_background_verifier()

    def _start_background_verifier(self):
        """Start background verification worker (non-blocking for webhook requests)."""
        if self._verifier_interval_seconds <= 0:
            logger.info("Background trade verifier disabled (TRADE_VERIFY_INTERVAL_SECONDS<=0)")
            return
        if self._verifier_thread and self._verifier_thread.is_alive():
            return

        def _loop():
            while not self._stop_event.is_set():
                try:
                    resolved = self.verify_active_trades(max_trades_per_cycle=5)
                    if resolved and self._on_resolve_callback:
                        for trade in resolved:
                            try:
                                self._on_resolve_callback(trade)
                            except Exception as cb_err:
                                logger.error(f"Resolve callback error: {cb_err}")
                except Exception as e:
                    logger.error(f"Background verification error: {e}")
                self._stop_event.wait(self._verifier_interval_seconds)

        self._verifier_thread = threading.Thread(target=_loop, name='trade-verifier', daemon=True)
        self._verifier_thread.start()
        logger.info(f"✅ Background trade verifier started (every {self._verifier_interval_seconds}s)")

    def verify_active_trades(self, symbol: str = None, max_trades_per_cycle: int = 5) -> List[Dict[str, Any]]:
        """Run full yfinance verification on active trades outside webhook request path."""
        resolved = []

        with self._lock:
            candidates = [
                (signal_id, trade)
                for signal_id, trade in self.active_trades.items()
                if trade.status == 'active' and (symbol is None or trade.symbol == symbol)
            ]

        checked = 0
        for signal_id, trade in candidates:
            if checked >= max_trades_per_cycle:
                break
            checked += 1

            verification = verify_trade_against_history(trade)
            if not verification or not verification.get('verified'):
                continue

            outcome = verification['outcome']
            trade.status = outcome
            trade.exit_price = verification['exit_price']
            trade.exit_time = verification['exit_time']

            if trade.direction in ('long', 'buy'):
                if outcome == 'win':
                    trade.pips_result = _calculate_pips(trade.take_profit - trade.entry_price, trade.symbol)
                else:
                    trade.pips_result = _calculate_pips(trade.stop_loss - trade.entry_price, trade.symbol)
            else:
                if outcome == 'win':
                    trade.pips_result = _calculate_pips(trade.entry_price - trade.take_profit, trade.symbol)
                else:
                    trade.pips_result = -_calculate_pips(trade.stop_loss - trade.entry_price, trade.symbol)

            sl_distance = _calculate_pips(abs(trade.entry_price - trade.stop_loss), trade.symbol)
            trade.rr_achieved = (trade.pips_result / sl_distance) if sl_distance > 0 else 0

            with self._lock:
                if signal_id in self.active_trades:
                    self.active_trades.pop(signal_id)
                    self.history.append(asdict(trade))

            resolved.append({**asdict(trade), 'verified': True})

        if resolved:
            with self._lock:
                self._save_active_trades()
                self._save_history()
        return resolved
    
    def _load_active_trades(self) -> Dict[str, Trade]:
        """Load active trades from file."""
        try:
            if TRADES_FILE.exists():
                with open(TRADES_FILE, 'r') as f:
                    data = json.load(f)
                    return {k: Trade(**v) for k, v in data.items()}
        except Exception as e:
            logger.error(f"Error loading active trades: {e}")
        return {}
    
    def _save_active_trades(self):
        """Save active trades to file."""
        try:
            with open(TRADES_FILE, 'w') as f:
                data = {k: asdict(v) for k, v in self.active_trades.items()}
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving active trades: {e}")
    
    def _load_history(self) -> List[Dict]:
        """Load trade history."""
        try:
            if HISTORY_FILE.exists():
                with open(HISTORY_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading history: {e}")
        return []
    
    def _save_history(self):
        """Save trade history."""
        try:
            with open(HISTORY_FILE, 'w') as f:
                json.dump(self.history, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving history: {e}")
    
    def add_trade(self, signal: Dict[str, Any], symbol: str, signal_id: str = None,
                  skip_verification: bool = False) -> Tuple[str, Optional[Dict]]:
        """
        Add a new trade to track.
        
        On registration, immediately verifies against real price history.
        If SL/TP was already hit (e.g. stale signal on restart), resolves
        it instantly with verified data — never trusts a blind comparison.
        
        Args:
            signal: Signal dict from strategy.analyze()
            symbol: e.g. 'EUR_USD'
            signal_id: Key from active_signals dict (used to sync resolution)
            skip_verification: If True, skip yfinance check (for brand-new signals < 1 candle old)
        
        Returns:
            (trade_id, resolution_dict_or_None)
            - resolution_dict is set if the trade was immediately resolved via verification
        """
        trade_id = signal_id or f"{symbol}_{signal.get('timestamp', int(datetime.now().timestamp()))}"
        
        # Don't double-register
        with self._lock:
            if trade_id in self.active_trades:
                logger.debug(f"Trade {trade_id} already tracked, skipping")
                return trade_id, None
        
        trade = Trade(
            signal_id=trade_id,
            symbol=symbol,
            direction=signal.get('direction', 'long'),
            entry_price=signal.get('entry_price', 0),
            stop_loss=signal.get('stop_loss', 0),
            take_profit=signal.get('take_profit', 0),
            entry_time=datetime.fromtimestamp(signal.get('timestamp', datetime.now().timestamp())).isoformat(),
            setup_type=signal.get('setup_type', 'UNKNOWN'),
            confidence=signal.get('confidence', 0.0)
        )
        
        logger.info(f"📊 Tracking new trade: {trade_id} | {trade.direction} {symbol} @ {trade.entry_price:.5f} | SL={trade.stop_loss:.5f} TP={trade.take_profit:.5f}")
        
        # ── IMMEDIATE VERIFICATION ──
        # For signals that are more than 1 candle old (e.g. startup sync),
        # verify against real price history BEFORE accepting as active.
        if not skip_verification:
            verification = verify_trade_against_history(trade)
            if verification and verification.get('verified'):
                outcome = verification['outcome']
                
                # Handle expired (entry never filled — limit order cancelled)
                if outcome == 'expired':
                    trade.status = 'expired'
                    trade.exit_time = verification['exit_time']
                    trade.pips_result = 0
                    trade.rr_achieved = 0
                    self.history.append(asdict(trade))
                    self._save_history()
                    logger.info(
                        f"⏰ EXPIRED on registration — {trade_id} | "
                        f"Entry {trade.entry_price:.5f} never reached (limit not filled)"
                    )
                    return trade_id, {**asdict(trade), 'verified': True, 'entry_filled': False}
                
                trade.status = outcome
                trade.exit_price = verification['exit_price']
                trade.exit_time = verification['exit_time']
                
                if trade.direction in ('long', 'buy'):
                    if outcome == 'win':
                        trade.pips_result = _calculate_pips(trade.take_profit - trade.entry_price, symbol)
                    else:
                        trade.pips_result = _calculate_pips(trade.stop_loss - trade.entry_price, symbol)
                else:
                    if outcome == 'win':
                        trade.pips_result = _calculate_pips(trade.entry_price - trade.take_profit, symbol)
                    else:
                        trade.pips_result = -_calculate_pips(trade.stop_loss - trade.entry_price, symbol)
                
                sl_distance = _calculate_pips(abs(trade.entry_price - trade.stop_loss), symbol)
                trade.rr_achieved = (trade.pips_result / sl_distance) if sl_distance > 0 else 0
                
                # Straight to history — never sits as "active"
                self.history.append(asdict(trade))
                self._save_history()
                
                candles = verification.get('candles_checked', '?')
                hit_time = verification.get('hit_candle_time', '?')
                icon = "✅" if outcome == 'win' else "❌"
                logger.info(
                    f"{icon} VERIFIED {outcome.upper()} on registration — {trade_id} | "
                    f"{trade.pips_result:.1f} pips | Hit at {hit_time} | "
                    f"Checked {candles} candles"
                )
                
                return trade_id, {**asdict(trade), 'verified': True}
        
        # No hit found yet — trade is genuinely active
        with self._lock:
            self.active_trades[trade_id] = trade
            self._save_active_trades()
        return trade_id, None
    
    def update_trades(self, symbol: str, current_price: float,
                       candle_high: float = None, candle_low: float = None,
                       force_verify: bool = False,
                       allow_full_verify: bool = True) -> List[Dict[str, Any]]:
        """
        Check if any active trades for this symbol hit TP or SL.
        
        TWO-LAYER RESOLUTION:
        1. Quick check: uses the incoming candle high/low (fast, every 5 min)
        2. Full verification: fetches yfinance history and walks chronologically
           - Triggered every 6th candle (~30 min) OR when quick check finds a hit
           - This catches gaps the poller missed
        
        A trade is NEVER resolved without yfinance verification.
        
        Args:
            symbol: e.g. 'EUR_USD'
            current_price: Candle close price
            candle_high: Candle high (if None, uses current_price)
            candle_low: Candle low (if None, uses current_price)
            force_verify: If True, always do full yfinance verification
        
        Returns:
            List of resolved trade dicts (for notifications/status sync).
        """
        if candle_high is None:
            candle_high = current_price
        if candle_low is None:
            candle_low = current_price
        
        resolved = []
        to_remove = []
        
        with self._lock:
            active_items = list(self.active_trades.items())

        for signal_id, trade in active_items:
            if trade.symbol != symbol or trade.status != 'active':
                continue
            
            # ── QUICK CHECK: Does the current candle touch TP/SL? ──
            # First: verify entry was filled (sell/buy limit logic)
            # For SHORT: price must have risen to entry (candle high >= entry)
            # For LONG: price must have dropped to entry (candle low <= entry)
            entry_filled = getattr(trade, '_entry_filled', False)
            
            if not entry_filled:
                if trade.direction in ('long', 'buy'):
                    if candle_low <= trade.entry_price:
                        trade._entry_filled = True
                        entry_filled = True
                        logger.info(f"✅ Entry filled: {signal_id} | {trade.direction} @ {trade.entry_price:.5f}")
                else:  # short / sell
                    if candle_high >= trade.entry_price:
                        trade._entry_filled = True
                        entry_filled = True
                        logger.info(f"✅ Entry filled: {signal_id} | {trade.direction} @ {trade.entry_price:.5f}")
                
                if not entry_filled:
                    # Entry not yet reached — skip TP/SL check
                    # Check if expired (24h without fill)
                    try:
                        entry_dt = datetime.fromisoformat(trade.entry_time.replace('Z', '+00:00'))
                        if entry_dt.tzinfo is None:
                            entry_dt = entry_dt.replace(tzinfo=timezone.utc)
                        age_hours = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 3600
                        if age_hours > 24:
                            logger.info(
                                f"⏰ EXPIRED — {signal_id} entry at {trade.entry_price:.5f} "
                                f"never reached after {age_hours:.1f}h. Cancelling."
                            )
                            trade.status = 'expired'
                            trade.exit_time = datetime.now(timezone.utc).isoformat()
                            trade.pips_result = 0
                            trade.rr_achieved = 0
                            to_remove.append(signal_id)
                            resolved.append({**asdict(trade), 'verified': True, 'entry_filled': False})
                    except Exception:
                        pass
                    continue  # Don't check TP/SL until entry fills
            
            # Apply spread buffer — futures price must clearly breach the level
            buffer = SPREAD_BUFFER.get(symbol, 0.00020)
            hit_tp = False
            hit_sl = False
            
            if trade.direction in ('long', 'buy'):
                hit_tp = candle_high >= (trade.take_profit - buffer)
                hit_sl = candle_low <= (trade.stop_loss - buffer)
            else:  # short / sell
                hit_tp = candle_low <= (trade.take_profit + buffer)
                hit_sl = candle_high >= (trade.stop_loss + buffer)
            
            quick_hit = hit_tp or hit_sl
            
            # ── PERIODIC FULL VERIFICATION ──
            # Track how many candles since last full verify
            if not hasattr(trade, '_verify_counter'):
                trade._verify_counter = 0
            trade._verify_counter = getattr(trade, '_verify_counter', 0) + 1
            
            # Full verify every 6 candles (~30 min) or when quick check found a hit
            needs_full_verify = allow_full_verify and (quick_hit or force_verify or (trade._verify_counter >= 6))
            
            if needs_full_verify:
                trade._verify_counter = 0  # Reset counter
                
                verification = verify_trade_against_history(trade)
                
                if verification and verification.get('verified'):
                    outcome = verification['outcome']
                    trade.status = outcome
                    trade.exit_price = verification['exit_price']
                    trade.exit_time = verification['exit_time']
                    
                    # Calculate pips
                    if trade.direction in ('long', 'buy'):
                        if outcome == 'win':
                            trade.pips_result = _calculate_pips(trade.take_profit - trade.entry_price, symbol)
                        else:
                            trade.pips_result = _calculate_pips(trade.stop_loss - trade.entry_price, symbol)
                    else:
                        if outcome == 'win':
                            trade.pips_result = _calculate_pips(trade.entry_price - trade.take_profit, symbol)
                        else:
                            trade.pips_result = -_calculate_pips(trade.stop_loss - trade.entry_price, symbol)
                    
                    sl_distance = _calculate_pips(abs(trade.entry_price - trade.stop_loss), symbol)
                    trade.rr_achieved = (trade.pips_result / sl_distance) if sl_distance > 0 else 0
                    
                    candles = verification.get('candles_checked', '?')
                    hit_time = verification.get('hit_candle_time', '?')
                    icon = "✅" if outcome == 'win' else "❌"
                    logger.info(
                        f"{icon} VERIFIED {outcome.upper()} — {signal_id} | "
                        f"{trade.pips_result:.1f} pips | Hit at {hit_time} | "
                        f"Checked {candles} candles of history"
                    )
                    
                    to_remove.append(signal_id)
                    resolved.append({**asdict(trade), 'verified': True})
                    
                elif quick_hit and verification is None:
                    # Quick check said hit, but yfinance returned no data
                    # DON'T resolve — we can't verify it
                    logger.warning(
                        f"⚠️ Quick check found {'TP' if hit_tp else 'SL'} hit for {signal_id} "
                        f"but yfinance verification returned no data — NOT resolving (will retry)"
                    )
                # else: verification returned None (no hit found in history) — trade stays active
        
        # Move completed trades to history
        with self._lock:
            for signal_id in to_remove:
                if signal_id in self.active_trades:
                    trade = self.active_trades.pop(signal_id)
                    self.history.append(asdict(trade))
        
        if to_remove:
            with self._lock:
                self._save_active_trades()
                self._save_history()
        
        return resolved
    
    def get_active_count(self) -> int:
        """Number of trades currently being monitored."""
        return sum(1 for t in self.active_trades.values() if t.status == 'active')
    
    def get_performance_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get performance statistics."""
        # Filter recent trades
        cutoff = datetime.now().timestamp() - (days * 86400)
        recent = [t for t in self.history if datetime.fromisoformat(t['entry_time']).timestamp() > cutoff]
        
        if not recent:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0.0,
                'total_pips': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'by_pair': {},
                'by_setup': {}
            }
        
        wins = [t for t in recent if t['status'] == 'win']
        losses = [t for t in recent if t['status'] == 'loss']
        
        total_pips = sum(t.get('pips_result', 0) for t in recent)
        win_pips = sum(t.get('pips_result', 0) for t in wins)
        loss_pips = abs(sum(t.get('pips_result', 0) for t in losses))
        
        # By pair
        by_pair = {}
        for symbol in set(t['symbol'] for t in recent):
            pair_trades = [t for t in recent if t['symbol'] == symbol]
            pair_wins = [t for t in pair_trades if t['status'] == 'win']
            by_pair[symbol] = {
                'trades': len(pair_trades),
                'wins': len(pair_wins),
                'win_rate': len(pair_wins) / len(pair_trades) * 100 if pair_trades else 0,
                'pips': sum(t.get('pips_result', 0) for t in pair_trades)
            }
        
        # By setup
        by_setup = {}
        for setup in set(t['setup_type'] for t in recent):
            setup_trades = [t for t in recent if t['setup_type'] == setup]
            setup_wins = [t for t in setup_trades if t['status'] == 'win']
            by_setup[setup] = {
                'trades': len(setup_trades),
                'wins': len(setup_wins),
                'win_rate': len(setup_wins) / len(setup_trades) * 100 if setup_trades else 0
            }
        
        return {
            'total_trades': len(recent),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / len(recent) * 100 if recent else 0,
            'total_pips': total_pips,
            'avg_win': win_pips / len(wins) if wins else 0,
            'avg_loss': loss_pips / len(losses) if losses else 0,
            'profit_factor': win_pips / loss_pips if loss_pips > 0 else 0,
            'by_pair': by_pair,
            'by_setup': by_setup
        }


# Singleton
_tracker: Optional[TradeTracker] = None

def get_trade_tracker(on_resolve_callback=None) -> TradeTracker:
    """Get trade tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = TradeTracker(on_resolve_callback=on_resolve_callback)
    elif on_resolve_callback is not None and _tracker._on_resolve_callback is None:
        _tracker._on_resolve_callback = on_resolve_callback
    return _tracker
