"""
Weekly Review Report
Sends comprehensive performance analysis every Sunday
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / 'data'
WEEKLY_ARCHIVE_DIR = DATA_DIR / 'weekly_reports'


class WeeklyReporter:
    """Generate and send weekly performance reviews."""
    
    def __init__(self):
        WEEKLY_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        self.trade_history = self._load_trade_history()
        self.daily_archives = self._load_daily_archives()
    
    def _load_trade_history(self) -> List[Dict]:
        """Load trade history."""
        history_file = DATA_DIR / 'trade_history.json'
        try:
            if history_file.exists():
                with open(history_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading trade history: {e}")
        return []
    
    def _load_daily_archives(self) -> List[Dict]:
        """Load all daily report archives from this week."""
        archives = []
        today = datetime.utcnow().date()
        week_start = today - timedelta(days=today.weekday() + 1)  # Last Sunday
        
        for i in range(7):
            day = week_start + timedelta(days=i)
            archive_file = DATA_DIR / f'report_{day.isoformat()}.json'
            if archive_file.exists():
                try:
                    with open(archive_file, 'r') as f:
                        data = json.load(f)
                        data['date'] = day.isoformat()
                        archives.append(data)
                except Exception as e:
                    logger.error(f"Error loading archive {archive_file}: {e}")
        
        return archives
    
    def get_weekly_stats(self) -> Dict[str, Any]:
        """Calculate weekly statistics."""
        # Get trades from this week
        today = datetime.utcnow()
        week_start = today - timedelta(days=today.weekday() + 1)  # Last Sunday
        
        weekly_trades = [
            t for t in self.trade_history
            if self._parse_date(t.get('exit_time', t.get('entry_time', ''))) >= week_start
        ]
        
        # Count from daily archives
        total_signals = 0
        total_rejections = 0
        rejection_reasons = {}
        
        for archive in self.daily_archives:
            total_signals += archive.get('signals_generated', 0)
            rejections = archive.get('rejections', {})
            total_rejections += sum(rejections.values())
            for reason, count in rejections.items():
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + count
        
        # Trade performance
        wins = [t for t in weekly_trades if t.get('status') == 'win']
        losses = [t for t in weekly_trades if t.get('status') == 'loss']
        
        win_pips = sum(t.get('pips_result', 0) for t in wins)
        loss_pips = sum(abs(t.get('pips_result', 0)) for t in losses)
        total_pips = sum(t.get('pips_result', 0) for t in weekly_trades)
        
        # By pair analysis
        by_pair = {}
        for trade in weekly_trades:
            symbol = trade.get('symbol', 'Unknown')
            if symbol not in by_pair:
                by_pair[symbol] = {'trades': 0, 'wins': 0, 'pips': 0}
            by_pair[symbol]['trades'] += 1
            if trade.get('status') == 'win':
                by_pair[symbol]['wins'] += 1
            by_pair[symbol]['pips'] += trade.get('pips_result', 0)
        
        # By day analysis
        by_day = {}
        for trade in weekly_trades:
            day = self._parse_date(trade.get('entry_time', '')).strftime('%A')
            if day not in by_day:
                by_day[day] = {'trades': 0, 'wins': 0}
            by_day[day]['trades'] += 1
            if trade.get('status') == 'win':
                by_day[day]['wins'] += 1
        
        # Best and worst setups
        by_setup = {}
        for trade in weekly_trades:
            setup = trade.get('setup_type', 'Unknown')
            if setup not in by_setup:
                by_setup[setup] = {'trades': 0, 'wins': 0, 'pips': 0}
            by_setup[setup]['trades'] += 1
            if trade.get('status') == 'win':
                by_setup[setup]['wins'] += 1
            by_setup[setup]['pips'] += trade.get('pips_result', 0)
        
        return {
            'week_start': week_start.strftime('%Y-%m-%d'),
            'week_end': today.strftime('%Y-%m-%d'),
            'total_trades': len(weekly_trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / len(weekly_trades) * 100 if weekly_trades else 0,
            'total_pips': total_pips,
            'win_pips': win_pips,
            'loss_pips': loss_pips,
            'profit_factor': win_pips / loss_pips if loss_pips > 0 else 0,
            'signals_generated': total_signals,
            'rejections': total_rejections,
            'top_rejection_reasons': dict(sorted(rejection_reasons.items(), key=lambda x: x[1], reverse=True)[:5]),
            'by_pair': by_pair,
            'by_day': by_day,
            'by_setup': by_setup,
            'best_pair': max(by_pair.items(), key=lambda x: x[1]['pips'])[0] if by_pair else None,
            'worst_pair': min(by_pair.items(), key=lambda x: x[1]['pips'])[0] if by_pair else None,
            'best_day': max(by_day.items(), key=lambda x: x[1].get('wins', 0) / max(x[1].get('trades', 1), 1))[0] if by_day else None
        }
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime."""
        try:
            if not date_str:
                return datetime.min
            return datetime.fromisoformat(date_str.replace('Z', '+00:00').replace('+00:00', ''))
        except:
            return datetime.min
    
    def format_telegram_report(self) -> str:
        """Format weekly stats for Telegram."""
        stats = self.get_weekly_stats()
        
        # Header
        lines = [
            f"📊 *WEEKLY PERFORMANCE REVIEW*",
            f"Week: {stats['week_start']} → {stats['week_end']}",
            "",
            "━━━━━━━━━━━━━━━━━━━━━"
        ]
        
        # Overall Performance
        lines.extend([
            "",
            "📈 *Overall Performance*",
            f"• Trades: {stats['total_trades']}",
            f"• Wins: {stats['wins']} | Losses: {stats['losses']}",
            f"• Win Rate: {stats['win_rate']:.1f}%",
            f"• Total Pips: {stats['total_pips']:+.1f}",
            f"• Profit Factor: {stats['profit_factor']:.2f}",
        ])
        
        # Signals/Rejections
        lines.extend([
            "",
            "🔍 *Signal Analysis*",
            f"• Signals Generated: {stats['signals_generated']}",
            f"• Rejections: {stats['rejections']}",
        ])
        
        if stats.get('top_rejection_reasons'):
            lines.append("• Top Rejection Reasons:")
            for reason, count in list(stats['top_rejection_reasons'].items())[:3]:
                short_reason = reason[:40] + "..." if len(reason) > 40 else reason
                lines.append(f"  - {short_reason} ({count})")
        
        # By Pair
        if stats.get('by_pair'):
            lines.extend([
                "",
                "💱 *Performance by Pair*"
            ])
            for pair, data in stats['by_pair'].items():
                wr = data['wins'] / data['trades'] * 100 if data['trades'] > 0 else 0
                emoji = "🟢" if wr >= 60 else "🟡" if wr >= 50 else "🔴"
                lines.append(f"{emoji} {pair}: {wr:.0f}% WR ({data['trades']} trades, {data['pips']:+.1f} pips)")
        
        # By Day
        if stats.get('by_day'):
            lines.extend([
                "",
                "📅 *Performance by Day*"
            ])
            for day, data in stats['by_day'].items():
                wr = data['wins'] / data['trades'] * 100 if data['trades'] > 0 else 0
                lines.append(f"• {day}: {wr:.0f}% WR ({data['trades']} trades)")
        
        # Insights
        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━━━━",
            "",
            "🎯 *Insights*"
        ])
        
        if stats.get('best_pair'):
            lines.append(f"✅ Best Pair: {stats['best_pair']}")
        if stats.get('worst_pair') and stats['worst_pair'] != stats.get('best_pair'):
            lines.append(f"⚠️ Worst Pair: {stats['worst_pair']}")
        if stats.get('best_day'):
            lines.append(f"📈 Best Day: {stats['best_day']}")
        
        # Target check
        target_wr = 60.0
        if stats['win_rate'] >= target_wr:
            lines.append(f"✅ Target win rate ({target_wr}%) ACHIEVED!")
        else:
            diff = target_wr - stats['win_rate']
            lines.append(f"📊 {diff:.1f}% below target win rate")
        
        lines.extend([
            "",
            "_Report generated: " + datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC') + "_"
        ])
        
        return "\n".join(lines)
    
    def save_weekly_archive(self):
        """Save weekly report to archive."""
        stats = self.get_weekly_stats()
        filename = f"weekly_{stats['week_start']}_{stats['week_end']}.json"
        archive_path = WEEKLY_ARCHIVE_DIR / filename
        
        try:
            with open(archive_path, 'w') as f:
                json.dump(stats, f, indent=2)
            logger.info(f"Weekly report archived to {archive_path}")
            return True
        except Exception as e:
            logger.error(f"Error archiving weekly report: {e}")
            return False


# Singleton
_weekly_reporter: Optional[WeeklyReporter] = None


def get_weekly_reporter() -> WeeklyReporter:
    """Get weekly reporter instance."""
    global _weekly_reporter
    if _weekly_reporter is None:
        _weekly_reporter = WeeklyReporter()
    return _weekly_reporter


def should_send_weekly_report() -> bool:
    """Check if it's Sunday and time to send weekly report (17:00 UTC)."""
    now = datetime.utcnow()
    return now.weekday() == 6 and now.hour == 17 and now.minute < 5


if __name__ == "__main__":
    # Test the weekly reporter
    reporter = WeeklyReporter()
    print(reporter.format_telegram_report())
