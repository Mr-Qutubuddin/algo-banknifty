"""
TradeLogger — Logs every trade, signal, tick to SQLite storage.
Every action in the algo is persisted for audit and analysis.
"""
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

BASE_DIR = Path(__file__).parent.parent.parent.parent
DB_PATH = BASE_DIR / "data" / "banknifty.db"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.FileHandler(Path(__file__).parent.parent.parent / 'logs' / 'trade_logger.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class TradeLogger:
    """Persists all trading activity to SQLite database."""

    def __init__(self, db_path: str = None):
        self.db_path = str(db_path or DB_PATH)
        self._ensure_tables()
        logger.info(f"TradeLogger initialized: {self.db_path}")

    def _ensure_tables(self):
        """Create all required tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS signals
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      timestamp TEXT NOT NULL,
                      signal TEXT,
                      strike INTEGER,
                      option_type TEXT,
                      lots INTEGER,
                      confidence REAL,
                      reason TEXT,
                      strategy_id TEXT,
                      approach_id TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS orders
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      timestamp TEXT NOT NULL,
                      order_id TEXT UNIQUE,
                      instrument TEXT,
                      side TEXT,
                      quantity INTEGER,
                      fill_price REAL,
                      charges REAL,
                      status TEXT,
                      strategy_id TEXT,
                      approach_id TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS positions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      timestamp TEXT NOT NULL,
                      instrument TEXT,
                      strike INTEGER,
                      option_type TEXT,
                      side TEXT,
                      quantity INTEGER,
                      entry_price REAL,
                      current_price REAL,
                      unrealized_pnl REAL,
                      status TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS pnl_snapshots
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      timestamp TEXT NOT NULL,
                      realized_pnl REAL,
                      unrealized_pnl REAL,
                      total_pnl REAL,
                      margin_used REAL,
                      drawdown_pct REAL,
                      equity REAL)''')

        c.execute('''CREATE TABLE IF NOT EXISTS daily_summary
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      date TEXT UNIQUE,
                      total_trades INTEGER,
                      winning_trades INTEGER,
                      losing_trades INTEGER,
                      win_rate REAL,
                      total_pnl REAL,
                      realized_pnl REAL,
                      max_drawdown REAL,
                      capital_used REAL,
                      timestamp TEXT DEFAULT CURRENT_TIMESTAMP)''')

        c.execute('''CREATE TABLE IF NOT EXISTS config_changes
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      timestamp TEXT NOT NULL,
                      config_name TEXT,
                      param TEXT,
                      old_value TEXT,
                      new_value TEXT,
                      reason TEXT)''')

        conn.commit()
        conn.close()

    def log_signal(self, signal: Dict, strategy_id: str = "", approach_id: str = ""):
        """Log a trading signal."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''INSERT INTO signals
                        (timestamp, signal, strike, option_type, lots, confidence, reason, strategy_id, approach_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (datetime.now().isoformat(), signal.get("signal"), signal.get("strike"),
                       signal.get("option_type"), signal.get("lots"), signal.get("confidence"),
                       signal.get("reason", ""), strategy_id, approach_id))
            conn.commit()
            conn.close()
            logger.debug(f"Signal logged: {signal.get('signal')} {signal.get('strike')} {signal.get('option_type')}")
        except Exception as e:
            logger.error(f"Failed to log signal: {e}")

    def log_order(self, order: Dict, strategy_id: str = "", approach_id: str = ""):
        """Log an order."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''INSERT INTO orders
                        (timestamp, order_id, instrument, side, quantity, fill_price, charges, status, strategy_id, approach_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (datetime.now().isoformat(), order.get("order_id"), order.get("instrument"),
                       order.get("side"), order.get("quantity"), order.get("fill_price"),
                       order.get("charges", {}).get("total_charges", 0), order.get("status"),
                       strategy_id, approach_id))
            conn.commit()
            conn.close()
            logger.info(f"Order logged: {order.get('order_id')} {order.get('status')}")
        except Exception as e:
            logger.error(f"Failed to log order: {e}")

    def log_position(self, position: Dict, status: str = "OPEN"):
        """Log a position state change."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''INSERT INTO positions
                        (timestamp, instrument, strike, option_type, side, quantity,
                         entry_price, current_price, unrealized_pnl, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (datetime.now().isoformat(), position.get("instrument"), position.get("strike"),
                       position.get("option_type"), position.get("side"), position.get("quantity"),
                       position.get("entry_price"), position.get("current_price", 0),
                       position.get("unrealized_pnl", 0), status))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to log position: {e}")

    def log_pnl_snapshot(self, realized: float, unrealized: float, margin: float, drawdown: float, equity: float):
        """Log a P&L snapshot."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''INSERT INTO pnl_snapshots
                        (timestamp, realized_pnl, unrealized_pnl, total_pnl, margin_used, drawdown_pct, equity)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                      (datetime.now().isoformat(), realized, unrealized, realized + unrealized,
                       margin, drawdown, equity))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to log P&L snapshot: {e}")

    def log_daily_summary(self, date: str, trades: List[Dict], equity: float):
        """Log end-of-day summary."""
        try:
            winning = sum(1 for t in trades if t.get("pnl", 0) > 0)
            losing = sum(1 for t in trades if t.get("pnl", 0) <= 0)
            total_pnl = sum(t.get("pnl", 0) for t in trades)

            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''INSERT OR REPLACE INTO daily_summary
                        (date, total_trades, winning_trades, losing_trades, win_rate, total_pnl, realized_pnl, capital_used, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (date, len(trades), winning, losing,
                       winning / len(trades) if trades else 0, total_pnl, total_pnl,
                       equity, datetime.now().isoformat()))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to log daily summary: {e}")

    def log_config_change(self, config_name: str, param: str, old_value: any, new_value: any, reason: str):
        """Log a configuration change."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''INSERT INTO config_changes
                        (timestamp, config_name, param, old_value, new_value, reason)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                      (datetime.now().isoformat(), config_name, param, str(old_value), str(new_value), reason))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to log config change: {e}")

    def get_trade_history(self, limit: int = 100) -> List[Dict]:
        """Get recent trade history."""
        conn = sqlite3.connect(self.db_path)
        df = __import__('pandas').read_sql_query(
            "SELECT * FROM orders WHERE status='FILLED' ORDER BY timestamp DESC LIMIT ?",
            conn, params=(limit,))
        conn.close()
        return df.to_dict('records')

    def get_signals(self, limit: int = 50) -> List[Dict]:
        """Get recent signals."""
        conn = sqlite3.connect(self.db_path)
        df = __import__('pandas').read_sql_query(
            "SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?",
            conn, params=(limit,))
        conn.close()
        return df.to_dict('records')

    def get_daily_summaries(self, days: int = 30) -> List[Dict]:
        """Get daily summary for last N days."""
        conn = sqlite3.connect(self.db_path)
        df = __import__('pandas').read_sql_query(
            "SELECT * FROM daily_summary ORDER BY date DESC LIMIT ?",
            conn, params=(days,))
        conn.close()
        return df.to_dict('records')


if __name__ == "__main__":
    logger = TradeLogger()
    print("TradeLogger ready.")