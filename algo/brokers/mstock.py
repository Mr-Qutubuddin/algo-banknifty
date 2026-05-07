"""
mStock Broker Integration.
Implements BaseBroker interface for Motilal Oswal mStock API.

Requires: pip install requests websocket-client

Note: This implementation uses the standard mStock REST/WebSocket API structure.
Update the API endpoints and authentication method based on your mStock API documentation.
"""
import os
import json
import logging
import time
import threading
import hashlib
import hmac
import base64
from datetime import datetime, time as dt_time
from typing import Dict, List, Optional
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).parent.parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"

logger = logging.getLogger(__name__)


class MStockBroker:
    """Motilal Oswal mStock broker implementation."""

    LOT_SIZE = 15

    # mStock API endpoints (update these with actual mStock endpoints)
    BASE_URL = "https://api.mstock.com"
    WS_URL = "wss://ws.mstock.com"
    LOGIN_URL = f"{BASE_URL}/oauth/token"
    QUOTE_URL = f"{BASE_URL}/market/quote"
    ORDER_URL = f"{BASE_URL}/orders"

    def __init__(self, config: Dict = None):
        self.config = config or self._load_config()
        self.is_connected = False

        # API credentials from config
        self.api_key = self.config.get("api_key", "")
        self.api_secret = self.config.get("api_secret", "")
        self.client_id = self.config.get("client_id", "")
        self.consumer_key = self.config.get("consumer_key", "")

        # Auth tokens
        self.access_token = None
        self.feed_token = None

        # Connection state
        self._ws = None
        self._ws_thread = None
        self._ws_callback = None
        self._instrument_tokens = []

        # Price cache
        self.current_prices: Dict[str, float] = {}

        # Auto-detect config
        self._detect_connection_mode()

    def _load_config(self) -> Dict:
        """Load broker configuration from config/broker_config.yaml."""
        broker_config_path = CONFIG_DIR / "broker_config.yaml"
        if broker_config_path.exists():
            with open(broker_config_path) as f:
                full_config = yaml.safe_load(f) or {}
                return full_config.get("mstock", {})
        return {}

    def _detect_connection_mode(self):
        """Detect if real credentials are provided."""
        if self.api_key and self.client_id:
            logger.info(f"mStock broker configured with API key: {self.api_key[:8]}...")
        else:
            logger.warning("mStock API credentials not configured. Use config/broker_config.yaml")

    def login(self) -> bool:
        """Authenticate with mStock API using OAuth or API key."""
        if not self.api_key or not self.client_id:
            logger.warning("mStock: No credentials — running in disconnected mode")
            return False

        try:
            import requests

            # Method 1: API Key + Secret authentication
            # Update this based on actual mStock auth mechanism
            auth_payload = {
                "client_id": self.client_id,
                "api_key": self.api_key,
                "api_secret": self.api_secret,
                "grant_type": "client_credentials"
            }

            response = requests.post(
                self.LOGIN_URL,
                json=auth_payload,
                timeout=10
            )

            if response.status_code == 200:
                auth_data = response.json()
                self.access_token = auth_data.get("access_token")
                self.feed_token = auth_data.get("feed_token", "")
                self.is_connected = True
                logger.info("mStock broker connected successfully")
                return True
            else:
                logger.error(f"mStock auth failed: {response.status_code} - {response.text}")
                return False

        except ImportError:
            logger.error("requests library not installed. Run: pip install requests")
            return False
        except Exception as e:
            logger.error(f"mStock login error: {e}")
            return False

    # ── Market Data ─────────────────────────────────────────────────────────

    def get_instruments(self) -> List[Dict]:
        """Get instrument list from mStock."""
        if not self.is_connected:
            return []

        try:
            import requests
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(
                f"{self.BASE_URL}/instruments",
                headers=headers,
                params={"exchange": "NFO"},
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch instruments: {e}")
        return []

    def get_quote(self, instrument_token: int) -> Dict:
        """Get quote for an instrument."""
        if not self.is_connected:
            return {}

        try:
            import requests
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(
                f"{self.QUOTE_URL}/{instrument_token}",
                headers=headers,
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                symbol = str(instrument_token)
                self.current_prices[symbol] = data.get("last_price", 0)
                return data
        except Exception as e:
            logger.error(f"Quote error: {e}")
        return {}

    def update_price(self, instrument: str, price: float):
        """Update cached price (called from WebSocket tick handler)."""
        self.current_prices[instrument] = price

    def get_live_price(self, instrument: str) -> Optional[float]:
        """Get current cached price for an instrument."""
        return self.current_prices.get(instrument)

    # ── Order Placement ─────────────────────────────────────────────────────

    def place_market_order(self, instrument: str, side: str, quantity: int,
                           option_type: str = "CE") -> Dict:
        """Place a market order."""
        if not self.is_connected:
            logger.warning("mStock not connected — order not placed")
            return {"status": "REJECTED", "reason": "Not connected"}

        try:
            import requests

            # Build order payload
            # mStock format: tradingsymbol like "BANKNIFTY26MAY45000CE"
            tradingsymbol = instrument.upper()

            order_payload = {
                "exchange": "NFO",
                "tradingsymbol": tradingsymbol,
                "transaction_type": "BUY" if side == "BUY" else "SELL",
                "quantity": quantity * self.LOT_SIZE,  # quantity in lots × lot size
                "order_type": "MARKET",
                "product": self.config.get("product_type", "MIS"),
                "validity": "DAY"
            }

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            response = requests.post(
                f"{self.ORDER_URL}/place",
                json=order_payload,
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                order_data = response.json()
                order_id = order_data.get("order_id", f"MST_{int(time.time())}")
                logger.info(f"mStock order placed: {order_id}")
                return {
                    "status": "FILLED",  # Assume filled for market order
                    "order_id": order_id,
                    "fill_price": order_data.get("average_price", 0),
                    "instrument": tradingsymbol
                }
            else:
                logger.error(f"mStock order failed: {response.status_code} - {response.text}")
                return {"status": "REJECTED", "reason": response.text}

        except Exception as e:
            logger.error(f"Market order failed: {e}")
            return {"status": "REJECTED", "reason": str(e)}

    def place_limit_order(self, instrument: str, side: str, quantity: int,
                          price: float, option_type: str = "CE") -> Dict:
        """Place a limit order."""
        if not self.is_connected:
            return {"status": "REJECTED", "reason": "Not connected"}

        try:
            import requests

            tradingsymbol = instrument.upper()
            order_payload = {
                "exchange": "NFO",
                "tradingsymbol": tradingsymbol,
                "transaction_type": "BUY" if side == "BUY" else "SELL",
                "quantity": quantity * self.LOT_SIZE,
                "order_type": "LIMIT",
                "price": price,
                "product": self.config.get("product_type", "MIS"),
                "validity": "DAY"
            }

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            response = requests.post(
                f"{self.ORDER_URL}/place",
                json=order_payload,
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                order_data = response.json()
                return {
                    "status": "OPEN",
                    "order_id": order_data.get("order_id", f"MST_{int(time.time())}"),
                    "limit_price": price,
                    "instrument": tradingsymbol
                }
            else:
                return {"status": "REJECTED", "reason": response.text}

        except Exception as e:
            logger.error(f"Limit order failed: {e}")
            return {"status": "REJECTED", "reason": str(e)}

    def place_sl_order(self, instrument: str, side: str, quantity: int,
                       trigger_price: float, option_type: str = "CE") -> Dict:
        """Place a stop-loss order."""
        if not self.is_connected:
            return {"status": "REJECTED", "reason": "Not connected"}

        try:
            import requests

            tradingsymbol = instrument.upper()
            order_payload = {
                "exchange": "NFO",
                "tradingsymbol": tradingsymbol,
                "transaction_type": "BUY" if side == "BUY" else "SELL",
                "quantity": quantity * self.LOT_SIZE,
                "order_type": "SL",
                "price": trigger_price,
                "trigger_price": trigger_price,
                "product": self.config.get("product_type", "MIS"),
                "validity": "DAY"
            }

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            response = requests.post(
                f"{self.ORDER_URL}/place",
                json=order_payload,
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                order_data = response.json()
                return {
                    "status": "OPEN",
                    "order_id": order_data.get("order_id", f"MST_{int(time.time())}")
                }
            else:
                return {"status": "REJECTED", "reason": response.text}

        except Exception as e:
            logger.error(f"SL order failed: {e}")
            return {"status": "REJECTED", "reason": str(e)}

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        if not self.is_connected:
            return False

        try:
            import requests
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.delete(
                f"{self.ORDER_URL}/cancel/{order_id}",
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                logger.info(f"mStock order {order_id} cancelled")
                return True
        except Exception as e:
            logger.error(f"Cancel failed for {order_id}: {e}")
        return False

    def get_order_status(self, order_id: str) -> str:
        """Get order status from broker."""
        if not self.is_connected:
            return "UNKNOWN"

        try:
            import requests
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(
                f"{self.ORDER_URL}/status/{order_id}",
                headers=headers,
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("status", "UNKNOWN")
        except Exception as e:
            logger.error(f"Status check failed: {e}")
        return "ERROR"

    def get_positions(self) -> List[Dict]:
        """Get open positions."""
        if not self.is_connected:
            return []

        try:
            import requests
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(
                f"{self.ORDER_URL}/positions",
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                return response.json().get("positions", [])
        except Exception as e:
            logger.error(f"Positions error: {e}")
        return []

    def get_balance(self) -> Dict:
        """Get account balance and margin."""
        if not self.is_connected:
            return {}

        try:
            import requests
            headers = {"Authorization": f"Bearer {self.access_token}"}
            response = requests.get(
                f"{self.BASE_URL}/user/balance",
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    "cash": data.get("cash", 0),
                    "available_margin": data.get("available_margin", 0),
                    "used_margin": data.get("used_margin", 0)
                }
        except Exception as e:
            logger.error(f"Balance error: {e}")
        return {}

    # ── WebSocket (Real-Time Data) ─────────────────────────────────────────

    def connect_websocket(self, callback, instrument_tokens: List[int]):
        """Connect to mStock WebSocket for real-time data.

        Args:
            callback: Function to call with each tick
            instrument_tokens: List of instrument tokens to subscribe
        """
        if not self.is_connected:
            logger.warning("mStock not connected — cannot start WebSocket")
            return

        self._ws_callback = callback
        self._instrument_tokens = instrument_tokens

        try:
            import websocket

            def on_message(ws, message):
                try:
                    tick = json.loads(message)
                    # Normalize tick format
                    normalized = {
                        "instrument_token": tick.get("instrument_token", tick.get("token")),
                        "ltp": tick.get("last_price", tick.get("ltp", 0)),
                        "open": tick.get("open", tick.get("ltp", 0)),
                        "high": tick.get("high", tick.get("ltp", 0)),
                        "low": tick.get("low", tick.get("ltp", 0)),
                        "close": tick.get("close", tick.get("ltp", 0)),
                        "volume": tick.get("volume", 0),
                        "timestamp": tick.get("timestamp", datetime.now().isoformat())
                    }
                    # Update price cache
                    symbol = str(normalized["instrument_token"])
                    self.current_prices["BANKNIFTY"] = normalized["ltp"]
                    callback(normalized)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid tick JSON: {message}")

            def on_error(ws, error):
                logger.error(f"mStock WebSocket error: {error}")

            def on_close(ws, close_code, close_msg):
                logger.warning(f"mStock WebSocket closed: {close_code} - {close_msg}")
                # Attempt reconnect
                self._attempt_ws_reconnect(callback, instrument_tokens)

            def on_open(ws):
                logger.info(f"mStock WebSocket connected for tokens: {instrument_tokens}")
                # Subscribe to instruments
                for token in instrument_tokens:
                    ws.send(json.dumps({
                        "type": "subscribe",
                        "instrument_tokens": [str(token)]
                    }))

            # Build WebSocket URL with auth
            ws_url = f"{self.WS_URL}?token={self.access_token}"
            ws = websocket.WebSocketApp(
                ws_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )

            self._ws = ws
            self._ws_thread = threading.Thread(target=ws.run_forever, daemon=True)
            self._ws_thread.start()

        except ImportError:
            logger.error("websocket-client not installed. Run: pip install websocket-client")
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")

    def _attempt_ws_reconnect(self, callback, instrument_tokens: List[int],
                               max_attempts: int = 5, delay: int = 5):
        """Attempt to reconnect WebSocket with backoff."""
        for attempt in range(max_attempts):
            if not self.is_connected:
                break
            logger.info(f"WebSocket reconnect attempt {attempt + 1}/{max_attempts}")
            time.sleep(delay * (attempt + 1))  # Exponential backoff
            try:
                self.connect_websocket(callback, instrument_tokens)
                return
            except Exception as e:
                logger.error(f"Reconnect failed: {e}")
        logger.error("WebSocket reconnection failed after max attempts")

    def disconnect_websocket(self):
        """Gracefully disconnect WebSocket."""
        if self._ws:
            self._ws.close()
            logger.info("mStock WebSocket disconnected")

    # ── Historical Data ─────────────────────────────────────────────────────

    def get_historical_data(self, instrument_token: int, from_date: str,
                            to_date: str, interval: str) -> List[Dict]:
        """Get historical OHLCV data from mStock.

        Args:
            instrument_token: Numeric instrument token
            from_date: "YYYY-MM-DD"
            to_date: "YYYY-MM-DD"
            interval: "5minute" | "hourly" | "day"
        """
        if not self.is_connected:
            return []

        try:
            import requests
            headers = {"Authorization": f"Bearer {self.access_token}"}
            params = {
                "instrument_token": instrument_token,
                "from": from_date,
                "to": to_date,
                "interval": interval
            }
            response = requests.get(
                f"{self.BASE_URL}/market/historical",
                headers=headers,
                params=params,
                timeout=30
            )
            if response.status_code == 200:
                return response.json().get("data", [])
        except Exception as e:
            logger.error(f"Historical data error: {e}")
        return []

    def logout(self):
        """Logout and cleanup."""
        self.disconnect_websocket()
        self.access_token = None
        self.feed_token = None
        self.is_connected = False
        logger.info("mStock broker logged out")


if __name__ == "__main__":
    broker = MStockBroker()
    print(f"mStock broker initialized. Connected: {broker.is_connected}")
    print(f"Config loaded: api_key={'set' if broker.api_key else 'not set'}")