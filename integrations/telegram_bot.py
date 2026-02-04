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
        emoji = "🟢" if direction == "BUY" else "🔴" if direction == "SELL" else "⚪"
        
        # Format symbol nicely
        pair = symbol.replace('_', '/')
        
        # Price note for Gold
        price_note = ""
        if 'XAU' in symbol:
            price_note = "\n\n⚠️ <i>Futures price - spot ~$30-40 lower</i>"
        
        # ML section
        ml_section = ""
        if ml_confidence is not None:
            risk_emoji = "🟢" if ml_recommendation == 'full_risk' else "🟡" if 'half' in ml_recommendation or 'quarter' in ml_recommendation else "🔴"
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
            pnl_emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
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
        pnl_emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
        
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
        Send comprehensive daily trading report.
        
        Args:
            report_data: Dictionary containing:
                - signals_generated: list of signals
                - signals_rejected: list of rejection reasons
                - market_analysis: dict of pair analyses
                - session_summary: session activity
        """
        date_str = datetime.now().strftime('%Y-%m-%d')
        
        # Header
        message = f"""📋 <b>DAILY TRADING REPORT</b>
📅 {date_str} | Session: 10:00-17:00 UTC

{'='*30}
"""
        
        # Signals Generated
        signals = report_data.get('signals_generated', [])
        if signals:
            message += f"\n🎯 <b>SIGNALS GENERATED ({len(signals)})</b>\n"
            for sig in signals[-5:]:  # Last 5 signals
                direction = sig.get('direction', 'N/A')
                symbol = sig.get('symbol', 'N/A').replace('_', '/')
                entry = sig.get('entry_price', 0)
                rr = sig.get('risk_reward', 0)
                setup = sig.get('setup_type', 'ICT')
                confirmations = sig.get('confirmations', [])
                emoji = "🟢" if direction == "BUY" else "🔴"
                
                message += f"\n{emoji} <b>{symbol}</b> {direction}\n"
                message += f"   Entry: {entry:.5f} | RR: 1:{rr:.1f}\n"
                message += f"   Setup: {setup}\n"
                message += f"   ✓ {', '.join(confirmations[:3])}\n"
        else:
            message += "\n🎯 <b>SIGNALS GENERATED: 0</b>\n"
            message += "   No valid ICT setups detected today.\n"
        
        # Rejections Analysis
        rejections = report_data.get('rejections_summary', {})
        if rejections:
            message += f"\n{'='*30}\n"
            message += "\n❌ <b>WHY SIGNALS WERE REJECTED</b>\n"
            
            # Sort by count
            sorted_reasons = sorted(rejections.items(), key=lambda x: x[1], reverse=True)
            for reason, count in sorted_reasons[:6]:
                message += f"   • {reason}: {count}x\n"
        
        # Per-Pair Analysis
        pair_analysis = report_data.get('pair_analysis', {})
        if pair_analysis:
            message += f"\n{'='*30}\n"
            message += "\n📈 <b>PAIR-BY-PAIR ANALYSIS</b>\n"
            
            for pair, analysis in pair_analysis.items():
                display_pair = pair.replace('_', '/')
                bias = analysis.get('htf_bias', 'neutral')
                bias_emoji = "🟢" if 'bullish' in bias.lower() else "🔴" if 'bearish' in bias.lower() else "⚪"
                
                message += f"\n<b>{display_pair}</b> {bias_emoji}\n"
                message += f"   HTF Bias: {bias}\n"
                
                if analysis.get('sweeps_detected'):
                    message += f"   Sweeps: {analysis['sweeps_detected']}\n"
                if analysis.get('fvgs_available'):
                    message += f"   FVGs: {analysis['fvgs_available']}\n"
                if analysis.get('obs_available'):
                    message += f"   Order Blocks: {analysis['obs_available']}\n"
                if analysis.get('rejection_reason'):
                    message += f"   ⚠️ {analysis['rejection_reason']}\n"
        
        # Market Sentiment
        sentiment = report_data.get('market_sentiment', '')
        if sentiment:
            message += f"\n{'='*30}\n"
            message += f"\n🧠 <b>MARKET SENTIMENT</b>\n{sentiment}\n"
        
        # Session Stats
        stats = report_data.get('session_stats', {})
        if stats:
            message += f"\n{'='*30}\n"
            message += "\n📊 <b>SESSION STATISTICS</b>\n"
            message += f"   Candles Analyzed: {stats.get('candles_analyzed', 0)}\n"
            message += f"   Setups Checked: {stats.get('setups_checked', 0)}\n"
            message += f"   Valid Sweeps: {stats.get('valid_sweeps', 0)}\n"
            message += f"   Valid BoS: {stats.get('valid_bos', 0)}\n"
            
            # Format active time
            hours = stats.get('hours_active', 0)
            mins = stats.get('minutes_active', 0)
            time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
            message += f"   Session Active: {time_str}\n"
        
        # Footer
        message += f"\n{'='*30}\n"
        message += "\n<i>ICT/SMC Strategy | 1:2 RR | 60% Target</i>"
        
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
