"""
Telegram Bot Integration for Forex Trading Bot
Sends real-time alerts for signals, trade updates, and system status.
"""

import os
import requests
import logging
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send trading alerts to Telegram."""
    
    def __init__(self, bot_token: str = None, chat_id: str = None):
        """
        Initialize Telegram notifier.
        
        Args:
            bot_token: Telegram bot token from BotFather
            chat_id: Your Telegram chat ID (or channel ID)
        """
        self.bot_token = bot_token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
        self.enabled = bool(self.bot_token and self.chat_id)
        
        if not self.enabled:
            logger.warning("Telegram notifications disabled - missing bot token or chat ID")
    
    def send_message(self, text: str, parse_mode: str = "HTML", disable_notification: bool = False) -> bool:
        """
        Send a message to Telegram.
        
        Args:
            text: Message text (supports HTML formatting)
            parse_mode: "HTML" or "Markdown"
            disable_notification: If True, send silently
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            logger.debug(f"Telegram disabled, would send: {text[:100]}...")
            return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_notification": disable_notification
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info("✅ Telegram message sent")
                return True
            else:
                logger.error(f"Telegram error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False
    
    def notify_signal(self, signal: Dict[str, Any], symbol: str) -> bool:
        """
        Send a trading signal notification.
        
        Args:
            signal: Signal dictionary with direction, entry, sl, tp, etc.
            symbol: Trading pair (e.g., "EUR_USD")
        """
        direction = signal.get('direction', signal.get('type', 'UNKNOWN'))
        entry = signal.get('entry_price', signal.get('entry', 0))
        sl = signal.get('stop_loss', 0)
        tp = signal.get('take_profit', 0)
        rr = signal.get('risk_reward', 0)
        setup = signal.get('setup_type', 'ICT Setup')
        confidence = signal.get('confidence', 0) * 100
        
        # ML Risk info
        ml_confidence = signal.get('ml_confidence')
        ml_recommendation = signal.get('ml_recommendation', '')
        ml_reasoning = signal.get('ml_reasoning', [])
        
        # Direction emoji
        if direction == "BUY":
            emoji = "🟢"
        elif direction == "SELL":
            emoji = "🔴"
        else:
            emoji = "⚪"
        
        # Format symbol nicely
        pair = symbol.replace('_', '/')
        
        # Price note for Gold
        price_note = ""
        if 'XAU' in symbol:
            price_note = "\n\n⚠️ <i>Futures price - spot ~$30-40 lower</i>"
        
        # ML section
        ml_section = ""
        if ml_confidence is not None:
            if ml_recommendation == 'full_risk':
                risk_emoji = "🟢"
            elif 'half' in ml_recommendation or 'quarter' in ml_recommendation:
                risk_emoji = "🟡"
            else:
                risk_emoji = "🔴"
            ml_section = f"\n\n🤖 <b>ML Score:</b> {ml_confidence}% {risk_emoji}\n📊 <b>Risk:</b> {ml_recommendation.replace('_', ' ').title()}"
            if ml_reasoning:
                ml_section += "\n" + "\n".join(ml_reasoning[:3])
        
        message = f"""
{emoji} <b>NEW SIGNAL: {pair}</b>

📊 <b>Setup:</b> {setup}
📈 <b>Direction:</b> {direction}

💰 <b>Entry:</b> <code>{entry:.5f}</code>
🛑 <b>Stop Loss:</b> <code>{sl:.5f}</code>
🎯 <b>Take Profit:</b> <code>{tp:.5f}</code>

⚖️ <b>Risk/Reward:</b> 1:{rr:.1f}
🎲 <b>Confidence:</b> {confidence:.0f}%{ml_section}{price_note}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC
"""
        return self.send_message(message.strip())
    
    def notify_trade_update(self, symbol: str, status: str, pnl: float = None) -> bool:
        """
        Notify about trade status change.
        
        Args:
            symbol: Trading pair
            status: "executed", "stopped_out", "take_profit", "cancelled"
            pnl: Profit/loss in points (optional)
        """
        pair = symbol.replace('_', '/')
        
        status_emoji = {
            'executed': '✅',
            'stopped_out': '❌',
            'take_profit': '💰',
            'cancelled': '⚪',
            'breakeven': '➖'
        }
        
        emoji = status_emoji.get(status, '📢')
        
        pnl_text = ""
        if pnl is not None:
            if pnl > 0:
                pnl_emoji = "🟢"
            elif pnl < 0:
                pnl_emoji = "🔴"
            else:
                pnl_emoji = "⚪"
            pnl_text = f"\n💵 <b>P&L:</b> {pnl_emoji} {pnl:+.1f} points"
        
        message = f"""
{emoji} <b>TRADE UPDATE: {pair}</b>

📋 <b>Status:</b> {status.upper()}{pnl_text}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC
"""
        return self.send_message(message.strip())
    
    def notify_system_status(self, status: str, details: str = "") -> bool:
        """
        Send system status notification.
        
        Args:
            status: "online", "offline", "error", "warning"
            details: Additional details
        """
        status_emoji = {
            'online': '🟢',
            'offline': '🔴',
            'error': '⚠️',
            'warning': '🟡',
            'startup': '🚀'
        }
        
        emoji = status_emoji.get(status, '📢')
        
        message = f"""
{emoji} <b>SYSTEM: {status.upper()}</b>

{details if details else 'Trading bot status update'}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC
"""
        return self.send_message(message.strip())
    
    def notify_daily_summary(self, trades: int, wins: int, pnl: float, pairs_tracked: list) -> bool:
        """
        Send daily trading summary.
        
        Args:
            trades: Total trades today
            wins: Winning trades
            pnl: Total P&L in points
            pairs_tracked: List of pairs being tracked
        """
        win_rate = (wins / trades * 100) if trades > 0 else 0
        
        if pnl > 0:
            pnl_emoji = "🟢"
        elif pnl < 0:
            pnl_emoji = "🔴"
        else:
            pnl_emoji = "⚪"
        
        message = f"""
📊 <b>DAILY SUMMARY</b>

📈 <b>Trades:</b> {trades}
✅ <b>Wins:</b> {wins} ({win_rate:.1f}%)
💵 <b>P&L:</b> {pnl_emoji} {pnl:+.1f} points

🔍 <b>Tracking:</b> {', '.join(pairs_tracked)}

⏰ {datetime.now().strftime('%Y-%m-%d')} End of Day
"""
        return self.send_message(message.strip())
    
    def send_daily_report(self, report_data: Dict[str, Any]) -> bool:
        """
        Send comprehensive daily trading report with verified trade outcomes.
        
        Args:
            report_data: Dictionary containing:
                - signals_generated: list of signals
                - rejections_summary: dict of rejection reasons
                - trade_outcomes: list of resolved trades
                - session_stats: session activity
        """
        date_str = datetime.now().strftime('%Y-%m-%d')
        day_name = datetime.now().strftime('%A')
        
        # --- Load trade outcomes from active_signals.json ---
        outcomes = report_data.get('trade_outcomes', [])
        if not outcomes:
            try:
                import json as _json
                from pathlib import Path as _Path
                sig_file = _Path(__file__).parent.parent / 'data' / 'active_signals.json'
                if sig_file.exists():
                    with open(sig_file) as _f:
                        all_sigs = _json.load(_f)
                    for sid, sig in all_sigs.items():
                        det = sig.get('detected_at', '')
                        if date_str in det:
                            outcomes.append(sig)
            except Exception:
                pass
        
        wins = [t for t in outcomes if t.get('status') == 'win']
        losses = [t for t in outcomes if t.get('status') == 'loss']
        expired = [t for t in outcomes if t.get('status') == 'expired']
        pending = [t for t in outcomes if t.get('status') in ('pending', 'active')]
        resolved = wins + losses
        
        total_r = sum(t.get('rr_achieved', 0) for t in wins) + sum(t.get('rr_achieved', 0) for t in losses)
        win_r = sum(t.get('rr_achieved', 0) for t in wins)
        win_rate = len(wins) / len(resolved) * 100 if resolved else 0
        
        # Header
        r_emoji = "🟢" if total_r > 0 else "🔴" if total_r < 0 else "⚪"
        message = f"""📋 <b>END OF DAY REPORT</b>
📅 {date_str} | {day_name}

{r_emoji} <b>Day Result: {total_r:+.1f}R</b> ({len(wins)}W / {len(losses)}L"""
        
        if expired:
            message += f" / {len(expired)}E"
        if pending:
            message += f" / {len(pending)}P"
        message += f""")
🎯 Win Rate: {win_rate:.0f}%

{'='*30}
"""
        
        # --- TRADE OUTCOMES (the main event) ---
        if resolved or expired:
            message += "\n📊 <b>TRADE OUTCOMES</b>\n"
            
            for t in sorted(outcomes, key=lambda x: x.get('detected_at', '')):
                status = t.get('status', '?')
                if status not in ('win', 'loss', 'expired'):
                    continue
                    
                pair = str(t.get('symbol', t.get('pair', '?'))).replace('_', '/')
                direction = t.get('direction', '?')
                entry = t.get('entry_price', 0)
                pips = t.get('pips_result', 0)
                rr = t.get('rr_achieved', 0)
                setup = t.get('setup_type', '?')
                filled = t.get('entry_filled', True)
                
                if status == 'win':
                    icon = "✅"
                    pips_str = f"+{pips:.1f} pips" if isinstance(pips, (int, float)) else str(pips)
                    rr_str = f"+{rr:.1f}R"
                elif status == 'loss':
                    icon = "❌"
                    pips_str = f"{pips:.1f} pips" if isinstance(pips, (int, float)) else str(pips)
                    rr_str = f"{rr:.1f}R"
                else:  # expired
                    icon = "🚫"
                    pips_str = "not filled"
                    rr_str = "0R"
                
                dir_arrow = "⬇️" if direction == 'short' else "⬆️"
                message += f"\n{icon} <b>{pair}</b> {dir_arrow} {direction}\n"
                message += f"   {setup} | {pips_str} | {rr_str}\n"
            
            if pending:
                message += f"\n⏳ <b>{len(pending)} trade(s) still pending</b>\n"
        
        # --- BY PAIR SUMMARY ---
        pair_stats = {}
        for t in resolved:
            p = str(t.get('symbol', t.get('pair', 'Unknown')))
            if p not in pair_stats:
                pair_stats[p] = {'wins': 0, 'losses': 0, 'r': 0}
            if t.get('status') == 'win':
                pair_stats[p]['wins'] += 1
            else:
                pair_stats[p]['losses'] += 1
            pair_stats[p]['r'] += t.get('rr_achieved', 0)
        
        if pair_stats:
            message += f"\n{'='*30}\n"
            message += "\n💱 <b>BY PAIR</b>\n"
            for pair, ps in sorted(pair_stats.items()):
                display = pair.replace('_', '/')
                wr = ps['wins'] / (ps['wins'] + ps['losses']) * 100 if (ps['wins'] + ps['losses']) > 0 else 0
                p_emoji = "🟢" if ps['r'] > 0 else "🔴"
                message += f"{p_emoji} {display}: {ps['wins']}W/{ps['losses']}L | {ps['r']:+.1f}R | {wr:.0f}% WR\n"
        
        # --- BY SETUP SUMMARY ---
        setup_stats = {}
        for t in resolved:
            s = t.get('setup_type', 'Unknown')
            if s not in setup_stats:
                setup_stats[s] = {'wins': 0, 'losses': 0, 'r': 0}
            if t.get('status') == 'win':
                setup_stats[s]['wins'] += 1
            else:
                setup_stats[s]['losses'] += 1
            setup_stats[s]['r'] += t.get('rr_achieved', 0)
        
        if setup_stats:
            message += f"\n{'='*30}\n"
            message += "\n🔧 <b>BY SETUP</b>\n"
            for setup, ss in sorted(setup_stats.items(), key=lambda x: x[1]['r'], reverse=True):
                s_emoji = "✅" if ss['r'] > 0 else "❌"
                message += f"{s_emoji} {setup}: {ss['wins']}W/{ss['losses']}L | {ss['r']:+.1f}R\n"
        
        # --- SIGNALS GENERATED ---
        signals = report_data.get('signals_generated', [])
        if signals:
            message += f"\n{'='*30}\n"
            message += f"\n🎯 <b>SIGNALS GENERATED ({len(signals)})</b>\n"
            for sig in signals:
                direction = sig.get('direction', 'N/A')
                symbol = sig.get('symbol', 'N/A').replace('_', '/')
                entry = sig.get('entry_price', 0)
                rr = sig.get('risk_reward', 0)
                setup = sig.get('setup_type', 'ICT')
                confirmations = sig.get('confirmations', [])
                dir_arrow = "⬇️" if direction in ('short', 'SELL') else "⬆️"
                
                message += f"\n{dir_arrow} <b>{symbol}</b> {direction}\n"
                message += f"   Entry: {entry:.5f} | RR: 1:{rr:.1f}\n" if entry < 100 else f"   Entry: {entry:.2f} | RR: 1:{rr:.1f}\n"
                message += f"   {setup} | ✓ {', '.join(confirmations[:3])}\n"
        
        # --- TOP REJECTIONS ---
        rejections = report_data.get('rejections_summary', {})
        if rejections:
            message += f"\n{'='*30}\n"
            message += "\n❌ <b>TOP REJECTIONS</b>\n"
            sorted_reasons = sorted(rejections.items(), key=lambda x: x[1], reverse=True)
            for reason, count in sorted_reasons[:5]:
                message += f"   • {reason}: {count}x\n"
        
        # --- SESSION STATS ---
        stats = report_data.get('session_stats', {})
        if stats:
            message += f"\n{'='*30}\n"
            message += "\n📊 <b>SESSION STATS</b>\n"
            message += f"   Candles: {stats.get('candles_analyzed', 0)} | Setups: {stats.get('setups_checked', 0)}\n"
            message += f"   Sweeps: {stats.get('valid_sweeps', 0)} | BoS: {stats.get('valid_bos', 0)}\n"
        
        # Footer
        message += f"\n{'='*30}\n"
        message += f"\n<i>Jarvis ICT/SMC | Dynamic TP | Entry Fill Verified</i>"
        
        return self.send_message(message)
    
    def send_no_signal_reason(self, symbol: str, reasons: list) -> bool:
        """
        Send explanation of why no signal was generated.
        Only called periodically (not every candle).
        """
        display_symbol = symbol.replace('_', '/')
        
        message = f"""⚪ <b>No Signal: {display_symbol}</b>

<b>Missing Conditions:</b>
"""
        for reason in reasons[:5]:
            message += f"• {reason}\n"
        
        message += f"\n<i>{datetime.now().strftime('%H:%M')} UTC</i>"
        
        return self.send_message(message, disable_notification=True)
    
    def test_connection(self) -> bool:
        """Test the Telegram connection."""
        if not self.enabled:
            return False
        
        return self.send_message(
            "🤖 <b>Forex Trading Bot Connected!</b>\n\n"
            "✅ Telegram notifications are now active.\n"
            "📊 You'll receive alerts for:\n"
            "• New trading signals\n"
            "• Trade executions\n"
            "• System status updates",
            disable_notification=False
        )


# Singleton instance
_notifier: Optional[TelegramNotifier] = None


def get_telegram_notifier() -> TelegramNotifier:
    """Get or create the Telegram notifier singleton."""
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier


def init_telegram(bot_token: str = None, chat_id: str = None) -> TelegramNotifier:
    """Initialize Telegram with credentials."""
    global _notifier
    _notifier = TelegramNotifier(bot_token=bot_token, chat_id=chat_id)
    return _notifier
