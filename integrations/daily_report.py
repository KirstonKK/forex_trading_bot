"""
Daily Report Tracker
Collects data throughout the trading day for end-of-day report.
"""

import os
import json
import logging
from datetime import datetime, date, timezone
from typing import Dict, List, Any, Optional
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)

# Import database
try:
    from database.trades import TradesDatabase
    DB_AVAILABLE = True
except ImportError:
    logger.warning("TradesDatabase not available, using JSON-only storage")
    DB_AVAILABLE = False

# Data file for persistence
DATA_DIR = Path(__file__).parent.parent / 'data'
REPORT_FILE = DATA_DIR / 'daily_report_data.json'


class DailyReportTracker:
    """Track trading activity for daily reports."""
    
    def __init__(self):
        # Initialize database connection
        if DB_AVAILABLE:
            try:
                self.db = TradesDatabase()
                logger.info("Database connection initialized for signal storage")
            except Exception as e:
                logger.error(f"Failed to initialize database: {e}")
                self.db = None
        else:
            self.db = None
        
        self.reset_if_new_day()
    
    def reset_if_new_day(self):
        """Reset data if it's a new trading day."""
        today = date.today().isoformat()
        
        # Try to load existing data
        self.data = self._load_data()
        
        # If it's a new day, reset
        if self.data.get('date') != today:
            self.data = {
                'date': today,
                'signals_generated': [],
                'rejections': defaultdict(int),
                'pair_analysis': {},
                'session_stats': {
                    'candles_analyzed': 0,
                    'setups_checked': 0,
                    'valid_sweeps': 0,
                    'valid_bos': 0,
                    'start_time': None,
                    'end_time': None,
                    'trading_minutes': 0  # Time spent in trading window (10-17 UTC)
                },
                'hourly_activity': defaultdict(int),
                'last_rejection_reasons': {}  # Per-pair last rejection
            }
            self._save_data()
    
    def _load_data(self) -> dict:
        """Load data from file."""
        try:
            if REPORT_FILE.exists():
                with open(REPORT_FILE, 'r') as f:
                    data = json.load(f)
                    # Convert defaultdicts
                    data['rejections'] = defaultdict(int, data.get('rejections', {}))
                    data['hourly_activity'] = defaultdict(int, data.get('hourly_activity', {}))
                    return data
        except Exception as e:
            logger.error(f"Error loading report data: {e}")
        return {}
    
    def _save_data(self):
        """Save data to file."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            # Convert defaultdicts to regular dicts for JSON
            save_data = self.data.copy()
            save_data['rejections'] = dict(save_data.get('rejections', {}))
            save_data['hourly_activity'] = dict(save_data.get('hourly_activity', {}))
            with open(REPORT_FILE, 'w') as f:
                json.dump(save_data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving report data: {e}")
    
    def record_signal(self, signal: Dict[str, Any], symbol: str):
        """Record a generated signal in both JSON and database."""
        self.reset_if_new_day()
        
        signal_record = {
            'symbol': symbol,
            'direction': signal.get('direction'),
            'entry_price': signal.get('entry_price'),
            'stop_loss': signal.get('stop_loss'),
            'take_profit': signal.get('take_profit'),
            'risk_reward': signal.get('risk_reward'),
            'setup_type': signal.get('setup_type'),
            'confirmations': signal.get('confirmations', []),
            'confidence': signal.get('confidence'),
            'timestamp': datetime.now().isoformat()
        }
        
        # Save to JSON (for backward compatibility)
        self.data['signals_generated'].append(signal_record)
        
        # Note: DB save is handled by the webhook server to avoid duplicates
        
        # Record hourly activity
        hour = datetime.now().hour
        self.data['hourly_activity'][str(hour)] += 1
        
        self._save_data()
        logger.info(f"📝 Recorded signal for {symbol}")
    
    def record_rejection(self, symbol: str, reasons: List[str]):
        """Record why a signal was rejected."""
        self.reset_if_new_day()
        
        for reason in reasons:
            self.data['rejections'][reason] = self.data['rejections'].get(reason, 0) + 1
        
        # Store last rejection for this pair
        self.data['last_rejection_reasons'][symbol] = {
            'reasons': reasons,
            'timestamp': datetime.now().isoformat()
        }
        
        self._save_data()
    
    def record_analysis(self, symbol: str, analysis: Dict[str, Any]):
        """Record pair analysis data."""
        self.reset_if_new_day()
        
        self.data['pair_analysis'][symbol] = {
            'htf_bias': analysis.get('htf_bias', 'neutral'),
            'sweeps_detected': analysis.get('sweeps_detected', 0),
            'fvgs_available': analysis.get('fvgs_available', 0),
            'obs_available': analysis.get('obs_available', 0),
            'rejection_reason': analysis.get('rejection_reason'),
            'last_update': datetime.now().isoformat()
        }
        
        self._save_data()
    
    def record_stats(self, stat_type: str, count: int = 1):
        """Record session statistics."""
        self.reset_if_new_day()
        
        if stat_type in self.data['session_stats']:
            self.data['session_stats'][stat_type] += count
        
        # Update session times
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        
        if not self.data['session_stats']['start_time']:
            self.data['session_stats']['start_time'] = now_str
        self.data['session_stats']['end_time'] = now_str
        
        # Track trading window time (10:00-17:00 UTC)
        if 10 <= now.hour < 17:
            # Add 5 minutes (typical candle interval) to trading time
            self.data['session_stats']['trading_minutes'] = \
                self.data['session_stats'].get('trading_minutes', 0) + 5
        
        self._save_data()
    
    def get_report_data(self) -> Dict[str, Any]:
        """Get compiled data for daily report."""
        self.reset_if_new_day()
        
        # Get signals from database if available (more reliable than JSON)
        signals_from_db = []
        if self.db:
            try:
                signals_from_db = self.db.get_signals(date=date.today().isoformat())
                logger.info(f"Retrieved {len(signals_from_db)} signals from database")
            except Exception as e:
                logger.error(f"Failed to get signals from database: {e}")
        
        # Use DB signals if available, otherwise fall back to JSON
        signals = signals_from_db if signals_from_db else self.data.get('signals_generated', [])
        
        # Calculate hours active in trading window (10:00-17:00 UTC)
        stats = self.data.get('session_stats', {})
        
        # Use trading_minutes which tracks actual time in trading window
        trading_mins = stats.get('trading_minutes', 0)
        hours_active = trading_mins // 60
        minutes_active = trading_mins % 60
        
        stats['hours_active'] = hours_active
        stats['minutes_active'] = minutes_active
        
        return {
            'date': self.data.get('date'),
            'signals_generated': signals,
            'rejections_summary': dict(self.data.get('rejections', {})),
            'pair_analysis': self.data.get('pair_analysis', {}),
            'session_stats': stats,
            'hourly_activity': dict(self.data.get('hourly_activity', {})),
            'market_sentiment': self._generate_sentiment(signals)
        }
    
    def _generate_sentiment(self, signals: List[Dict] = None) -> str:
        """Generate market sentiment summary."""
        if signals is None:
            signals = self.data.get('signals_generated', [])
        
        if not signals:
            rejections = self.data.get('rejections', {})
            if rejections:
                top_reason = max(rejections.items(), key=lambda x: x[1])[0] if rejections else "No data"
                return f"Quiet session. Most common issue: {top_reason}"
            return "No significant market activity detected."
        
        # Analyze signal directions
        buys = sum(1 for s in signals if s.get('direction') == 'BUY')
        sells = sum(1 for s in signals if s.get('direction') == 'SELL')
        
        if buys > sells * 2:
            return "Bullish bias detected. More buy setups validated."
        elif sells > buys * 2:
            return "Bearish bias detected. More sell setups validated."
        else:
            return "Mixed market conditions. Both directions showed setups."
    
    def should_send_report(self) -> bool:
        """Check if it's time to send the daily report (after 17:00 UTC)."""
        now = datetime.now(timezone.utc)
        hour = now.hour
        
        # Send report after session close (17:00 UTC) and before midnight
        # Only send once - check if we've already sent today
        if 17 <= hour < 23:
            last_report = self.data.get('last_report_sent')
            today = date.today().isoformat()
            
            if last_report != today:
                return True
        
        return False
    
    def mark_report_sent(self):
        """Mark that we've sent today's report and save a copy."""
        self.data['last_report_sent'] = date.today().isoformat()
        
        # Save a copy of the report for historical reference
        try:
            report_archive_file = DATA_DIR / f'report_{date.today().isoformat()}.json'
            save_data = self.data.copy()
            save_data['rejections'] = dict(save_data.get('rejections', {}))
            save_data['hourly_activity'] = dict(save_data.get('hourly_activity', {}))
            with open(report_archive_file, 'w') as f:
                json.dump(save_data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to archive report: {e}")
        
        self._save_data()


# Singleton instance
_tracker: Optional[DailyReportTracker] = None


def get_report_tracker() -> DailyReportTracker:
    """Get or create the report tracker singleton."""
    global _tracker
    if _tracker is None:
        _tracker = DailyReportTracker()
    return _tracker
