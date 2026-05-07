"""
ExportHandler — Export data to Excel, JSON, CSV formats on demand.
"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List

import pandas as pd

BASE_DIR = Path(__file__).parent.parent.parent.parent
DB_PATH = BASE_DIR / "data" / "banknifty.db"
EXPORTS_DIR = BASE_DIR / "data" / "exports"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.FileHandler(Path(__file__).parent.parent.parent / 'logs' / 'export_handler.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class ExportHandler:
    """Exports trading data to Excel, JSON, CSV formats."""

    def __init__(self, db_path: str = None):
        self.db_path = str(db_path or DB_PATH)
        self.exports_dir = Path(EXPORTS_DIR)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def export_trades_to_excel(self, output_path: str = None, days: int = 30) -> str:
        """Export trade history to Excel with multiple sheets."""
        output_path = output_path or str(self.exports_dir / f"trades_{datetime.now().strftime('%Y%m%d')}.xlsx")

        conn = __import__('sqlite3').connect(self.db_path)

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            orders_df = pd.read_sql_query(
                "SELECT * FROM orders ORDER BY timestamp DESC LIMIT ?",
                conn, params=(days * 100,)
            )
            orders_df.to_excel(writer, sheet_name='Orders', index=False)

            signals_df = pd.read_sql_query(
                "SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?",
                conn, params=(days * 50,)
            )
            signals_df.to_excel(writer, sheet_name='Signals', index=False)

            positions_df = pd.read_sql_query(
                "SELECT * FROM positions ORDER BY timestamp DESC",
                conn
            )
            positions_df.to_excel(writer, sheet_name='Positions', index=False)

            pnl_df = pd.read_sql_query(
                "SELECT * FROM pnl_snapshots ORDER BY timestamp DESC LIMIT ?",
                conn, params=(days * 78,)
            )
            pnl_df.to_excel(writer, sheet_name='P&L_Snapshots', index=False)

            daily_df = pd.read_sql_query(
                "SELECT * FROM daily_summary ORDER BY date DESC LIMIT ?",
                conn, params=(days,)
            )
            daily_df.to_excel(writer, sheet_name='Daily_Summary', index=False)

        conn.close()
        logger.info(f"Trades exported to {output_path}")
        return output_path

    def export_trades_to_json(self, output_path: str = None, days: int = 30) -> str:
        """Export trade history to JSON."""
        output_path = output_path or str(self.exports_dir / f"trades_{datetime.now().strftime('%Y%m%d')}.json")

        conn = __import__('sqlite3').connect(self.db_path)

        data = {
            "orders": pd.read_sql_query("SELECT * FROM orders ORDER BY timestamp DESC LIMIT ?",
                                         conn, params=(days * 100,)).to_dict('records'),
            "signals": pd.read_sql_query("SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?",
                                         conn, params=(days * 50,)).to_dict('records'),
            "positions": pd.read_sql_query("SELECT * FROM positions ORDER BY timestamp DESC",
                                           conn).to_dict('records'),
            "daily_summary": pd.read_sql_query("SELECT * FROM daily_summary ORDER BY date DESC LIMIT ?",
                                               conn, params=(days,)).to_dict('records'),
            "export_timestamp": datetime.now().isoformat()
        }

        conn.close()

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"Trades exported to {output_path}")
        return output_path

    def export_trades_to_csv(self, output_dir: str = None) -> Dict[str, str]:
        """Export each table to separate CSV files."""
        output_dir = output_dir or str(self.exports_dir / f"csv_{datetime.now().strftime('%Y%m%d')}")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        tables = ['orders', 'signals', 'positions', 'pnl_snapshots', 'daily_summary']
        exported = {}

        conn = __import__('sqlite3').connect(self.db_path)

        for table in tables:
            filepath = Path(output_dir) / f"{table}.csv"
            df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
            df.to_csv(filepath, index=False)
            exported[table] = str(filepath)
            logger.info(f"Exported {table} to {filepath}")

        conn.close()
        return exported

    def export_backtest_results(self, results_dir: Path, output_path: str = None) -> str:
        """Export backtest results to formatted Excel."""
        output_path = output_path or str(self.exports_dir / f"backtest_results_{datetime.now().strftime('%Y%m%d')}.xlsx")

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            summary_data = []
            for strategy_dir in results_dir.iterdir():
                if strategy_dir.is_dir():
                    summary_file = strategy_dir / "summary.json"
                    if summary_file.exists():
                        import json
                        with open(summary_file) as f:
                            summary_data.append(json.load(f))

            if summary_data:
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Strategy_Summary', index=False)

            equity_files = list(results_dir.glob("*/equity_curve.csv"))
            for i, ef in enumerate(equity_files[:10]):
                df = pd.read_csv(ef)
                sheet_name = ef.parent.name[:31]
                df.to_excel(writer, sheet_name=sheet_name, index=False)

        logger.info(f"Backtest results exported to {output_path}")
        return output_path

    def generate_performance_report(self, days: int = 30) -> Dict:
        """Generate performance metrics summary."""
        conn = __import__('sqlite3').connect(self.db_path)

        orders_df = pd.read_sql_query("SELECT * FROM orders WHERE status='FILLED'", conn)
        daily_df = pd.read_sql_query("SELECT * FROM daily_summary ORDER BY date DESC LIMIT ?",
                                      conn, params=(days,))

        conn.close()

        if orders_df.empty:
            return {"error": "No trade data available"}

        total_trades = len(orders_df)
        winning_trades = daily_df['winning_trades'].sum() if 'winning_trades' in daily_df.columns else 0
        total_pnl = daily_df['total_pnl'].sum() if 'total_pnl' in daily_df.columns else 0

        report = {
            "period_days": days,
            "total_trades": total_trades,
            "total_winning": winning_trades,
            "win_rate": round(winning_trades / total_trades, 4) if total_trades > 0 else 0,
            "total_pnl": round(total_pnl, 2),
            "avg_pnl_per_trade": round(total_pnl / total_trades, 2) if total_trades > 0 else 0,
            "best_day": daily_df.loc[daily_df['total_pnl'].idxmax(), 'date'] if not daily_df.empty and 'total_pnl' in daily_df.columns else None,
            "worst_day": daily_df.loc[daily_df['total_pnl'].idxmin(), 'date'] if not daily_df.empty and 'total_pnl' in daily_df.columns else None
        }

        return report


if __name__ == "__main__":
    exporter = ExportHandler()
    print("ExportHandler ready.")