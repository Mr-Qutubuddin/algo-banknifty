"""
DBHandler — SQLite/PostgreSQL interface for all database operations.
Centralized database access layer.
"""
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

BASE_DIR = Path(__file__).parent.parent.parent.parent
DB_PATH = BASE_DIR / "data" / "banknifty.db"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.FileHandler(Path(__file__).parent.parent.parent / 'logs' / 'db_handler.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class DBHandler:
    """Centralized database access and operations."""

    def __init__(self, db_path: str = None):
        self.db_path = str(db_path or DB_PATH)
        self._ensure_db()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_db(self):
        """Ensure database and base tables exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def execute(self, query: str, params: tuple = None) -> sqlite3.Cursor:
        """Execute a query and return cursor."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            conn.commit()
            return cursor

    def fetch_one(self, query: str, params: tuple = None) -> Optional[Dict]:
        """Fetch one row as dict."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            row = cursor.fetchone()
            return dict(row) if row else None

    def fetch_all(self, query: str, params: tuple = None) -> List[Dict]:
        """Fetch all rows as list of dicts."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def fetch_pandas(self, query: str, params: tuple = None):
        """Fetch data as pandas DataFrame."""
        import pandas as pd
        with self.get_connection() as conn:
            return pd.read_sql_query(query, conn, params=params or ())

    def insert(self, table: str, data: Dict) -> int:
        """Insert a row and return the row ID."""
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(data.values()))
            conn.commit()
            return cursor.lastrowid

    def update(self, table: str, data: Dict, where: str, where_params: tuple) -> int:
        """Update rows matching where clause."""
        set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
        query = f"UPDATE {table} SET {set_clause} WHERE {where}"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(data.values()) + where_params)
            conn.commit()
            return cursor.rowcount

    def delete(self, table: str, where: str, where_params: tuple) -> int:
        """Delete rows matching where clause."""
        query = f"DELETE FROM {table} WHERE {where}"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, where_params)
            conn.commit()
            return cursor.rowcount

    def table_exists(self, table: str) -> bool:
        """Check if a table exists."""
        query = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        result = self.fetch_one(query, (table,))
        return result is not None

    def vacuum(self):
        """Optimize database file size."""
        with self.get_connection() as conn:
            conn.execute("VACUUM")
        logger.info("Database vacuumed")

    def backup(self, backup_path: str):
        """Create a database backup."""
        import shutil
        shutil.copy2(self.db_path, backup_path)
        logger.info(f"Database backed up to {backup_path}")

    def close(self):
        """Close any open connections (no-op for sqlite, but required by interface)."""
        pass


if __name__ == "__main__":
    db = DBHandler()
    print(f"DBHandler ready. DB: {db.db_path}")