"""
Weekly Review Report
Sends comprehensive performance analysis every Friday/Sunday
Reads verified trade outcomes from active_signals.json
"""

import json
import logging
import os
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / 'data'
WEEKLY_ARCHIVE_DIR = DATA_DIR / 'weekly_reports'


class WeeklyReporter:
    """Generate and send weekly performance reviews from active_signals.json."""
    
    def __init__(self):
        WEEKLY_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        self.signals = self._load_signals()
    
    def _load_signals(self) -> Dict:
        """Load all signals from active_signals.json."""
        sig_file = DATA_DIR / 'active_signals.json'
        try:
            if sig_file.exists():
                with open(sig_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading active_signals.json: {e}")
        return {}
    
    def _get_week_range(self, week_offset: int = 0) -> tuple:
        """Get Monday-Friday range for a given week offset (0=current, -1=last)."""
        today = datetime.utcnow().date()
        # Find this week's Monday
        monday = today - timedelta(days=today.weekday())
        # Apply offset
        monday = monday + timedelta(weeks=week_offset)
        friday = monday + timedelta(days=4)
        sunday = monday + timedelta(days=6)
        return monday, friday, sunday
    
    def _get_week_signals(self, week_offset: int = 0) -> List[Dict]:
        """Get all signals from a specific week."""
        monday, friday, sunday = self._get_week_range(week_offset)
        
        week_sigs = []
        for sig_id, sig in self.signals.items():
            det = sig.get('detected_at', '')
            if not det:
                continue
            try:
                sig_date = datetime.fromisoformat(det.replace('Z', '+00:00')).date()
            except (ValueError, TypeError):
                continue
            
            if monday <= sig_date <= sunday:
                sig['_sig_id'] = sig_id
                week_sigs.append(sig)
        
        return week_sigs
    
    def get_weekly_stats(self, week_offset: int = 0) -> Dict[str, Any]:
        """Calculate comprehensive weekly statistics."""
        monday, friday, sunday = self._get_week_range(week_offset)
        week_sigs = self._get_week_signals(week_offset)
        
        wins = [s for s in week_sigs if s.get('status') == 'win']
        losses = [s for s in week_sigs if s.get('status') == 'loss']
        expired = [s for s in week_sigs if s.get('status') == 'expired']
        pending = [s for s in week_sigs if s.get('status') in ('pending', 'active')]
        resolved = wins + losses
        
        # R calculations
        total_r = sum(s.get('rr_achieved', 0) for s in resolved)
        win_r = sum(s.get('rr_achieved', 0) for s in wins)
        loss_r = sum(abs(s.get('rr_achieved', 0)) for s in losses)
        
        # Pips
        total_pips_forex = 0
        total_pips_gold = 0
        for s in resolved:
            pips = s.get('pips_result', 0) or 0
            pair = str(s.get('symbol', s.get('pair', '')))
            if 'XAU' in pair:
                total_pips_gold += pips
            else:
                total_pips_forex += pips
        
        # By pair
        by_pair = defaultdict(lambda: {'wins': 0, 'losses': 0, 'expired': 0, 'r': 0, 'pips': 0, 'trades': []})
        for s in week_sigs:
            pair = str(s.get('symbol', s.get('pair', 'Unknown')))
            status = s.get('status', '')
            if status == 'win':
                by_pair[pair]['wins'] += 1
            elif status == 'loss':
                by_pair[pair]['losses'] += 1
            elif status == 'expired':
                by_pair[pair]['expired'] += 1
            by_pair[pair]['r'] += s.get('rr_achieved', 0) or 0
            by_pair[pair]['pips'] += s.get('pips_result', 0) or 0
            by_pair[pair]['trades'].append(s)
        
        # By setup type
        by_setup = defaultdict(lambda: {'wins': 0, 'losses': 0, 'r': 0})
        for s in resolved:
            setup = s.get('setup_type', 'Unknown')
            if s.get('status') == 'win':
                by_setup[setup]['wins'] += 1
            else:
                by_setup[setup]['losses'] += 1
            by_setup[setup]['r'] += s.get('rr_achieved', 0) or 0
        
        # By day
        by_day = defaultdict(lambda: {'wins': 0, 'losses': 0, 'expired': 0, 'r': 0})
        for s in week_sigs:
            det = s.get('detected_at', '')
            try:
                sig_date = datetime.fromisoformat(det.replace('Z', '+00:00'))
                day_name = sig_date.strftime('%A')
                day_key = sig_date.strftime('%a %m/%d')
            except (ValueError, TypeError):
                day_key = 'Unknown'
            
            status = s.get('status', '')
            if status == 'win':
                by_day[day_key]['wins'] += 1
            elif status == 'loss':
                by_day[day_key]['losses'] += 1
            elif status == 'expired':
                by_day[day_key]['expired'] += 1
            by_day[day_key]['r'] += s.get('rr_achieved', 0) or 0
        
        # Equity curve (cumulative R by trade)
        equity = []
        cumulative_r = 0
        for s in sorted(resolved, key=lambda x: x.get('detected_at', '')):
            cumulative_r += s.get('rr_achieved', 0) or 0
            equity.append(round(cumulative_r, 1))
        
        # Streaks
        best_streak = 0
        worst_streak = 0
        current_w = 0
        current_l = 0
        for s in sorted(resolved, key=lambda x: x.get('detected_at', '')):
            if s.get('status') == 'win':
                current_w += 1
                current_l = 0
                best_streak = max(best_streak, current_w)
            else:
                current_l += 1
                current_w = 0
                worst_streak = max(worst_streak, current_l)
        
        return {
            'week_start': monday.isoformat(),
            'week_end': friday.isoformat(),
            'total_signals': len(week_sigs),
            'wins': len(wins),
            'losses': len(losses),
            'expired': len(expired),
            'pending': len(pending),
            'win_rate': len(wins) / len(resolved) * 100 if resolved else 0,
            'total_r': total_r,
            'win_r': win_r,
            'loss_r': loss_r,
            'profit_factor': win_r / loss_r if loss_r > 0 else float('inf') if win_r > 0 else 0,
            'total_pips_forex': total_pips_forex,
            'total_pips_gold': total_pips_gold,
            'by_pair': dict(by_pair),
            'by_setup': dict(by_setup),
            'by_day': dict(by_day),
            'equity_curve': equity,
            'best_win_streak': best_streak,
            'worst_loss_streak': worst_streak,
        }
    
    def format_telegram_report(self, week_offset: int = 0) -> str:
        """Format weekly stats as a Telegram message."""
        stats = self.get_weekly_stats(week_offset)
        
        # Determine if profitable
        total_r = stats['total_r']
        r_emoji = "🟢" if total_r > 0 else "🔴" if total_r < 0 else "⚪"
        target_hit = "✅" if stats['win_rate'] >= 60 else "⚠️"
        
        lines = [
            f"📊 <b>WEEKLY PERFORMANCE REPORT</b>",
            f"📅 {stats['week_start']} → {stats['week_end']}",
            "",
            "━━━━━━━━━━━━━━━━━━━━━",
            "",
            f"{r_emoji} <b>WEEK RESULT: {total_r:+.1f}R</b>",
            f"📈 Record: {stats['wins']}W / {stats['losses']}L / {stats['expired']}E",
            f"{target_hit} Win Rate: {stats['win_rate']:.0f}% (target: 60%)",
            f"📊 Profit Factor: {stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "📊 Profit Factor: ∞",
        ]
        
        # Pips breakdown
        if stats['total_pips_forex'] or stats['total_pips_gold']:
            lines.append(f"💰 Forex Pips: {stats['total_pips_forex']:+.1f} | Gold: ${stats['total_pips_gold']:+.0f}")
        
        if stats['best_win_streak'] or stats['worst_loss_streak']:
            lines.append(f"🔥 Best Streak: {stats['best_win_streak']}W | Worst: {stats['worst_loss_streak']}L")
        
        # By Pair
        if stats['by_pair']:
            lines.extend(["", "━━━━━━━━━━━━━━━━━━━━━", "", "💱 <b>BY PAIR</b>"])
            for pair, data in sorted(stats['by_pair'].items(), key=lambda x: x[1].get('r', 0), reverse=True):
                display = pair.replace('_', '/')
                total = data['wins'] + data['losses']
                wr = data['wins'] / total * 100 if total > 0 else 0
                p_emoji = "🟢" if data['r'] > 0 else "🔴" if data['r'] < 0 else "⚪"
                exp_str = f" / {data['expired']}E" if data.get('expired', 0) > 0 else ""
                lines.append(f"{p_emoji} <b>{display}</b>: {data['wins']}W/{data['losses']}L{exp_str} | {data['r']:+.1f}R | {wr:.0f}% WR")
        
        # By Setup
        if stats['by_setup']:
            lines.extend(["", "━━━━━━━━━━━━━━━━━━━━━", "", "🔧 <b>BY SETUP TYPE</b>"])
            for setup, data in sorted(stats['by_setup'].items(), key=lambda x: x[1].get('r', 0), reverse=True):
                total = data['wins'] + data['losses']
                wr = data['wins'] / total * 100 if total > 0 else 0
                s_emoji = "✅" if data['r'] > 0 else "❌"
                lines.append(f"{s_emoji} {setup}: {data['wins']}W/{data['losses']}L | {data['r']:+.1f}R | {wr:.0f}% WR")
        
        # By Day
        if stats['by_day']:
            lines.extend(["", "━━━━━━━━━━━━━━━━━━━━━", "", "📅 <b>BY DAY</b>"])
            for day, data in sorted(stats['by_day'].items()):
                total = data['wins'] + data['losses']
                wr = data['wins'] / total * 100 if total > 0 else 0
                d_emoji = "🟢" if data['r'] > 0 else "🔴" if data['r'] < 0 else "⚪"
                exp_str = f" / {data['expired']}E" if data.get('expired', 0) > 0 else ""
                lines.append(f"{d_emoji} {day}: {data['wins']}W/{data['losses']}L{exp_str} | {data['r']:+.1f}R | {wr:.0f}% WR")
        
        # Equity curve (text sparkline)
        if stats['equity_curve']:
            eq = stats['equity_curve']
            lines.extend(["", "━━━━━━━━━━━━━━━━━━━━━", "", "📈 <b>EQUITY CURVE (cumulative R)</b>"])
            # Simple text sparkline
            if len(eq) > 1:
                min_r = min(eq)
                max_r = max(eq)
                blocks = "▁▂▃▄▅▆▇█"
                r_range = max_r - min_r if max_r != min_r else 1
                sparkline = ""
                for val in eq:
                    idx = int((val - min_r) / r_range * (len(blocks) - 1))
                    sparkline += blocks[idx]
                lines.append(f"   {sparkline}")
                lines.append(f"   Start: 0R → End: {eq[-1]:+.1f}R (Peak: {max_r:+.1f}R, Trough: {min_r:+.1f}R)")
        
        # Insights
        lines.extend(["", "━━━━━━━━━━━━━━━━━━━━━", "", "🎯 <b>INSIGHTS</b>"])
        
        # Best pair
        if stats['by_pair']:
            best_pair = max(stats['by_pair'].items(), key=lambda x: x[1].get('r', 0))
            worst_pair = min(stats['by_pair'].items(), key=lambda x: x[1].get('r', 0))
            lines.append(f"✅ Best: {best_pair[0].replace('_', '/')} ({best_pair[1]['r']:+.1f}R)")
            if worst_pair[0] != best_pair[0] and worst_pair[1]['r'] < 0:
                lines.append(f"⚠️ Worst: {worst_pair[0].replace('_', '/')} ({worst_pair[1]['r']:+.1f}R)")
        
        # Best setup
        if stats['by_setup']:
            best_setup = max(stats['by_setup'].items(), key=lambda x: x[1].get('r', 0))
            lines.append(f"🏆 Best Setup: {best_setup[0]} ({best_setup[1]['r']:+.1f}R)")
        
        # Win rate assessment
        if stats['win_rate'] >= 60:
            lines.append(f"✅ Target win rate (60%) ACHIEVED at {stats['win_rate']:.0f}%!")
        elif stats['win_rate'] >= 50:
            lines.append(f"📊 Win rate {stats['win_rate']:.0f}% — close to 60% target")
        else:
            lines.append(f"📊 Win rate {stats['win_rate']:.0f}% — below 60% target, review losers")
        
        lines.extend([
            "",
            f"<i>Jarvis ICT/SMC | Dynamic TP | Entry Fill Verified</i>",
            f"<i>Report: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</i>"
        ])
        
        return "\n".join(lines)
    
    def save_weekly_archive(self, week_offset: int = 0):
        """Save weekly report to archive."""
        stats = self.get_weekly_stats(week_offset)
        # Remove non-serializable items
        for pair in stats.get('by_pair', {}).values():
            pair.pop('trades', None)
        
        filename = f"weekly_{stats['week_start']}_{stats['week_end']}.json"
        archive_path = WEEKLY_ARCHIVE_DIR / filename
        
        try:
            with open(archive_path, 'w') as f:
                json.dump(stats, f, indent=2, default=str)
            logger.info(f"Weekly report archived to {archive_path}")
            return True
        except Exception as e:
            logger.error(f"Error archiving weekly report: {e}")
            return False


# Singleton
_weekly_reporter: Optional[WeeklyReporter] = None


def get_weekly_reporter() -> WeeklyReporter:
    """Get weekly reporter instance (re-creates to reload data)."""
    global _weekly_reporter
    # Always recreate to get fresh data from active_signals.json
    _weekly_reporter = WeeklyReporter()
    return _weekly_reporter


def should_send_weekly_report() -> bool:
    """Check if it's Friday after session close or Sunday."""
    now = datetime.utcnow()
    # Friday after 17:00 UTC or Sunday at 17:00 UTC
    if now.weekday() == 4 and now.hour >= 17 and now.minute < 30:
        return True
    if now.weekday() == 6 and now.hour == 17 and now.minute < 5:
        return True
    return False


if __name__ == "__main__":
    # Test the weekly reporter
    reporter = WeeklyReporter()
    print(reporter.format_telegram_report())
