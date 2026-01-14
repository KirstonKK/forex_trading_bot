"""
Trading Database
Persistent storage for trades, orders, and performance data.
"""

import sqlite3
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path


class TradesDatabase:
    """SQLite database for trade history and statistics."""

    def __init__(self, db_path: str = "data/trading.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self):
        """Get database connection."""
        return sqlite3.connect(str(self.db_path))

    def init_db(self):
        """Initialize database schema."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                quantity REAL NOT NULL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                entry_time TIMESTAMP NOT NULL,
                exit_time TIMESTAMP,
                pnl REAL DEFAULT 0.0,
                pnl_percent REAL DEFAULT 0.0,
                status TEXT DEFAULT 'open',
                pattern_type TEXT
            )
        """)
        
        # Orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                trade_id TEXT,
                symbol TEXT NOT NULL,
                order_type TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                opened_at TIMESTAMP,
                closed_at TIMESTAMP,
                pnl REAL DEFAULT 0.0,
                FOREIGN KEY (trade_id) REFERENCES trades(id)
            )
        """)
        
        # Performance metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TIMESTAMP NOT NULL,
                total_trades INTEGER,
                winning_trades INTEGER,
                losing_trades INTEGER,
                win_rate REAL,
                avg_win REAL,
                avg_loss REAL,
                total_pnl REAL,
                account_balance REAL
            )
        """)
        
        conn.commit()
        conn.close()

    def save_trade(self, trade_dict: Dict) -> bool:
        """Save a trade to database."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO trades (
                    id, symbol, entry_price, exit_price, quantity,
                    stop_loss, take_profit, entry_time, exit_time,
                    pnl, pnl_percent, status, pattern_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_dict.get('id'),
                trade_dict.get('symbol'),
                trade_dict.get('entry_price'),
                trade_dict.get('exit_price'),
                trade_dict.get('quantity'),
                trade_dict.get('stop_loss'),
                trade_dict.get('take_profit'),
                trade_dict.get('entry_time'),
                trade_dict.get('exit_time'),
                trade_dict.get('pnl', 0.0),
                trade_dict.get('pnl_percent', 0.0),
                trade_dict.get('status', 'open'),
                trade_dict.get('pattern_type')
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error saving trade: {e}")
            return False

    def get_trades(self, symbol: str = None, status: str = None) -> List[Dict]:
        """Get trades from database."""
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
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            trades = []
            for row in rows:
                trades.append({
                    'id': row[0],
                    'symbol': row[1],
                    'entry_price': row[2],
                    'exit_price': row[3],
                    'quantity': row[4],
                    'stop_loss': row[5],
                    'take_profit': row[6],
                    'entry_time': row[7],
                    'exit_time': row[8],
                    'pnl': row[9],
                    'pnl_percent': row[10],
                    'status': row[11],
                    'pattern_type': row[12]
                })
            
            conn.close()
            return trades
        except Exception as e:
            print(f"Error getting trades: {e}")
            return []

    def get_closed_trades(self) -> List[Dict]:
        """Get all closed trades."""
        return self.get_trades(status='closed')

    def save_performance(self, perf_dict: Dict) -> bool:
        """Save performance metrics."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO performance (
                    date, total_trades, winning_trades, losing_trades,
                    win_rate, avg_win, avg_loss, total_pnl, account_balance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(),
                perf_dict.get('total_trades'),
                perf_dict.get('winning_trades'),
                perf_dict.get('losing_trades'),
                perf_dict.get('win_rate'),
                perf_dict.get('avg_win'),
                perf_dict.get('avg_loss'),
                perf_dict.get('total_pnl'),
                perf_dict.get('account_balance')
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error saving performance: {e}")
            return False

    def get_performance_history(self) -> List[Dict]:
        """Get performance history."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM performance ORDER BY date DESC LIMIT 100")
            rows = cursor.fetchall()
            
            history = []
            for row in rows:
                history.append({
                    'date': row[1],
                    'total_trades': row[2],
                    'winning_trades': row[3],
                    'losing_trades': row[4],
                    'win_rate': row[5],
                    'avg_win': row[6],
                    'avg_loss': row[7],
                    'total_pnl': row[8],
                    'account_balance': row[9]
                })
            
            conn.close()
            return history
        except Exception as e:
            print(f"Error getting performance: {e}")
            return []
