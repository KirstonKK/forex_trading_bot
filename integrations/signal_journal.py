"""
Signal Journal — Weekly Trading Performance Tracker

Checks every signal the bot sent to determine if it hit TP or SL,
then generates a weekly performance report sent to Telegram.

Outcome detection:
- Fetches 5M candles from yfinance after signal timestamp
- Walks candles chronologically to see which level was hit first (TP or SL)
- Marks signals as TP_HIT, SL_HIT, or EXPIRED (if neither hit within 48h)
"""

import logging
import os
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Pip definitions
PIP_VALUES = {
    'EUR_USD': 0.0001, 'GBP_USD': 0.0001, 'USD_JPY': 0.01,
    'XAU_USD': 0.10, 'EURUSD': 0.0001, 'GBPUSD': 0.0001,
    'USDJPY': 0.01, 'XAUUSD': 0.10,
}

# yfinance ticker mapping
TICKER_MAP = {
    'EUR_USD': 'EURUSD=X', 'GBP_USD': 'GBPUSD=X', 'XAU_USD': 'GC=F',
    'EURUSD': 'EURUSD=X', 'GBPUSD': 'GBPUSD=X', 'XAUUSD': 'GC=F',
}


def get_pip_value(symbol: str) -> float:
    """Get pip value for a symbol."""
    return PIP_VALUES.get(symbol, 0.0001)


def calculate_pips(symbol: str, entry: float, exit_price: float, direction: str) -> float:
    """Calculate pips gained/lost."""
    pip = get_pip_value(symbol)
    if direction.lower() in ('buy', 'long'):
        return (exit_price - entry) / pip
    else:
        return (entry - exit_price) / pip


