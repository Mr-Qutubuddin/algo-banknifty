"""
BaseBroker — Abstract broker interface for all broker implementations.
All brokers must implement this interface.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from enum import Enum


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SLM = "SLM"


class BaseBroker(ABC):
    """Abstract base class for broker implementations."""

    @abstractmethod
    def login(self) -> bool:
        """Authenticate with the broker API."""
        pass

    @abstractmethod
    def get_instruments(self) -> List[Dict]:
        """Get available instruments."""
        pass

    @abstractmethod
    def get_quote(self, instrument_token: int) -> Dict:
        """Get quote for an instrument."""
        pass

    @abstractmethod
    def place_market_order(self, instrument: str, side: str, quantity: int,
                           option_type: str = "CE") -> Dict:
        """Place a market order."""
        pass

    @abstractmethod
    def place_limit_order(self, instrument: str, side: str, quantity: int,
                          price: float, option_type: str = "CE") -> Dict:
        """Place a limit order."""
        pass

    @abstractmethod
    def place_sl_order(self, instrument: str, side: str, quantity: int,
                       trigger_price: float, option_type: str = "CE") -> Dict:
        """Place a stop-loss order."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> str:
        """Get order status."""
        pass

    @abstractmethod
    def get_positions(self) -> List[Dict]:
        """Get open positions."""
        pass

    @abstractmethod
    def get_balance(self) -> Dict:
        """Get account balance and margin."""
        pass

    @abstractmethod
    def connect_websocket(self, callback, instrument_tokens: List[int]):
        """Connect to WebSocket for real-time data."""
        pass

    def get_historical_data(self, instrument_token: int, from_date: str,
                            to_date: str, interval: str) -> List[Dict]:
        """Get historical OHLCV data (optional implementation)."""
        raise NotImplementedError("Historical data not supported by this broker")