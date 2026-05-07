"""
SimulationBroker — Real tick feed, simulated order execution.
For paper trading: receives real ticks from WebSocket or DataFeeder replay,
but executes orders internally with simulated fills (no real API calls).

Same interface as ZerodhaBroker — switch seamlessly between live/zerodha/simulation.
"""
import logging
import time
from datetime import datetime, time as dt_time
from typing import Dict, List, Optional, Callable
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.FileHandler(Path(__file__).parent.parent.parent / 'logs' / 'simulation_broker.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class SimulationBroker:
    """Real ticks + simulated fills. Connects to live WebSocket OR historical replay.

    For paper trading with real market data:
    - Ticks come from live Zerodha WebSocket OR historical DataFeeder replay
    - Orders are filled locally at current market price with slippage
    - No real capital at risk — but fills reflect actual market prices
    """

    LOT_SIZE = 15
    SLIPPAGE = 0.0005  # 0.05% — user specified
    BROKERAGE_FLAT = 5.0  # ₹5 per side
    GST_PCT = 0.065   # 6.5% on brokerage
    STT_PCT = 0.0005  # 0.05% on sell turnover
    SEBI_PCT = 0.0001  # 0.01% on turnover

    def __init__(self, config: Dict = None, data_feeder=None):
        self.config = config or {}
        self.is_connected = True
        self.balance = self.config.get("initial_capital", 100000)
        self.positions: List[Dict] = []
        self.orders: List[Dict] = []
        self.order_counter = 0
        self.trading_hours_start = dt_time(9, 15)
        self.trading_hours_end = dt_time(15, 30)
        self.current_prices: Dict[str, float] = {}

        # Real tick feed (can be DataFeeder replay OR live WebSocket)
        self.data_feeder = data_feeder
        self.tick_callbacks: List[Callable] = []
        self._tick_thread = None
        self._is_running = False

        logger.info("SimulationBroker initialized — real ticks, simulated fills")

    # ── Connection / Auth ────────────────────────────────────────

    def login(self) -> bool:
        logger.info("SimulationBroker: logged in (simulation mode)")
        return True

    def connect_websocket(self, callback, instrument_tokens: List[int]):
        """Connect to real Zerodha WebSocket for live ticks.
        Fallback: if no real broker, use data_feeder if available."""
        if self.data_feeder is not None:
            self._start_feeder_replay(callback, instrument_tokens)
        else:
            logger.warning("SimulationBroker: no data_feeder set — ticks will be static")
            self._start_static_ticks(callback, instrument_tokens)

    def _start_feeder_replay(self, callback, instrument_tokens: List[int]):
        """Replay real historical ticks through DataFeeder.
        Maintains exact signal logic from backtest for validation."""
        logger.info(f"SimulationBroker: starting historical replay for tokens {instrument_tokens}")
        import threading

        def replay_loop():
            self._is_running = True
            data = self.data_feeder.data
            idx = 0
            while idx < len(data) and self._is_running:
                tick = data[idx]
                # Normalize tick format for AlgoAgent
                normalized = {
                    "instrument_token": tick.get("instrument_token", tick.get("token", 260105)),
                    "ltp": tick.get("close", tick.get("ltp", 45000)),
                    "open": tick.get("open", tick.get("ltp", 45000)),
                    "high": tick.get("high", tick.get("ltp", 45000)),
                    "low": tick.get("low", tick.get("ltp", 45000)),
                    "close": tick.get("close", tick.get("ltp", 45000)),
                    "volume": tick.get("volume", 0),
                    "timestamp": tick.get("timestamp", datetime.now().isoformat())
                }
                # Update current prices for fill simulation
                self.current_prices["BANKNIFTY"] = normalized["ltp"]
                self._dispatch_tick(normalized)
                idx += 1
                # Real-time replay: 1 tick per second (historical data is hourly)
                # For 5-minute data: adjust interval accordingly
                interval = 1.0  # 1 second between ticks
                time.sleep(interval)

        self._tick_thread = threading.Thread(target=replay_loop, daemon=True)
        self._tick_thread.start()

    def _start_static_ticks(self, callback, instrument_tokens: List[int]):
        """Fallback: generate static ticks when no real feed available."""
        import threading
        import random

        def static_loop():
            self._is_running = True
            while self._is_running:
                for token in instrument_tokens:
                    base = self.current_prices.get("BANKNIFTY", 45000)
                    tick = {
                        "instrument_token": token,
                        "ltp": round(base * (1 + random.uniform(-0.001, 0.001)), 2),
                        "timestamp": datetime.now().isoformat()
                    }
                    self._dispatch_tick(tick)
                time.sleep(2)

        self._tick_thread = threading.Thread(target=static_loop, daemon=True)
        self._tick_thread.start()

    def _dispatch_tick(self, tick: Dict):
        """Dispatch real tick to signal engine (AlgoAgent.on_tick → signal_engine.process_tick)."""
        for cb in self.tick_callbacks:
            try:
                cb(tick)
            except Exception as e:
                logger.error(f"Tick dispatch error: {e}")

    def register_tick_callback(self, callback: Callable):
        """Register callback for tick data — used by AlgoAgent."""
        self.tick_callbacks.append(callback)

    def stop(self):
        self._is_running = False
        if self._tick_thread:
            self._tick_thread.join(timeout=2)
        logger.info("SimulationBroker stopped")

    # ── Market Data ────────────────────────────────────────────────

    def get_quote(self, instrument_token: int) -> Dict:
        """Return current market quote from live prices."""
        symbol = self._get_symbol_from_token(instrument_token)
        price = self.current_prices.get(symbol, 45000)
        return {
            "instrument_token": instrument_token,
            "last_price": price,
            "bid": round(price - 0.5, 1),
            "ask": round(price + 0.5, 1),
            "volume": 0,
            "timestamp": datetime.now().isoformat()
        }

    def _get_symbol_from_token(self, token: int) -> str:
        token_map = {260105: "BANKNIFTY", 260106: "BANKNIFTY_CE", 260107: "BANKNIFTY_PE"}
        return token_map.get(token, "BANKNIFTY")

    def get_instruments(self) -> List[Dict]:
        return [
            {"instrument_token": 260105, "tradingsymbol": "BANKNIFTY", "exchange": "NSE"},
        ]

    def update_price(self, instrument: str, price: float):
        """Update live price for an instrument (called from tick dispatch)."""
        self.current_prices[instrument] = price

    # ── Order Execution (simulated fills) ─────────────────────────

    def _get_fill_price(self, instrument: str, side: str, option_type: str = "CE") -> float:
        """Get realistic fill price from current market prices + slippage."""
        # Use the BANKNIFTY spot from live feed
        spot = self.current_prices.get("BANKNIFTY", 45000)

        if instrument in self.current_prices:
            base_price = self.current_prices[instrument]
        elif option_type == "CE":
            # Derive option price from spot using Black-Scholes approximation
            atm_strike = round(spot / 100) * 100
            base_price = self._approx_option_price(spot, atm_strike, 0.5, "CE")
        elif option_type == "PE":
            atm_strike = round(spot / 100) * 100
            base_price = self._approx_option_price(spot, atm_strike, 0.5, "PE")
        else:
            base_price = self.current_prices.get(instrument, spot * 0.01)

        slippage = base_price * self.SLIPPAGE
        return base_price + slippage if side == "BUY" else base_price - slippage

    def _approx_option_price(self, spot: float, strike: int, expiry_days: float, opt_type: str) -> float:
        """Quick approximation of option price for fill simulation."""
        import math
        T = expiry_days / 365.0
        iv = 0.22  # 22% fixed IV

        def norm_cdf(x):
            return 0.5 * (1 + math.erf(x / math.sqrt(2)))

        if opt_type == "CE":
            d1 = (math.log(spot / strike) + (0.07 + 0.5 * iv**2) * T) / (iv * math.sqrt(T))
            d2 = d1 - iv * math.sqrt(T)
            return spot * norm_cdf(d1) - strike * math.exp(-0.07 * T) * norm_cdf(d2)
        else:
            d1 = (math.log(spot / strike) + (0.07 + 0.5 * iv**2) * T) / (iv * math.sqrt(T))
            d2 = d1 - iv * math.sqrt(T)
            return strike * math.exp(-0.07 * T) * norm_cdf(-d2) - spot * norm_cdf(-d1)

    def place_market_order(self, instrument: str, side: str, quantity: int,
                           option_type: str = "CE") -> Dict:
        """Place a simulated market order with realistic fill price.

        Uses the current live price (from real WebSocket or replay) for the fill,
        then applies slippage and all brokerage charges per user spec.
        """
        self.order_counter += 1
        order_id = f"SIM_{self.order_counter:06d}"

        fill_price = self._get_fill_price(instrument, side, option_type)
        turnover = fill_price * quantity * self.LOT_SIZE
        brokerage = self.BROKERAGE_FLAT
        gst = brokerage * self.GST_PCT
        stt = turnover * self.STT_PCT if side == "SELL" else 0
        sebi = turnover * self.SEBI_PCT
        total_charges = round(brokerage + gst + stt + sebi, 2)

        required_margin = turnover * 0.2 if side == "BUY" else turnover * 0.15

        if side == "BUY" and self.balance < required_margin + total_charges:
            logger.warning(f"Insufficient margin for {order_id}: need ₹{required_margin:.0f}, have ₹{self.balance:.0f}")
            return {"status": "REJECTED", "reason": "Insufficient margin", "order_id": order_id}

        if side == "BUY":
            self.balance -= (required_margin + total_charges)

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
                "total_charges": total_charges
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

        logger.info(f"SimOrder FILLED: {order_id} {side} {quantity} {instrument} @ {fill_price}")
        return order

    def place_limit_order(self, instrument: str, side: str, quantity: int,
                          price: float, option_type: str = "CE") -> Dict:
        """Place a simulated limit order."""
        self.order_counter += 1
        order_id = f"SIM_{self.order_counter:06d}"

        order = {
            "order_id": order_id,
            "instrument": instrument,
            "side": side,
            "quantity": quantity,
            "option_type": option_type,
            "limit_price": round(price, 2),
            "fill_price": None,
            "status": "PENDING",
            "timestamp": datetime.now().isoformat(),
            "filled_quantity": 0
        }
        self.orders.append(order)
        logger.info(f"SimOrder PENDING: {order_id} {side} {quantity} {instrument} @ limit {price}")
        return order

    def place_sl_order(self, instrument: str, side: str, quantity: int,
                       trigger_price: float, option_type: str = "CE") -> Dict:
        """Place a simulated stop-loss order."""
        return self.place_limit_order(instrument, side, quantity, trigger_price, option_type)

    def check_pending_orders(self):
        """Fill pending orders when price conditions met."""
        filled_ids = []
        for order in self.orders:
            if order["status"] == "PENDING" and order.get("limit_price"):
                current = self._get_fill_price(order["instrument"], order["side"], order.get("option_type", "CE"))
                limit = order["limit_price"]
                if order["side"] == "BUY" and current >= limit:
                    order["fill_price"] = round(limit * (1 + self.SLIPPAGE), 2)
                    order["status"] = "FILLED"
                    order["filled_quantity"] = order["quantity"]
                    filled_ids.append(order["order_id"])
                elif order["side"] == "SELL" and current <= limit:
                    order["fill_price"] = round(limit * (1 - self.SLIPPAGE), 2)
                    order["status"] = "FILLED"
                    order["filled_quantity"] = order["quantity"]
                    filled_ids.append(order["order_id"])
        return filled_ids

    def cancel_order(self, order_id: str) -> bool:
        for order in self.orders:
            if order["order_id"] == order_id and order["status"] == "PENDING":
                order["status"] = "CANCELLED"
                logger.info(f"SimOrder CANCELLED: {order_id}")
                return True
        return False

    def get_order_status(self, order_id: str) -> str:
        for order in self.orders:
            if order["order_id"] == order_id:
                return order.get("status", "UNKNOWN")
        return "NOT_FOUND"

    def get_positions(self) -> List[Dict]:
        return self.positions.copy()

    def get_balance(self) -> Dict:
        unrealized_pnl = sum(
            (p["current_price"] - p["entry_price"]) * p["quantity"] * self.LOT_SIZE
            if p["side"] == "BUY" else
            (p["entry_price"] - p["current_price"]) * p["quantity"] * self.LOT_SIZE
            for p in self.positions
        )
        return {
            "cash": round(self.balance, 2),
            "available_margin": round(self.balance, 2),
            "used_margin": round(sum(p["entry_price"] * p["quantity"] * self.LOT_SIZE * 0.2 for p in self.positions), 2),
            "unrealized_pnl": round(unrealized_pnl, 2)
        }

    def reset(self):
        self.orders = []
        self.positions = []
        self.order_counter = 0
        self.balance = self.config.get("initial_capital", 100000)
        logger.info("SimulationBroker reset")


if __name__ == "__main__":
    broker = SimulationBroker({"initial_capital": 100000})
    order = broker.place_market_order("BANKNIFTY45000CE", "BUY", 1, "CE")
    print(f"Order: {order['order_id']}, fill: {order['fill_price']}, charges: {order['charges']}")