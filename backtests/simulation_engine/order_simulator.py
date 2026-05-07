"""
OrderSimulator — Simulates order placement, fills, and brokerage for backtesting.
Applies realistic slippage, brokerage, STT, GST, SEBI charges.
"""
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.FileHandler(Path(__file__).parent.parent.parent / 'logs' / 'order_simulator.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SLM = "SLM"

class OrderStatus(Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    PARTIAL = "PARTIAL"


class OrderSimulator:
    """Simulates order lifecycle with realistic fills and charges."""

    BROKERAGE_FLAT = 5.0  # ₹5 per side (buy or sell) — user specified
    GST_PCT = 0.065  # 6.5% GST on brokerage (user specified)
    STT_PCT = 0.0005  # 0.05% STT on sell side for options
    SEBI_CHARGES = 0.0001  # 0.01% of turnover
    SLIPPAGE_PCT = 0.0005  # 0.05%

    def calculate_charges(self, price: float, side: str = "BUY") -> Dict:
        """Calculate all charges for a trade.

        Brokerage: flat ₹5 per side (buy or sell)
        Govt charges: 6.5% GST + 0.01% SEBI + 0.05% STT (sell side only)
        """
        turnover = price * self.lot_size
        brokerage = self.BROKERAGE_FLAT  # flat ₹5 per side
        gst = brokerage * self.GST_PCT      # 6.5% GST on brokerage
        stt = (turnover * self.STT_PCT) if side == "SELL" else 0  # 0.05% STT on sell
        sebi = turnover * self.SEBI_CHARGES  # 0.01% SEBI
        total_charges = brokerage + gst + stt + sebi
        return {
            "brokerage": round(brokerage, 2),
            "stt": round(stt, 2),
            "gst": round(gst, 2),
            "sebi_charges": round(sebi, 2),
            "total_charges": round(total_charges, 2)
        }

    def __init__(self, lot_size: int = 15):
        self.lot_size = lot_size
        self.orders: List[Dict] = []
        self.order_counter = 0
        self.pending_orders: List[Dict] = []

    def place_market_order(self, instrument: str, side: str, quantity: int,
                           current_price: float, option_type: str = "CE",
                           strike: int = 0, tick_timestamp: str = None) -> Dict:
        """Place a market order and simulate fill."""
        self.order_counter += 1
        order_id = f"ORD_{self.order_counter:06d}"

        slippage = current_price * self.SLIPPAGE_PCT
        fill_price = current_price + slippage if side == "BUY" else current_price - slippage

        charges = self.calculate_charges(fill_price, side)

        order = {
            "order_id": order_id,
            "instrument": instrument,
            "side": side,
            "type": OrderType.MARKET.value,
            "quantity": quantity,
            "option_type": option_type,
            "strike": strike,
            "limit_price": None,
            "entry_price": round(fill_price, 2),
            "fill_price": round(fill_price, 2),
            "charges": charges,
            "status": OrderStatus.FILLED.value,
            "timestamp": tick_timestamp or datetime.now().isoformat(),
            "filled_quantity": quantity
        }
        self.orders.append(order)
        logger.info(f"Order {order_id} FILLED: {side} {quantity} {instrument} @ {fill_price}")
        return order

    def place_limit_order(self, instrument: str, side: str, quantity: int,
                          limit_price: float, option_type: str = "CE") -> Dict:
        """Place a limit order (will be filled if price reaches limit)."""
        self.order_counter += 1
        order_id = f"ORD_{self.order_counter:06d}"

        order = {
            "order_id": order_id,
            "instrument": instrument,
            "side": side,
            "type": OrderType.LIMIT.value,
            "quantity": quantity,
            "option_type": option_type,
            "limit_price": limit_price,
            "fill_price": None,
            "charges": {},
            "status": OrderStatus.PENDING.value,
            "timestamp": datetime.now().isoformat(),
            "filled_quantity": 0
        }
        self.pending_orders.append(order)
        self.orders.append(order)
        logger.info(f"Order {order_id} PENDING: {side} {quantity} {instrument} @ limit {limit_price}")
        return order

    def check_limit_orders(self, current_price: float):
        """Check and fill pending limit orders if price conditions met."""
        filled = []
        for order in self.pending_orders:
            limit_price = order["limit_price"]
            if order["side"] == "BUY" and current_price >= limit_price:
                slippage = limit_price * self.SLIPPAGE_PCT
                fill_price = limit_price + slippage
                order["fill_price"] = round(fill_price, 2)
                order["charges"] = self.calculate_charges(fill_price, "BUY")
                order["status"] = OrderStatus.FILLED.value
                order["filled_quantity"] = order["quantity"]
                filled.append(order["order_id"])
            elif order["side"] == "SELL" and current_price <= limit_price:
                slippage = limit_price * self.SLIPPAGE_PCT
                fill_price = limit_price - slippage
                order["fill_price"] = round(fill_price, 2)
                order["charges"] = self.calculate_charges(fill_price, "SELL")
                order["status"] = OrderStatus.FILLED.value
                order["filled_quantity"] = order["quantity"]
                filled.append(order["order_id"])

        self.pending_orders = [o for o in self.pending_orders if o["order_id"] not in filled]
        return filled

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        for order in self.pending_orders:
            if order["order_id"] == order_id:
                order["status"] = OrderStatus.CANCELLED.value
                self.pending_orders.remove(order)
                logger.info(f"Order {order_id} CANCELLED")
                return True
        return False

    def get_margin_required(self, price: float, quantity: int, side: str = "BUY") -> float:
        """Calculate margin required for a position."""
        if side == "BUY":
            return price * quantity * self.lot_size * 0.2  # 20% margin for buy
        else:
            return price * quantity * self.lot_size * 0.15  # 15% for sell

    def get_order_history(self) -> List[Dict]:
        return self.orders

    def get_filled_orders(self) -> List[Dict]:
        return [o for o in self.orders if o["status"] == OrderStatus.FILLED.value]

    def reset(self):
        self.orders = []
        self.pending_orders = []
        self.order_counter = 0


if __name__ == "__main__":
    sim = OrderSimulator()
    order = sim.place_market_order("BANKNIFTY", "BUY", 1, 350, "CE")
    print(f"Order placed: {order['order_id']}, charges: {order['charges']}")