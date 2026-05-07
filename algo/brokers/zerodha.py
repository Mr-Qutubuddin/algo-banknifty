"""
Zerodha/Kite Connect Broker Integration.
Implements BaseBroker interface for Zerodha Kite Connect API.
"""
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).parent.parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.FileHandler(Path(__file__).parent.parent.parent / 'logs' / 'zerodha_broker.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class ZerodhaBroker:
    """Zerodha Kite Connect broker implementation."""

    def __init__(self, config: Dict = None):
        self.config = config or self._load_config()
        self.api_key = self.config.get("api_key", "")
        self.access_token = self.config.get("access_token", "")
        self.kite = None
        self.is_connected = False
        self.instrument_cache: Dict[str, int] = {}
        self._login()

    def _load_config(self) -> Dict:
        broker_config_path = CONFIG_DIR / "broker_config.yaml"
        if broker_config_path.exists():
            with open(broker_config_path) as f:
                config = yaml.safe_load(f) or {}
                return config
        return {}

    def _login(self):
        """Authenticate with Kite Connect."""
        try:
            from kiteconnect import KiteConnect
            self.kite = KiteConnect(api_key=self.api_key)

            if self.access_token:
                self.kite.set_access_token(self.access_token)
                self.is_connected = True
                logger.info("Zerodha broker connected successfully")
            else:
                logger.warning("No access token — running in disconnected mode")
        except ImportError:
            logger.error("kiteconnect not installed. Run: pip install kiteconnect")
        except Exception as e:
            logger.error(f"Zerodha login failed: {e}")

    def login(self) -> bool:
        """Manual login/rlogin."""
        if self.kite and self.config.get("api_secret"):
            try:
                from kiteconnect import KiteConnect
                self.kite = KiteConnect(api_key=self.api_key)
                login_url = self.kite.login_url()
                logger.info(f"Login URL: {login_url}")
                return True
            except Exception as e:
                logger.error(f"Login error: {e}")
        return False

    def get_instruments(self) -> List[Dict]:
        """Get all tradable instruments from NSE."""
        if not self.is_connected:
            return []
        try:
            instruments = self.kite.instruments("NSE")
            self.instrument_cache = {i["tradingsymbol"]: i["instrument_token"]
                                     for i in instruments if i["exchange"] == "NSE"}
            return instruments
        except Exception as e:
            logger.error(f"Failed to fetch instruments: {e}")
            return []

    def get_quote(self, instrument_token: int) -> Dict:
        """Get quote for an instrument."""
        if not self.is_connected:
            return {}
        try:
            return self.kite.quote(instrument_token)
        except Exception as e:
            logger.error(f"Quote error: {e}")
            return {}

    def place_market_order(self, instrument: str, side: str, quantity: int,
                           option_type: str = "CE") -> Dict:
        """Place a market order."""
        if not self.is_connected:
            logger.warning("Broker not connected — order not placed")
            return {"status": "REJECTED", "reason": "Not connected"}

        try:
            tradingsymbol = self._get_tradingsymbol(instrument, option_type)
            order = self.kite.place_order(
                exchange="NFO",
                tradingsymbol=tradingsymbol,
                transaction_type=side.upper(),
                quantity=quantity * 15,  # lot size
                order_type="MARKET",
                product="MIS"
            )
            logger.info(f"Order placed: {order}")
            return {"status": "FILLED", "order_id": order}
        except Exception as e:
            logger.error(f"Market order failed: {e}")
            return {"status": "REJECTED", "reason": str(e)}

    def place_limit_order(self, instrument: str, side: str, quantity: int,
                          price: float, option_type: str = "CE") -> Dict:
        """Place a limit order."""
        if not self.is_connected:
            return {"status": "REJECTED", "reason": "Not connected"}

        try:
            tradingsymbol = self._get_tradingsymbol(instrument, option_type)
            order = self.kite.place_order(
                exchange="NFO",
                tradingsymbol=tradingsymbol,
                transaction_type=side.upper(),
                quantity=quantity * 15,
                order_type="LIMIT",
                price=price,
                product="MIS"
            )
            return {"status": "OPEN", "order_id": order}
        except Exception as e:
            logger.error(f"Limit order failed: {e}")
            return {"status": "REJECTED", "reason": str(e)}

    def place_sl_order(self, instrument: str, side: str, quantity: int,
                       trigger_price: float, option_type: str = "CE") -> Dict:
        """Place a stop-loss order."""
        if not self.is_connected:
            return {"status": "REJECTED", "reason": "Not connected"}

        try:
            tradingsymbol = self._get_tradingsymbol(instrument, option_type)
            order = self.kite.place_order(
                exchange="NFO",
                tradingsymbol=tradingsymbol,
                transaction_type=side.upper(),
                quantity=quantity * 15,
                order_type="SL",
                price=trigger_price,
                trigger_price=trigger_price,
                product="MIS"
            )
            return {"status": "OPEN", "order_id": order}
        except Exception as e:
            logger.error(f"SL order failed: {e}")
            return {"status": "REJECTED", "reason": str(e)}

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        if not self.is_connected:
            return False
        try:
            self.kite.cancel_order(order_id)
            logger.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Cancel failed: {e}")
            return False

    def get_order_status(self, order_id: str) -> str:
        """Get order status from broker."""
        if not self.is_connected:
            return "UNKNOWN"
        try:
            orders = self.kite.orders()
            for order in orders:
                if order.get("order_id") == order_id:
                    return order.get("status", "UNKNOWN")
            return "NOT_FOUND"
        except Exception as e:
            logger.error(f"Status check failed: {e}")
            return "ERROR"

    def get_positions(self) -> List[Dict]:
        """Get open positions."""
        if not self.is_connected:
            return []
        try:
            positions = self.kite.positions()
            return positions.get("net", [])
        except Exception as e:
            logger.error(f"Positions error: {e}")
            return []

    def get_balance(self) -> Dict:
        """Get account balance and margin."""
        if not self.is_connected:
            return {}
        try:
            margin = self.kite.margins()
            return {
                "cash": margin.get("cash", 0),
                "available_margin": margin.get("available", {}).get("cash", 0),
                "used_margin": margin.get("used", {}).get("cash", 0)
            }
        except Exception as e:
            logger.error(f"Balance error: {e}")
            return {}

    def connect_websocket(self, callback, instrument_tokens: List[int]):
        """Connect to Kite WebSocket for real-time data."""
        if not self.is_connected:
            logger.warning("Cannot connect WebSocket — not connected")
            return

        try:
            from kitews import KiteTicker
        except ImportError:
            logger.error("kitews not installed for WebSocket. Run: pip install kitews")
            return

        def on_tick(tick, callback=callback):
            callback(tick)

        ticker = KiteTicker(self.api_key, self.access_token)
        ticker.on_tick = on_tick
        ticker.connect()
        logger.info(f"WebSocket connected for tokens: {instrument_tokens}")

    def _get_tradingsymbol(self, instrument: str, option_type: str) -> str:
        """Convert instrument name to Zerodha tradingsymbol format."""
        return instrument.upper()

    def get_historical_data(self, instrument_token: int, from_date: str,
                            to_date: str, interval: str) -> List[Dict]:
        """Get historical OHLCV data."""
        if not self.is_connected:
            return []
        try:
            data = self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval=interval
            )
            return data
        except Exception as e:
            logger.error(f"Historical data error: {e}")
            return []


if __name__ == "__main__":
    broker = ZerodhaBroker()
    print(f"Zerodha broker initialized. Connected: {broker.is_connected}")