"""
PaperTrading Broker — Simulates broker behavior locally for backtesting and simulation.
Implements identical interface to ZerodhaBroker for seamless mode switching.
"""
import random
import logging
import time
from datetime import datetime, time as dt_time
from typing import Dict, List, Optional
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.FileHandler(Path(__file__).parent.parent.parent / 'logs' / 'paper_trading.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class PaperTradingBroker:
    """Simulates broker fills locally — used for backtesting and live simulation."""

    LOT_SIZE = 15
    SLIPPAGE = 0.0005  # 0.05% — user specified slippage
    # Brokerage model: ₹5 flat per side + 6.5% GST + 0.01% SEBI + 0.05% STT (sell side only)
    BROKERAGE_FLAT = 5.0
    GST_PCT = 0.065
    STT_PCT = 0.0005
    SEBI_PCT = 0.0001

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.is_connected = True  # Always connected in paper mode
        self.balance = self.config.get("initial_capital", 100000)
        self.positions: List[Dict] = []
        self.orders: List[Dict] = []
        self.order_counter = 0
        self.trading_hours_start = dt_time(9, 15)
        self.trading_hours_end = dt_time(15, 30)
        self.current_prices: Dict[str, float] = {}
        logger.info("PaperTrading broker initialized (SIMULATION MODE)")

    def login(self) -> bool:
        """Paper trading is always 'logged in'."""
        logger.info("PaperTrading: Login successful (simulation mode)")
        return True

    def get_instruments(self) -> List[Dict]:
        """Return simulated instrument list."""
        return [
            {"instrument_token": 260105, "tradingsymbol": "BANKNIFTY", "exchange": "NSE"},
            {"instrument_token": 260105, "tradingsymbol": "BANKNIFTY26MAY45000CE", "exchange": "NFO"},
            {"instrument_token": 260106, "tradingsymbol": "BANKNIFTY26MAY44800CE", "exchange": "NFO"},
            {"instrument_token": 260107, "tradingsymbol": "BANKNIFTY26MAY45000PE", "exchange": "NFO"},
        ]

    def get_quote(self, instrument_token: int) -> Dict:
        """Return simulated quote."""
        symbol = self._get_symbol_from_token(instrument_token)
        price = self.current_prices.get(symbol, 45000)
        return {
            "instrument_token": instrument_token,
            "last_price": price,
            "bid": price - 0.5,
            "ask": price + 0.5,
            "volume": random.randint(10000, 100000),
            "timestamp": datetime.now().isoformat()
        }

    def _get_symbol_from_token(self, token: int) -> str:
        token_map = {260105: "BANKNIFTY", 260106: "BANKNIFTY_CE", 260107: "BANKNIFTY_PE"}
        return token_map.get(token, "BANKNIFTY")

    def place_market_order(self, instrument: str, side: str, quantity: int,
                           option_type: str = "CE") -> Dict:
        """Simulate a market order fill with slippage."""
        self.order_counter += 1
        order_id = f"PAPER_{self.order_counter:06d}"

        base_price = self._get_current_price(instrument, option_type)
        slippage = base_price * self.SLIPPAGE
        fill_price = base_price + slippage if side == "BUY" else base_price - slippage

        turnover = fill_price * quantity * self.LOT_SIZE
        brokerage = self.BROKERAGE_FLAT
        gst = brokerage * self.GST_PCT
        stt = turnover * self.STT_PCT if side == "SELL" else 0
        sebi = turnover * self.SEBI_PCT
        total_charges = brokerage + gst + stt + sebi

        required_margin = turnover * 0.2 if side == "BUY" else turnover * 0.15

        if side == "BUY" and self.balance < required_margin + total_charges:
            logger.warning(f"Insufficient margin for {order_id}: need ₹{required_margin:.0f}, have ₹{self.balance:.0f}")
            return {"status": "REJECTED", "reason": "Insufficient margin", "order_id": order_id}

        if side == "BUY":
            self.balance -= (required_margin + total_charges)
        # SELL positions: margin blocked at entry, released at exit

        order = {
            "order_id": order_id,
            "instrument": instrument,
            "side": side,
            "quantity": quantity,
            "option_type": option_type,
            "fill_price": round(fill_price, 2),
            "charges": {
                "brokerage": round(brokerage, 2),
                "stt": round(stt, 2),
                "gst": round(gst, 2),
                "sebi_charges": round(sebi, 2),
                "total_charges": round(total_charges, 2)
            },
            "status": "FILLED",
            "timestamp": datetime.now().isoformat(),
            "filled_quantity": quantity
        }
        self.orders.append(order)

        self.positions.append({
            "order_id": order_id,
            "instrument": instrument,
            "option_type": option_type,
            "side": side,
            "quantity": quantity,
            "entry_price": fill_price,
            "current_price": fill_price,
            "timestamp": datetime.now().isoformat()
        })

        logger.info(f"PaperOrder FILLED: {order_id} {side} {quantity} {instrument} @ {fill_price}")
        return order

    def place_limit_order(self, instrument: str, side: str, quantity: int,
                          price: float, option_type: str = "CE") -> Dict:
        """Simulate a limit order."""
        self.order_counter += 1
        order_id = f"PAPER_{self.order_counter:06d}"

        order = {
            "order_id": order_id,
            "instrument": instrument,
            "side": side,
            "quantity": quantity,
            "option_type": option_type,
            "limit_price": price,
            "fill_price": None,
            "status": "PENDING",
            "timestamp": datetime.now().isoformat(),
            "filled_quantity": 0
        }
        self.orders.append(order)
        logger.info(f"PaperOrder PENDING: {order_id} {side} {quantity} {instrument} @ limit {price}")
        return order

    def place_sl_order(self, instrument: str, side: str, quantity: int,
                       trigger_price: float, option_type: str = "CE") -> Dict:
        """Simulate a stop-loss order."""
        return self.place_limit_order(instrument, side, quantity, trigger_price, option_type)

    def check_pending_orders(self):
        """Check and fill pending orders based on current prices."""
        filled = []
        for order in self.orders:
            if order["status"] == "PENDING" and order["limit_price"]:
                current = self._get_current_price(order["instrument"], order.get("option_type", "CE"))
                if order["side"] == "BUY" and current >= order["limit_price"]:
                    order["fill_price"] = order["limit_price"] * (1 + self.SLIPPAGE)
                    order["status"] = "FILLED"
                    order["filled_quantity"] = order["quantity"]
                    filled.append(order["order_id"])
                elif order["side"] == "SELL" and current <= order["limit_price"]:
                    order["fill_price"] = order["limit_price"] * (1 - self.SLIPPAGE)
                    order["status"] = "FILLED"
                    order["filled_quantity"] = order["quantity"]
                    filled.append(order["order_id"])
        return filled

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        for order in self.orders:
            if order["order_id"] == order_id and order["status"] == "PENDING":
                order["status"] = "CANCELLED"
                logger.info(f"PaperOrder CANCELLED: {order_id}")
                return True
        return False

    def get_order_status(self, order_id: str) -> str:
        """Get order status."""
        for order in self.orders:
            if order["order_id"] == order_id:
                return order.get("status", "UNKNOWN")
        return "NOT_FOUND"

    def get_positions(self) -> List[Dict]:
        """Get simulated open positions."""
        return self.positions.copy()

    def get_balance(self) -> Dict:
        """Get simulated balance and margin."""
        unrealized_pnl = sum(
            (p["current_price"] - p["entry_price"]) * p["quantity"] * self.LOT_SIZE
            if p["side"] == "BUY" else
            (p["entry_price"] - p["current_price"]) * p["quantity"] * self.LOT_SIZE
            for p in self.positions
        )
        return {
            "cash": self.balance,
            "available_margin": self.balance,
            "used_margin": sum(
                p["entry_price"] * p["quantity"] * self.LOT_SIZE * 0.2 for p in self.positions
            ),
            "unrealized_pnl": round(unrealized_pnl, 2)
        }

    def connect_websocket(self, callback, instrument_tokens: List[int]):
        """Simulate WebSocket by generating random ticks."""
        logger.info(f"PaperTrading WebSocket started (simulated) for tokens: {instrument_tokens}")
        import threading

        def tick_generator():
            while True:
                for token in instrument_tokens:
                    symbol = self._get_symbol_from_token(token)
                    base = self.current_prices.get(symbol, 45000)
                    tick = {
                        "instrument_token": token,
                        "last_price": round(base * (1 + random.uniform(-0.001, 0.001)), 2),
                        "volume": random.randint(1000, 10000),
                        "timestamp": datetime.now().isoformat()
                    }
                    callback(tick)
                time.sleep(1)

        thread = threading.Thread(target=tick_generator, daemon=True)
        thread.start()

    def update_price(self, instrument: str, price: float):
        """Update current price for an instrument (used by simulation engine)."""
        self.current_prices[instrument] = price

    def _get_current_price(self, instrument: str, option_type: str = "CE") -> float:
        """Get current price from cache or generate realistic price."""
        if instrument in self.current_prices:
            return self.current_prices[instrument]

        base = 45000
        if option_type == "CE":
            base = random.uniform(100, 500)
        else:
            base = random.uniform(100, 500)

        return base

    def reset(self):
        """Reset broker state for new backtest."""
        self.orders = []
        self.positions = []
        self.order_counter = 0
        self.balance = self.config.get("initial_capital", 100000)
        logger.info("PaperTrading broker reset")


if __name__ == "__main__":
    broker = PaperTradingBroker()
    order = broker.place_market_order("BANKNIFTY45000CE", "BUY", 1, "CE")
    print(f"Paper order: {order['order_id']}, Status: {order['status']}")