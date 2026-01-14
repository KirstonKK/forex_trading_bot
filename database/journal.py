"""
Trade Journal
Detailed logging of all trades for analysis and ML training.
"""

import sqlite3
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path


class TradeJournal:
    """SQLite-based trade journal for detailed trade logging."""

    def __init__(self, db_path: str = "data/journal.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self):
        """Get database connection."""
        return sqlite3.connect(str(self.db_path))

    def init_db(self):
        """Initialize journal schema."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Main trades table with detailed information
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                session TEXT,
                entry_time TIMESTAMP NOT NULL,
                exit_time TIMESTAMP,
                entry_price REAL NOT NULL,
                exit_price REAL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                quantity REAL NOT NULL,
                status TEXT DEFAULT 'open',
                
                -- SMC Strategy Details
                entry_zone_type TEXT,
                bos_strength REAL,
                pullback_confidence REAL,
                signal_strength REAL,
                
                -- Risk Management
                risk_amount REAL,
                reward_amount REAL,
                risk_reward_ratio REAL,
                
                -- P&L
                pnl REAL DEFAULT 0.0,
                pnl_percent REAL DEFAULT 0.0,
                pnl_in_pips REAL DEFAULT 0.0,
                
                -- Daily/Weekly Tracking
                daily_pnl REAL,
                weekly_pnl REAL,
                daily_trades_count INTEGER,
                account_balance_at_entry REAL,
                
                -- Exit Reason
                exit_reason TEXT,
                exit_comments TEXT
            )
        """)
        
        # Daily statistics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                date DATE PRIMARY KEY,
                total_trades INTEGER,
                winning_trades INTEGER,
                losing_trades INTEGER,
                win_rate REAL,
                avg_win REAL,
                avg_loss REAL,
                profit_factor REAL,
                total_pnl REAL,
                daily_pnl_percent REAL,
                account_balance REAL,
                sessions_traded TEXT
            )
        """)
        
        # Weekly statistics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weekly_stats (
                week_start DATE PRIMARY KEY,
                total_trades INTEGER,
                winning_trades INTEGER,
                losing_trades INTEGER,
                win_rate REAL,
                total_pnl REAL,
                weekly_pnl_percent REAL,
                account_balance REAL
            )
        """)
        
        conn.commit()
        conn.close()

    def log_trade(self, trade_data: Dict) -> bool:
        """
        Log a complete trade with all details.
        
        Args:
            trade_data: Dictionary with trade information
            
        Returns:
            True if successful
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO trades (
                    id, symbol, session, entry_time, exit_time,
                    entry_price, exit_price, stop_loss, take_profit, quantity,
                    status, entry_zone_type, bos_strength, pullback_confidence,
                    signal_strength, risk_amount, reward_amount, risk_reward_ratio,
                    pnl, pnl_percent, pnl_in_pips, daily_pnl, weekly_pnl,
                    daily_trades_count, account_balance_at_entry, exit_reason,
                    exit_comments
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                         ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_data.get('id'),
                trade_data.get('symbol'),
                trade_data.get('session'),
                trade_data.get('entry_time'),
                trade_data.get('exit_time'),
                trade_data.get('entry_price'),
                trade_data.get('exit_price'),
                trade_data.get('stop_loss'),
                trade_data.get('take_profit'),
                trade_data.get('quantity'),
                trade_data.get('status', 'open'),
                trade_data.get('entry_zone_type'),
                trade_data.get('bos_strength'),
                trade_data.get('pullback_confidence'),
                trade_data.get('signal_strength'),
                trade_data.get('risk_amount'),
                trade_data.get('reward_amount'),
                trade_data.get('risk_reward_ratio'),
                trade_data.get('pnl'),
                trade_data.get('pnl_percent'),
                trade_data.get('pnl_in_pips'),
                trade_data.get('daily_pnl'),
                trade_data.get('weekly_pnl'),
                trade_data.get('daily_trades_count'),
                trade_data.get('account_balance_at_entry'),
                trade_data.get('exit_reason'),
                trade_data.get('exit_comments')
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error logging trade: {e}")
            return False

    def get_trades(
        self,
        symbol: str = None,
        status: str = None,
        days: int = None
    ) -> List[Dict]:
        """
        Retrieve trades from journal.
        
        Args:
            symbol: Filter by trading pair
            status: Filter by status (open/closed)
            days: Last N days
            
        Returns:
            List of trade dictionaries
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            query = "SELECT * FROM trades WHERE 1=1"
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            if status:
                query += " AND status = ?"
                params.append(status)
            
            if days:
                query += " AND entry_time > datetime('now', '-' || ? || ' days')"
                params.append(days)
            
            query += " ORDER BY entry_time DESC"
            
            cursor.execute(query, params)
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            
            trades = [dict(zip(columns, row)) for row in rows]
            conn.close()
            
            return trades
        except Exception as e:
            print(f"Error retrieving trades: {e}")
            return []

    def get_closed_trades(self) -> List[Dict]:
        """Get all closed trades."""
        return self.get_trades(status='closed')

    def update_trade_exit(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str,
        exit_comments: str = ""
    ) -> bool:
        """Update trade with exit information."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT entry_price, quantity, stop_loss FROM trades WHERE id = ?
            """, (trade_id,))
            
            row = cursor.fetchone()
            if not row:
                return False
            
            entry_price, quantity, stop_loss = row
            
            # Calculate P&L
            pnl = (exit_price - entry_price) * quantity
            pnl_percent = ((exit_price - entry_price) / entry_price) * 100
            
            # Calculate pips (assuming 4 decimal places standard)
            pnl_pips = (exit_price - entry_price) * 10000
            
            cursor.execute("""
                UPDATE trades SET
                    exit_price = ?, exit_time = ?, status = 'closed',
                    pnl = ?, pnl_percent = ?, pnl_in_pips = ?,
                    exit_reason = ?, exit_comments = ?
                WHERE id = ?
            """, (
                exit_price,
                datetime.now().isoformat(),
                pnl,
                pnl_percent,
                pnl_pips,
                exit_reason,
                exit_comments,
                trade_id
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error updating trade: {e}")
            return False

    def get_statistics(self, days: int = None) -> Dict:
        """
        Get trading statistics.
        
        Args:
            days: Last N days, or all if None
            
        Returns:
            Dictionary of statistics
        """
        trades = self.get_closed_trades()
        
        if not trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "total_pnl": 0.0
            }
        
        winners = [t['pnl'] for t in trades if t['pnl'] and t['pnl'] > 0]
        losers = [t['pnl'] for t in trades if t['pnl'] and t['pnl'] < 0]
        
        total_wins = sum(winners)
        total_losses = sum(losers)
        
        profit_factor = total_wins / abs(total_losses) if total_losses != 0 else 0
        
        return {
            "total_trades": len(trades),
            "winning_trades": len(winners),
            "losing_trades": len(losers),
            "win_rate": (len(winners) / len(trades) * 100) if trades else 0,
            "avg_win": total_wins / len(winners) if winners else 0,
            "avg_loss": total_losses / len(losers) if losers else 0,
            "profit_factor": profit_factor,
            "total_pnl": total_wins + total_losses
        }

    def export_journal(self, filepath: str = "journal_export.csv") -> bool:
        """Export journal to CSV."""
        try:
            import csv
            
            trades = self.get_trades()
            
            if not trades:
                return False
            
            with open(filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=trades[0].keys())
                writer.writeheader()
                writer.writerows(trades)
            
            return True
        except Exception as e:
            print(f"Error exporting journal: {e}")
            return False
