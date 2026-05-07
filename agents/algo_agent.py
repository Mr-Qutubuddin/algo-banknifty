"""
AlgoAgent — Builds the real-time algo trading system once strategy is approved.
Implements data collection, signal engine, order management, position tracking, and risk management.
"""
import os
import json
import logging
import time
import sqlite3
from pathlib import Path
from datetime import datetime, time as dt_time
from typing import Dict, List, Optional, Callable
from threading import Thread, Lock

BASE_DIR = Path(__file__).parent.parent.parent
ALGO_DIR = BASE_DIR / "algo"
CORE_DIR = ALGO_DIR / "core"
STORAGE_DIR = ALGO_DIR / "storage"
DB_PATH = BASE_DIR / "data" / "banknifty.db"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.FileHandler(Path(__file__).parent.parent / 'logs' / 'algo_agent.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class DataCollector:
    """Real-time market data ingestion via WebSocket."""

    def __init__(self, broker, instrument_tokens: List[int]):
        self.broker = broker
        self.instrument_tokens = instrument_tokens
        self.ticks: List[Dict] = []
        self.rolling_window: List[Dict] = []
        self.max_window = 1000
        self.callbacks: List[Callable] = []
        self.is_running = False
        self._lock = Lock()

    def register_tick_callback(self, callback: Callable):
        self.callbacks.append(callback)

    def on_tick(self, tick: Dict):
        with self._lock:
            self.ticks.append({**tick, "received_at": datetime.now().isoformat()})
            self.rolling_window.append(tick)
            if len(self.rolling_window) > self.max_window:
                self.rolling_window.pop(0)

        self._store_tick(tick)
        for cb in self.callbacks:
            try:
                cb(tick)
            except Exception as e:
                logger.error(f"Tick callback error: {e}")

    def _store_tick(self, tick: Dict):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO ticks (timestamp, instrument, ltp, volume)
            VALUES (?, ?, ?, ?)
        ''', (tick.get('timestamp', datetime.now().isoformat()),
              tick.get('instrument', 'UNKNOWN'),
              tick.get('ltp', 0),
              tick.get('volume', 0)))
        conn.commit()
        conn.close()

    def start(self):
        self.is_running = True
        if hasattr(self.broker, 'connect_websocket'):
            Thread(target=self._ws_loop, daemon=True).start()
        logger.info("DataCollector started")

    def _ws_loop(self):
        try:
            self.broker.connect_websocket(self.on_tick, self.instrument_tokens)
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            time.sleep(5)
            if self.is_running:
                self._ws_loop()

    def stop(self):
        self.is_running = False
        logger.info("DataCollector stopped")

    def get_latest_price(self, instrument: str) -> Optional[float]:
        with self._lock:
            for tick in reversed(self.rolling_window):
                if tick.get('instrument') == instrument:
                    return tick.get('ltp')
        return None


class SignalEngine:
    """Generates trading signals from approved strategy logic."""

    def __init__(self, strategy_logic, config: Dict):
        self.strategy = strategy_logic
        self.config = config
        self.last_signal = None
        self.signal_count = 0
        logger.info(f"SignalEngine initialized with {strategy_logic.STRATEGY_ID}/{strategy_logic.APPROACH_ID}")

    def process_tick(self, tick: Dict) -> Optional[Dict]:
        data = self._prepare_data(tick)
        signal = self.strategy.get_entry_signal(data)

        if signal:
            self.last_signal = signal
            self.signal_count += 1
            logger.info(f"Signal #{self.signal_count}: {signal}")
            return signal

        return None

    def check_exit(self, position: Dict, current_price: float) -> Optional[Dict]:
        data = self._prepare_data({"ltp": current_price})
        return self.strategy.get_exit_signal(position, data)

    def _prepare_data(self, tick: Dict) -> Dict:
        return {
            "timestamp": tick.get('timestamp', datetime.now().isoformat()),
            "open": tick.get('open', tick.get('ltp')),
            "high": tick.get('high', tick.get('ltp')),
            "low": tick.get('low', tick.get('ltp')),
            "close": tick.get('close', tick.get('ltp')),
            "volume": tick.get('volume', 0),
            "ltp": tick.get('ltp', 0)
        }


class OrderManager:
    """Order placement, modification, cancellation, with retry logic."""

    def __init__(self, broker, position_tracker):
        self.broker = broker
        self.position_tracker = position_tracker
        self.pending_orders: List[Dict] = []
        self.filled_orders: List[Dict] = []
        self.order_counter = 0
        self.max_retries = 3
        self.retry_delay = 0.5

    def place_order(self, instrument: str, side: str, quantity: int,
                    order_type: str = "MARKET", limit_price: Optional[float] = None,
                    option_type: str = "CE") -> Optional[Dict]:
        self.order_counter += 1
        order_id = f"LIVE_{self.order_counter:06d}"

        position = self.position_tracker.get_position(instrument)
        if position and side == "BUY":
            max_lots = self.position_tracker.max_positions - self.position_tracker.get_open_count()
            if quantity > max_lots:
                logger.warning(f"Position limit exceeded. Reducing quantity from {quantity} to {max_lots}")
                quantity = max_lots

        for attempt in range(self.max_retries):
            try:
                if order_type == "MARKET":
                    order = self.broker.place_market_order(instrument, side, quantity, option_type)
                elif order_type == "LIMIT":
                    order = self.broker.place_limit_order(instrument, side, quantity, limit_price, option_type)
                else:
                    order = self.broker.place_sl_order(instrument, side, quantity, limit_price, option_type)

                order["order_id"] = order_id
                self.pending_orders.append(order)
                logger.info(f"Order {order_id} placed: {side} {quantity} {instrument}")
                return order

            except Exception as e:
                logger.error(f"Order attempt {attempt+1} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)

        logger.error(f"Order {order_id} failed after {self.max_retries} attempts")
        return None

    def check_order_status(self, order_id: str) -> Optional[Dict]:
        for order in self.pending_orders:
            if order.get("order_id") == order_id:
                status = self.broker.get_order_status(order_id)
                if status in ["FILLED", "REJECTED", "CANCELLED"]:
                    self.pending_orders.remove(order)
                    if status == "FILLED":
                        self.filled_orders.append(order)
                return order
        return None

    def cancel_order(self, order_id: str) -> bool:
        try:
            self.broker.cancel_order(order_id)
            self.pending_orders = [o for o in self.pending_orders if o.get("order_id") != order_id]
            logger.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Cancel failed for {order_id}: {e}")
            return False


class PositionTracker:
    """Real-time position book with live P&L tracking."""

    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.positions: List[Dict] = []
        self.closed_trades: List[Dict] = []
        self.max_positions = 3
        self.daily_pnl = 0.0
        self.cash = initial_capital

    def open_position(self, order: Dict, current_price: float):
        position = {
            "order_id": order.get("order_id"),
            "instrument": order.get("instrument"),
            "strike": order.get("strike", 0),
            "option_type": order.get("option_type", "CE"),
            "side": order.get("side"),
            "quantity": order.get("quantity", 1),
            "entry_price": order.get("fill_price", current_price),
            "current_price": current_price,
            "timestamp": datetime.now().isoformat()
        }
        self.positions.append(position)
        logger.info(f"Position opened: {position}")

    def close_position(self, position: Dict, exit_price: float, charges: float):
        pnl = (exit_price - position["entry_price"]) * position["quantity"] * 15
        if position["side"] == "SELL":
            pnl = -pnl
        pnl -= charges

        trade = {**position, "exit_price": exit_price, "pnl": pnl,
                 "exit_time": datetime.now().isoformat()}
        self.closed_trades.append(trade)
        self.positions.remove(position)
        self.daily_pnl += pnl
        self.cash += pnl
        logger.info(f"Position closed: P&L = {pnl:.2f}")

    def update_prices(self, prices: Dict):
        for pos in self.positions:
            inst = pos["instrument"]
            if inst in prices:
                pos["current_price"] = prices[inst]

    def get_position(self, instrument: str) -> Optional[Dict]:
        for pos in self.positions:
            if pos["instrument"] == instrument:
                return pos
        return None

    def get_open_count(self) -> int:
        return len(self.positions)

    def get_live_pnl(self) -> float:
        pnl = 0.0
        for pos in self.positions:
            diff = pos["current_price"] - pos["entry_price"]
            if pos["side"] == "SELL":
                diff = -diff
            pnl += diff * pos["quantity"] * 15
        return pnl

    def square_off_all(self, current_prices: Dict):
        for pos in list(self.positions):
            price = current_prices.get(pos["instrument"], pos["current_price"])
            self.close_position(pos, price, 0)

    def auto_squareoff(self, broker):
        if datetime.now().time() > dt_time(15, 20):
            logger.info("Auto square-off triggered")
            for pos in list(self.positions):
                broker.place_market_order(pos["instrument"], "SELL" if pos["side"] == "BUY" else "BUY",
                                          pos["quantity"], pos["current_price"], pos.get("option_type", "CE"))


class RiskManager:
    """Stop-loss, exposure limits, kill switch."""

    def __init__(self, config: Dict):
        self.max_daily_loss = config.get("max_daily_loss", 5000)
        self.max_open_positions = config.get("max_open_positions", 3)
        self.max_margin_utilization = config.get("max_margin_utilization", 0.8)
        self.max_per_trade_loss = config.get("max_per_trade_loss", 3000)
        self.kill_switch_activated = False
        self.alerts: List[str] = []

    def check_entry(self, position_tracker: PositionTracker, order_value: float) -> bool:
        if self.kill_switch_activated:
            logger.warning("Kill switch active — entry blocked")
            return False

        daily_loss = abs(position_tracker.daily_pnl)
        if daily_loss >= self.max_daily_loss:
            logger.warning(f"Daily loss limit hit: {daily_loss} >= {self.max_daily_loss}")
            self.alerts.append(f"Daily loss limit hit: ₹{daily_loss}")
            return False

        if position_tracker.get_open_count() >= self.max_open_positions:
            logger.warning("Max open positions reached")
            return False

        margin_used = position_tracker.cash * (1 - self.max_margin_utilization)
        if order_value > margin_used:
            logger.warning(f"Margin insufficient: {order_value} > {margin_used}")
            return False

        return True

    def check_exit_loss(self, position: Dict) -> bool:
        entry_price = position["entry_price"]
        current_price = position["current_price"]
        diff = abs(current_price - entry_price) * position["quantity"] * 15

        if diff >= self.max_per_trade_loss:
            logger.warning(f"Per-trade loss limit hit: {diff} >= {self.max_per_trade_loss}")
            self.alerts.append(f"Trade loss limit hit: ₹{diff:.0f}")
            return True
        return False

    def activate_kill_switch(self, message: str = ""):
        self.kill_switch_activated = True
        self.alerts.append(f"KILL SWITCH ACTIVATED: {message}")
        logger.critical(f"KILL SWITCH ACTIVATED: {message}")

    def reset_kill_switch(self):
        self.kill_switch_activated = False
        self.alerts.append("Kill switch reset")
        logger.info("Kill switch reset")


class TradeLogger:
    """Logs every trade, signal, tick to SQLite."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        self._init_tables()

    def _init_tables(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS signals
                     (id INTEGER PRIMARY KEY, timestamp TEXT, signal TEXT, strike INTEGER,
                      option_type TEXT, lots INTEGER, confidence REAL, reason TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS orders
                     (id INTEGER PRIMARY KEY, timestamp TEXT, order_id TEXT, instrument TEXT,
                      side TEXT, quantity INTEGER, fill_price REAL, charges REAL,
                      status TEXT, strategy_id TEXT, approach_id TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS positions
                     (id INTEGER PRIMARY KEY, timestamp TEXT, instrument TEXT, strike INTEGER,
                      side TEXT, quantity INTEGER, entry_price REAL, current_price REAL,
                      unrealized_pnl REAL, status TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS pnl_snapshots
                     (id INTEGER PRIMARY KEY, timestamp TEXT, realized_pnl REAL,
                      unrealized_pnl REAL, total_pnl REAL, margin_used REAL,
                      drawdown_pct REAL)''')

        conn.commit()
        conn.close()

    def log_signal(self, signal: Dict):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT INTO signals (timestamp, signal, strike, option_type, lots, confidence, reason)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (datetime.now().isoformat(), signal.get("signal"), signal.get("strike"),
                   signal.get("option_type"), signal.get("lots"), signal.get("confidence"),
                   signal.get("reason")))
        conn.commit()
        conn.close()

    def log_order(self, order: Dict, strategy_id: str = "", approach_id: str = ""):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT INTO orders (timestamp, order_id, instrument, side, quantity, fill_price,
                                      charges, status, strategy_id, approach_id)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (datetime.now().isoformat(), order.get("order_id"), order.get("instrument"),
                   order.get("side"), order.get("quantity"), order.get("fill_price"),
                   order.get("charges", {}).get("total_charges", 0), order.get("status"),
                   strategy_id, approach_id))
        conn.commit()
        conn.close()

    def log_position(self, position: Dict):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT INTO positions (timestamp, instrument, strike, side, quantity,
                                        entry_price, current_price, unrealized_pnl, status)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (datetime.now().isoformat(), position.get("instrument"), position.get("strike"),
                   position.get("side"), position.get("quantity"), position.get("entry_price"),
                   position.get("current_price"), position.get("unrealized_pnl", 0), "OPEN"))
        conn.commit()
        conn.close()

    def log_pnl_snapshot(self, realized: float, unrealized: float, margin: float, drawdown: float):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT INTO pnl_snapshots (timestamp, realized_pnl, unrealized_pnl, total_pnl,
                                             margin_used, drawdown_pct)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (datetime.now().isoformat(), realized, unrealized, realized + unrealized,
                   margin, drawdown))
        conn.commit()
        conn.close()