class SignalJournal:
    """Tracks signal outcomes and generates weekly reports."""

    def __init__(self, db=None):
        """
        Args:
            db: TradesDatabase instance
        """
        self.db = db

    def check_signal_outcome(self, signal: Dict) -> Optional[Dict]:
        """
        Check if a signal hit TP or SL by walking price candles after signal time.

        Returns dict with outcome info, or None if can't determine yet.
        """
        try:
            import yfinance as yf
        except ImportError:
            logger.error("yfinance not installed")
            return None

        symbol = signal['symbol']
        direction = signal['direction'].lower()
        entry = signal['entry_price']
        sl = signal['stop_loss']
        tp = signal['take_profit']
        signal_time = signal['timestamp']

        # Parse signal timestamp
        if isinstance(signal_time, str):
            try:
                sig_dt = datetime.fromisoformat(signal_time.replace('Z', '+00:00'))
            except ValueError:
                sig_dt = datetime.strptime(signal_time, '%Y-%m-%d %H:%M:%S.%f')
        elif isinstance(signal_time, (int, float)):
            sig_dt = datetime.fromtimestamp(signal_time, tz=timezone.utc)
        else:
            sig_dt = signal_time

        # Make timezone-aware
        if sig_dt.tzinfo is None:
            sig_dt = sig_dt.replace(tzinfo=timezone.utc)

        # If signal is less than 1 hour old, skip — not enough data yet
        now = datetime.now(timezone.utc)
        if (now - sig_dt).total_seconds() < 3600:
            return None

        # Fetch 5M candles from signal time to now (max 48h window)
        end_dt = min(now, sig_dt + timedelta(hours=48))
        ticker = TICKER_MAP.get(symbol)
        if not ticker:
            logger.warning(f"No ticker mapping for {symbol}")
            return None

        try:
            data = yf.download(
                ticker, 
                start=sig_dt.strftime('%Y-%m-%d'),
                end=(end_dt + timedelta(days=1)).strftime('%Y-%m-%d'),
                interval='5m',
                progress=False
            )
        except Exception as e:
            logger.error(f"yfinance download failed for {symbol}: {e}")
            return None

        if data is None or data.empty:
            logger.warning(f"No price data for {symbol} after {sig_dt}")
            return None

        # Walk candles after signal time
        for idx, row in data.iterrows():
            # Convert index to UTC for comparison
            candle_time = idx
            if hasattr(candle_time, 'tz_localize'):
                try:
                    candle_time = candle_time.tz_localize('UTC')
                except TypeError:
                    pass  # Already tz-aware

            # Skip candles before signal
            candle_ts = candle_time.timestamp() if hasattr(candle_time, 'timestamp') else 0
            if candle_ts < sig_dt.timestamp():
                continue

            # Handle both flat and MultiIndex columns
            try:
                high = float(row['High'].iloc[0]) if hasattr(row['High'], 'iloc') else float(row['High'])
                low = float(row['Low'].iloc[0]) if hasattr(row['Low'], 'iloc') else float(row['Low'])
            except (KeyError, IndexError):
                continue

            # Check TP and SL hit for this candle
            if direction in ('buy', 'long'):
                tp_hit = high >= tp
                sl_hit = low <= sl
            else:  # sell/short
                tp_hit = low <= tp
                sl_hit = high >= sl

            if tp_hit and sl_hit:
                # Both levels touched in same candle — conservative: count as SL
                # (In reality we'd need tick data to know which hit first)
                outcome_price = sl
                pips = calculate_pips(symbol, entry, sl, direction)
                return {
                    'outcome': 'SL_HIT',
                    'outcome_price': outcome_price,
                    'outcome_time': str(candle_time),
                    'pips_result': round(pips, 1),
                    'note': 'Both TP and SL touched in same candle — counted as SL (conservative)'
                }
            elif tp_hit:
                outcome_price = tp
                pips = calculate_pips(symbol, entry, tp, direction)
                return {
                    'outcome': 'TP_HIT',
                    'outcome_price': outcome_price,
                    'outcome_time': str(candle_time),
                    'pips_result': round(pips, 1)
                }
            elif sl_hit:
                outcome_price = sl
                pips = calculate_pips(symbol, entry, sl, direction)
                return {
                    'outcome': 'SL_HIT',
                    'outcome_price': outcome_price,
                    'outcome_time': str(candle_time),
                    'pips_result': round(pips, 1)
                }

        # Neither TP nor SL hit
        hours_elapsed = (now - sig_dt).total_seconds() / 3600
        if hours_elapsed >= 48:
            # Expired — get last known price as exit
            try:
                last_close = float(data['Close'].iloc[-1]) if not data.empty else entry
                if hasattr(last_close, 'iloc'):
                    last_close = float(last_close.iloc[0])
            except Exception:
                last_close = entry
            pips = calculate_pips(symbol, entry, last_close, direction)
            return {
                'outcome': 'EXPIRED',
                'outcome_price': last_close,
                'outcome_time': str(data.index[-1]) if not data.empty else str(now),
                'pips_result': round(pips, 1),
                'note': 'Neither TP nor SL hit within 48 hours'
            }

        # Still pending — not enough time elapsed
        return None

    def resolve_all_pending(self) -> Dict:
        """Check outcomes for all pending signals in the DB."""
        if not self.db:
            return {'error': 'No database connection'}

        pending = self.db.get_pending_signals()
        results = {'checked': 0, 'resolved': 0, 'tp_hit': 0, 'sl_hit': 0, 'expired': 0, 'still_pending': 0}

        for signal in pending:
            results['checked'] += 1
            outcome = self.check_signal_outcome(signal)

            if outcome:
                self.db.update_signal_outcome(
                    signal_id=signal['id'],
                    outcome=outcome['outcome'],
                    outcome_price=outcome['outcome_price'],
                    outcome_time=outcome['outcome_time'],
                    pips_result=outcome['pips_result']
                )
                results['resolved'] += 1
                if outcome['outcome'] == 'TP_HIT':
                    results['tp_hit'] += 1
                elif outcome['outcome'] == 'SL_HIT':
                    results['sl_hit'] += 1
                elif outcome['outcome'] == 'EXPIRED':
                    results['expired'] += 1
                logger.info(
                    f"📓 {signal['symbol']} {signal['direction']} @ {signal['entry_price']:.5f} "
                    f"→ {outcome['outcome']} ({outcome['pips_result']:+.1f} pips)"
                )
            else:
                results['still_pending'] += 1

        return results

    def generate_weekly_report(self, week_offset: int = 0) -> Dict:
        """
        Generate weekly performance report.

        Args:
            week_offset: 0 = current week, -1 = last week, etc.
        """
        if not self.db:
            return {'error': 'No database connection'}

        # Calculate week boundaries (Mon-Fri)
        today = datetime.now(timezone.utc).date()
        # Find this week's Monday
        days_since_monday = today.weekday()
        week_monday = today - timedelta(days=days_since_monday) + timedelta(weeks=week_offset)
        week_friday = week_monday + timedelta(days=4)

        signals = self.db.get_signals_for_week(
            week_start=week_monday.isoformat(),
            week_end=week_friday.isoformat()
        )

        if not signals:
            return {
                'week': f"{week_monday} → {week_friday}",
                'total_signals': 0,
                'message': 'No signals this week'
            }

        # Aggregate stats
        total = len(signals)
        tp_hits = [s for s in signals if s.get('outcome') == 'TP_HIT']
        sl_hits = [s for s in signals if s.get('outcome') == 'SL_HIT']
        expired = [s for s in signals if s.get('outcome') == 'EXPIRED']
        pending = [s for s in signals if s.get('outcome') in ('PENDING', None)]

        total_pips = sum(s.get('pips_result', 0) or 0 for s in signals if s.get('outcome') != 'PENDING')
        win_pips = sum(s.get('pips_result', 0) or 0 for s in tp_hits)
        loss_pips = sum(abs(s.get('pips_result', 0) or 0) for s in sl_hits)

        decided = len(tp_hits) + len(sl_hits)
        win_rate = (len(tp_hits) / decided * 100) if decided > 0 else 0
        profit_factor = (win_pips / loss_pips) if loss_pips > 0 else float('inf') if win_pips > 0 else 0

        # By pair
        by_pair = {}
        for s in signals:
            sym = s['symbol']
            if sym not in by_pair:
                by_pair[sym] = {'total': 0, 'wins': 0, 'losses': 0, 'pips': 0, 'signals': []}
            by_pair[sym]['total'] += 1
            by_pair[sym]['signals'].append(s)
            if s.get('outcome') == 'TP_HIT':
                by_pair[sym]['wins'] += 1
            elif s.get('outcome') == 'SL_HIT':
                by_pair[sym]['losses'] += 1
            by_pair[sym]['pips'] += s.get('pips_result', 0) or 0

        # By setup type
        by_setup = {}
        for s in signals:
            setup = s.get('setup_type', 'Unknown')
            if setup not in by_setup:
                by_setup[setup] = {'total': 0, 'wins': 0, 'losses': 0, 'pips': 0}
            by_setup[setup]['total'] += 1
            if s.get('outcome') == 'TP_HIT':
                by_setup[setup]['wins'] += 1
            elif s.get('outcome') == 'SL_HIT':
                by_setup[setup]['losses'] += 1
            by_setup[setup]['pips'] += s.get('pips_result', 0) or 0

        # By day
        by_day = {}
        for s in signals:
            try:
                ts = s.get('timestamp', '')
                if isinstance(ts, str):
                    day = datetime.fromisoformat(ts.replace('Z', '+00:00')).strftime('%A')
                else:
                    day = 'Unknown'
            except Exception:
                day = 'Unknown'
            if day not in by_day:
                by_day[day] = {'total': 0, 'wins': 0, 'losses': 0, 'pips': 0}
            by_day[day]['total'] += 1
            if s.get('outcome') == 'TP_HIT':
                by_day[day]['wins'] += 1
            elif s.get('outcome') == 'SL_HIT':
                by_day[day]['losses'] += 1
            by_day[day]['pips'] += s.get('pips_result', 0) or 0

        # Best/worst signal
        resolved = [s for s in signals if s.get('pips_result') and s.get('outcome') != 'PENDING']
        best = max(resolved, key=lambda s: s.get('pips_result', 0)) if resolved else None
        worst = min(resolved, key=lambda s: s.get('pips_result', 0)) if resolved else None

        # Average R:R achieved vs planned
        avg_planned_rr = sum(s.get('risk_reward', 0) or 0 for s in signals) / total if total > 0 else 0

        return {
            'week': f"{week_monday} → {week_friday}",
            'week_start': week_monday.isoformat(),
            'week_end': week_friday.isoformat(),
            'total_signals': total,
            'tp_hits': len(tp_hits),
            'sl_hits': len(sl_hits),
            'expired': len(expired),
            'pending': len(pending),
            'win_rate': round(win_rate, 1),
            'total_pips': round(total_pips, 1),
            'win_pips': round(win_pips, 1),
            'loss_pips': round(loss_pips, 1),
            'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else 999,
            'avg_planned_rr': round(avg_planned_rr, 2),
            'by_pair': by_pair,
            'by_setup': by_setup,
            'by_day': by_day,
            'best_signal': {
                'symbol': best['symbol'],
                'direction': best['direction'],
                'pips': best.get('pips_result', 0),
                'setup': best.get('setup_type', ''),
            } if best else None,
            'worst_signal': {
                'symbol': worst['symbol'],
                'direction': worst['direction'],
                'pips': worst.get('pips_result', 0),
                'setup': worst.get('setup_type', ''),
            } if worst else None,
            'signals': signals,  # Full list for detailed view
        }

    def format_telegram_report(self, report: Dict) -> str:
        """Format weekly report for Telegram (HTML)."""
        if report.get('total_signals', 0) == 0:
            return (
                f"📓 <b>WEEKLY JOURNAL</b>\n"
                f"Week: {report['week']}\n\n"
                f"No signals generated this week."
            )

        lines = [
            f"📓 <b>WEEKLY TRADING JOURNAL</b>",
            f"📅 {report['week']}",
            "",
            "━━━━━━━━━━━━━━━━━━━━━",
        ]

        # Overall stats
        wr = report['win_rate']
        wr_emoji = "🟢" if wr >= 60 else "🟡" if wr >= 50 else "🔴"
        pips_emoji = "📈" if report['total_pips'] > 0 else "📉"

        lines.extend([
            "",
            f"📊 <b>Performance Summary</b>",
            f"• Signals: {report['total_signals']}",
            f"• ✅ TP Hit: {report['tp_hits']} | ❌ SL Hit: {report['sl_hits']}",
        ])
        if report['expired'] > 0:
            lines.append(f"• ⏰ Expired: {report['expired']}")
        if report['pending'] > 0:
            lines.append(f"• ⏳ Pending: {report['pending']}")
        lines.extend([
            f"• {wr_emoji} Win Rate: {wr:.1f}%",
            f"• {pips_emoji} Net Pips: {report['total_pips']:+.1f}",
            f"• 💰 Win Pips: +{report['win_pips']:.1f} | Loss Pips: -{report['loss_pips']:.1f}",
            f"• ⚖️ Profit Factor: {report['profit_factor']:.2f}",
            f"• 🎯 Avg Planned R:R: 1:{report['avg_planned_rr']:.1f}",
        ])

        # By pair
        if report.get('by_pair'):
            lines.extend(["", "💱 <b>By Pair</b>"])
            for pair, data in report['by_pair'].items():
                decided = data['wins'] + data['losses']
                pair_wr = (data['wins'] / decided * 100) if decided > 0 else 0
                emoji = "🟢" if pair_wr >= 60 else "🟡" if pair_wr >= 50 else "🔴"
                lines.append(
                    f"{emoji} {pair}: {data['wins']}W/{data['losses']}L "
                    f"({pair_wr:.0f}%) {data['pips']:+.1f} pips"
                )

        # By setup type
        if report.get('by_setup'):
            lines.extend(["", "🔧 <b>By Setup</b>"])
            for setup, data in report['by_setup'].items():
                decided = data['wins'] + data['losses']
                setup_wr = (data['wins'] / decided * 100) if decided > 0 else 0
                lines.append(
                    f"• {setup}: {data['wins']}W/{data['losses']}L "
                    f"({setup_wr:.0f}%) {data['pips']:+.1f} pips"
                )

        # By day
        if report.get('by_day'):
            day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
            lines.extend(["", "📅 <b>By Day</b>"])
            for day in day_order:
                if day in report['by_day']:
                    data = report['by_day'][day]
                    decided = data['wins'] + data['losses']
                    day_wr = (data['wins'] / decided * 100) if decided > 0 else 0
                    lines.append(
                        f"• {day}: {data['total']} signals, "
                        f"{day_wr:.0f}% WR, {data['pips']:+.1f} pips"
                    )

        # Best/worst
        lines.append("")
        if report.get('best_signal'):
            b = report['best_signal']
            lines.append(f"🏆 Best: {b['symbol']} {b['direction']} ({b['setup']}) → {b['pips']:+.1f} pips")
        if report.get('worst_signal'):
            w = report['worst_signal']
            lines.append(f"💀 Worst: {w['symbol']} {w['direction']} ({w['setup']}) → {w['pips']:+.1f} pips")

        # Signal detail list
        resolved_signals = [s for s in report.get('signals', []) if s.get('outcome') != 'PENDING']
        if resolved_signals:
            lines.extend(["", "━━━━━━━━━━━━━━━━━━━━━", "", "📝 <b>Signal Details</b>"])
            for s in resolved_signals:
                outcome = s.get('outcome', 'PENDING')
                pips = s.get('pips_result', 0) or 0
                emoji = "✅" if outcome == 'TP_HIT' else "❌" if outcome == 'SL_HIT' else "⏰"
                try:
                    ts = s.get('timestamp', '')
                    if isinstance(ts, str):
                        ts_short = datetime.fromisoformat(ts.replace('Z', '+00:00')).strftime('%a %H:%M')
                    else:
                        ts_short = str(ts)[:16]
                except Exception:
                    ts_short = '?'
                lines.append(
                    f"{emoji} {ts_short} {s['symbol']} {s['direction']} "
                    f"{s.get('setup_type', '')} → {pips:+.1f}p"
                )

        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━━━━",
            f"<i>Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</i>"
        ])

        return "\n".join(lines)


# Singleton
_journal: Optional[SignalJournal] = None


def get_signal_journal(db=None) -> SignalJournal:
    """Get or create signal journal instance."""
    global _journal
    if _journal is None or (db is not None and _journal.db is None):
        _journal = SignalJournal(db=db)
    return _journal
