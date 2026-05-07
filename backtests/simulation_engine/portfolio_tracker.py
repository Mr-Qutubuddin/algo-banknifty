"""
PortfolioTracker — Tracks positions, P&L, drawdown, margin in real-time.
"""
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.FileHandler(Path(__file__).parent.parent.parent / 'logs' / 'portfolio_tracker.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


@dataclass
class Position:
    order_id: str
    instrument: str
    strike: int
    option_type: str
    side: str
    quantity: int
    entry_price: float
    current_price: float
    timestamp: str
    charges: Dict = field(default_factory=dict)

    @property
    def unrealized_pnl(self) -> float:
        if self.side == "BUY":
            return (self.current_price - self.entry_price) * self.quantity * 15
        else:
            return (self.entry_price - self.current_price) * self.quantity * 15

    @property
    def realized_pnl(self) -> float:
        return 0.0

    @property
    def entry_value(self) -> float:
        return self.entry_price * self.quantity * 15

    @property
    def current_value(self) -> float:
        return self.current_price * self.quantity * 15


class PortfolioTracker:
    """Tracks portfolio with live P&L, positions, and drawdown."""

    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: List[Position] = []
        self.closed_trades: List[Dict] = []
        self.trade_history: List[Dict] = []
        self.equity_curve: List[Dict] = []
        self.daily_pnl: List[float] = []
        self.peak_equity = initial_capital
        self.max_drawdown = 0.0

    def open_position(self, order: Dict):
        """Open a new position from a filled order."""
        position = Position(
            order_id=order["order_id"],
            instrument=order["instrument"],
            strike=order.get("strike", 0),
            option_type=order.get("option_type", "CE"),
            side=order["side"],
            quantity=order["quantity"],
            entry_price=order["fill_price"],
            current_price=order["fill_price"],
            timestamp=order["timestamp"],
            charges=order.get("charges", {})
        )
        self.positions.append(position)
        margin = order["fill_price"] * order["quantity"] * 15 * (0.2 if order["side"] == "BUY" else 0.15)
        self.cash -= (margin + order["charges"].get("total_charges", 0) if order["side"] == "BUY" else 0)
        logger.info(f"Position opened: {position.instrument} {position.side} {position.quantity} @ {position.entry_price}")

    def close_position(self, position, exit_price: float, charges: Dict, exit_timestamp: str = None):
        """Close a position and record the trade."""
        # Handle both dict (from backtest) and Position object (from live)
        if isinstance(position, dict):
            # Dict format from backtest simulation
            order_id = position.get("order_id", "UNK")
            instrument = position.get("instrument", "UNKNOWN")
            strike = position.get("strike", 0)
            option_type = position.get("option_type", "CE")
            side = position.get("side", "BUY")
            quantity = position.get("quantity", 1)
            entry_price = position.get("entry_price", 0)
            entry_timestamp = position.get("timestamp", datetime.now().isoformat())
            # Calculate pnl for dict case
            if side == "BUY":
                pnl = (exit_price - entry_price) * quantity * 15 - charges.get("total_charges", 0)
            else:
                pnl = (entry_price - exit_price) * quantity * 15 - charges.get("total_charges", 0)
        else:
            # Position object format - live trading
            order_id = position.order_id
            instrument = position.instrument
            strike = position.strike
            option_type = position.option_type
            side = position.side
            quantity = position.quantity
            entry_price = position.entry_price
            entry_timestamp = position.timestamp
            position.current_price = exit_price
            pnl = position.unrealized_pnl - charges.get("total_charges", 0)
            self.positions.remove(position)
            margin_release = position.entry_value * (0.2 if side == "BUY" else 0.15)
            self.cash += margin_release + pnl

        trade = {
            "order_id": order_id,
            "instrument": instrument,
            "strike": strike,
            "option_type": option_type,
            "side": side,
            "quantity": quantity,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": round(pnl, 2),
            "charges": charges,
            "entry_time": entry_timestamp,
            "exit_time": exit_timestamp or datetime.now().isoformat(),
            "duration_minutes": 0
        }
        if entry_price and quantity:
            try:
                entry_dt = datetime.fromisoformat(entry_timestamp)
                exit_dt = datetime.fromisoformat(trade["exit_time"])
                trade["duration_minutes"] = (exit_dt - entry_dt).total_seconds() / 60
            except:
                pass

        self.closed_trades.append(trade)
        self.trade_history.append(trade)
        if not isinstance(position, dict):
            self.positions.remove(position)
            margin_release = position.entry_price * position.quantity * 15 * (0.2 if position.side == "BUY" else 0.15)
            self.cash += margin_release + pnl
        else:
            # Backtest dict case: margin was blocked but not deducted from cash at entry
            # Release margin + apply P&L
            entry_value = entry_price * quantity * 15
            margin_release = entry_value * (0.2 if side == "BUY" else 0.15)
            self.cash += margin_release + pnl

        logger.info(f"Position closed: P&L = {pnl:.2f}")
        return trade

    def update_market_price(self, instrument: str, price: float):
        """Update current prices for all positions."""
        for pos in self.positions:
            if pos.instrument == instrument:
                pos.current_price = price

    def get_unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions)

    def get_realized_pnl(self) -> float:
        return sum(t["pnl"] for t in self.closed_trades)

    def get_total_pnl(self) -> float:
        return self.get_realized_pnl() + self.get_unrealized_pnl()

    def get_equity(self) -> float:
        return self.cash + self.get_unrealized_pnl()

    def record_equity_snapshot(self, timestamp: str = None):
        equity = self.get_equity()
        self.equity_curve.append({
            "timestamp": timestamp or datetime.now().isoformat(),
            "equity": round(equity, 2),
            "cash": round(self.cash, 2),
            "unrealized_pnl": round(self.get_unrealized_pnl(), 2),
            "drawdown": round(self.get_current_drawdown(), 4)
        })
        if equity > self.peak_equity:
            self.peak_equity = equity
        self.max_drawdown = max(self.max_drawdown, self.get_current_drawdown())

    def get_current_drawdown(self) -> float:
        equity = self.get_equity()
        if self.peak_equity == 0:
            return 0.0
        return (self.peak_equity - equity) / self.peak_equity

    def get_max_drawdown_pct(self) -> float:
        return self.max_drawdown

    def get_margin_used(self) -> float:
        margin = 0.0
        for pos in self.positions:
            margin += pos.entry_value * (0.2 if pos.side == "BUY" else 0.15)
        return margin

    def get_open_positions_count(self) -> int:
        return len(self.positions)

    def square_off_all(self, current_prices: Dict[str, float], order_simulator):
        """Square off all open positions at current market prices."""
        trades = []
        for pos in list(self.positions):
            price = current_prices.get(pos.instrument, pos.current_price)
            exit_side = "SELL" if pos.side == "BUY" else "BUY"
            order = order_simulator.place_market_order(
                pos.instrument, exit_side, pos.quantity, price, pos.option_type
            )
            charges = order["charges"]
            trade = self.close_position(pos, order["fill_price"], charges)
            trades.append(trade)
        return trades

    def get_statistics(self) -> Dict:
        total_trades = len(self.closed_trades)
        if total_trades == 0:
            return {"total_trades": 0, "win_rate": 0, "profit_factor": 0,
                    "avg_trade": 0, "sharpe": 0, "max_drawdown": 0}

        wins = [t["pnl"] for t in self.closed_trades if t["pnl"] > 0]
        losses = [t["pnl"] for t in self.closed_trades if t["pnl"] <= 0]

        total_pnl = sum(t["pnl"] for t in self.closed_trades)
        win_rate = len(wins) / total_trades if total_trades > 0 else 0
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0
        profit_factor = avg_win / avg_loss if avg_loss > 0 else 0

        returns = [t["pnl"] / self.initial_capital for t in self.closed_trades]
        avg_return = sum(returns) / len(returns) if returns else 0
        std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5 if len(returns) > 1 else 1
        sharpe = (avg_return / std_return * (252 ** 0.5)) if std_return > 0 else 0

        return {
            "total_trades": total_trades,
            "win_rate": round(win_rate, 4),
            "profit_factor": round(profit_factor, 2),
            "avg_trade": round(total_pnl / total_trades, 2),
            "sharpe_ratio": round(sharpe, 3),
            "max_drawdown_pct": round(self.max_drawdown * 100, 2),
            "total_pnl": round(total_pnl, 2),
            "open_positions": self.get_open_positions_count(),
            "margin_used": round(self.get_margin_used(), 2)
        }

    def reset(self):
        self.__init__(self.initial_capital)


if __name__ == "__main__":
    pt = PortfolioTracker(100000)
    print(f"Initial capital: {pt.initial_capital}, Equity: {pt.get_equity()}")