class AlgoAgent:
    """Master algo trading system — coordinates all core components."""

    def __init__(self, strategy_logic, broker, config: Dict):
        self.strategy_logic = strategy_logic
        self.broker = broker
        self.config = config

        self.trade_logger = TradeLogger()
        self.position_tracker = PositionTracker(config.get("initial_capital", 100000))
        self.risk_manager = RiskManager(config)

        self.data_collector = DataCollector(broker, config.get("instrument_tokens", [260105]))
        self.signal_engine = SignalEngine(strategy_logic, config)
        self.order_manager = OrderManager(broker, self.position_tracker)

        self.is_running = False
        self.trading_hours_start = dt_time(9, 15)
        self.trading_hours_end = dt_time(15, 30)

        self.data_collector.register_tick_callback(self.on_tick)
        logger.info("AlgoAgent initialized")

    def on_tick(self, tick: Dict):
        if not self.is_running:
            return

        current_time = datetime.now().time()
        if current_time < self.trading_hours_start or current_time > self.trading_hours_end:
            if self.position_tracker.get_open_count() > 0:
                logger.info("Outside trading hours — squaring off positions")
                self.risk_manager.activate_kill_switch("Outside trading hours")
                self.shutdown()
            return

        signal = self.signal_engine.process_tick(tick)
        if signal and signal.get("signal") in ["BUY", "SELL"]:
            self._execute_signal(signal, tick)

        self._check_exit_conditions(tick)

        if self.risk_manager.kill_switch_activated:
            self._emergency_exit()

    def _execute_signal(self, signal: Dict, tick: Dict):
        order_value = signal.get("lots", 1) * 15 * (tick.get("ltp", 45000) * 0.3)

        if not self.risk_manager.check_entry(self.position_tracker, order_value):
            logger.warning(f"Entry blocked by risk manager: {signal}")
            return

        self.trade_logger.log_signal(signal)

        order = self.order_manager.place_order(
            instrument=f"BANKNIFTY_{signal.get('strike')}_{signal.get('option_type')}",
            side=signal["signal"],
            quantity=signal.get("lots", 1),
            option_type=signal.get("option_type", "CE")
        )

        if order:
            self.trade_logger.log_order(order, self.strategy_logic.STRATEGY_ID,
                                        self.strategy_logic.APPROACH_ID)
            self.position_tracker.open_position(order, tick.get("ltp", 0))

    def _check_exit_conditions(self, tick: Dict):
        for pos in list(self.position_tracker.positions):
            if self.risk_manager.check_exit_loss(pos):
                logger.info(f"Stop-loss triggered for {pos['instrument']}")
                self.order_manager.place_order(
                    pos["instrument"], "SELL" if pos["side"] == "BUY" else "BUY",
                    pos["quantity"], "MARKET", option_type=pos.get("option_type", "CE")
                )

    def _emergency_exit(self):
        logger.critical("EMERGENCY EXIT — all positions being squared off")
        current_prices = {pos["instrument"]: pos["current_price"]
                          for pos in self.position_tracker.positions}
        self.position_tracker.square_off_all(current_prices)

    def start(self):
        self.is_running = True
        self.data_collector.start()
        logger.info("AlgoAgent started — live trading active")

    def stop(self):
        self.is_running = False
        self.position_tracker.auto_squareoff(self.broker)
        self.data_collector.stop()
        logger.info("AlgoAgent stopped")

    def shutdown(self):
        self.stop()
        logger.info("AlgoAgent shutdown complete")


if __name__ == "__main__":
    print("AlgoAgent module loaded. Import and initialize with a broker and strategy.")