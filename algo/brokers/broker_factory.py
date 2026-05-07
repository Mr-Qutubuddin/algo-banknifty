"""
BrokerFactory — Dynamically instantiates brokers based on config.
All broker selection flows through here — no hardcoded broker references.

Usage:
    from algo.brokers.broker_factory import get_broker

    # Load from config automatically
    broker = get_broker()

    # Or specify explicitly
    broker = get_broker("zerodha")
    broker = get_broker("mstock")
    broker = get_broker("simulation", data_feeder=feeder)
"""
import logging
from pathlib import Path
from typing import Dict, Optional

import yaml

BASE_DIR = Path(__file__).parent.parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"

logger = logging.getLogger(__name__)


class BrokerFactory:
    """Factory for creating broker instances from configuration."""

    _instances: Dict[str, object] = {}

    @classmethod
    def get_broker(cls, provider: str = None, data_feeder=None) -> object:
        """Get broker instance by name, loaded from config.

        Args:
            provider: Broker name ("zerodha" | "mstock" | "simulation" | "paper_trading")
                     If None, reads from broker_config.yaml
            data_feeder: DataFeeder instance for simulation broker (replay mode)

        Returns:
            Broker instance implementing BaseBroker interface
        """
        config = cls._load_broker_config()
        provider = provider or config.get("broker", {}).get("provider", "paper_trading")

        logger.info(f"Initializing broker: {provider}")

        if provider == "zerodha":
            return cls._get_zerodha_broker(config)
        elif provider == "mstock":
            return cls._get_mstock_broker(config)
        elif provider in ("simulation", "paper_trading"):
            return cls._get_simulation_broker(config, data_feeder)
        else:
            logger.warning(f"Unknown broker '{provider}' — defaulting to simulation")
            return cls._get_simulation_broker(config, data_feeder)

    @classmethod
    def _load_broker_config(cls) -> Dict:
        """Load broker configuration from YAML."""
        config_path = CONFIG_DIR / "broker_config.yaml"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        return {}

    @classmethod
    def _get_zerodha_broker(cls, config: Dict) -> object:
        """Instantiate Zerodha broker."""
        from algo.brokers.zerodha import ZerodhaBroker

        zerodha_config = config.get("zerodha", {})
        # Pass full broker config section (includes trading hours, lot size etc)
        full_config = {
            "api_key": zerodha_config.get("api_key", ""),
            "api_secret": zerodha_config.get("api_secret", ""),
            "access_token": zerodha_config.get("access_token", ""),
            "instrument_tokens": zerodha_config.get("instrument_tokens", {}),
            "product": config.get("broker", {}).get("default_product", "MIS"),
            "exchange": config.get("broker", {}).get("default_exchange", "NFO"),
            "auto_squareoff_time": config.get("broker", {}).get("auto_squareoff_time", "15:20"),
        }

        broker = ZerodhaBroker(full_config)
        logger.info("Zerodha broker instance created", extra={
            "broker": "zerodha",
            "has_credentials": bool(full_config.get("api_key")),
            "connected": broker.is_connected
        })
        return broker

    @classmethod
    def _get_mstock_broker(cls, config: Dict) -> object:
        """Instantiate mStock broker."""
        from algo.brokers.mstock import MStockBroker

        mstock_config = config.get("mstock", {})
        full_config = {
            "api_key": mstock_config.get("api_key", ""),
            "api_secret": mstock_config.get("api_secret", ""),
            "client_id": mstock_config.get("client_id", ""),
            "consumer_key": mstock_config.get("consumer_key", ""),
            "product_type": mstock_config.get("product_types", {}).get("intraday", "MIS"),
            "instrument_tokens": mstock_config.get("instrument_tokens", {}),
        }

        broker = MStockBroker(full_config)
        logger.info("mStock broker instance created", extra={
            "broker": "mstock",
            "has_credentials": bool(full_config.get("api_key")),
            "connected": broker.is_connected
        })
        return broker

    @classmethod
    def _get_simulation_broker(cls, config: Dict, data_feeder=None) -> object:
        """Instantiate Simulation broker with real tick feed."""
        from algo.brokers.simulation_broker import SimulationBroker

        sim_config = config.get("simulation", config.get("paper_trading", {}))

        # Brokerage from config
        brokerage = sim_config.get("brokerage", {})
        initial_capital = sim_config.get("initial_capital", 100000)

        broker = SimulationBroker(
            config={
                "initial_capital": initial_capital,
            },
            data_feeder=data_feeder
        )

        # Also configure broker params from config
        broker.LOT_SIZE = config.get("broker", {}).get("default_lot_size", 15)
        broker.BROKERAGE_FLAT = brokerage.get("flat_per_side", 5.0)
        broker.GST_PCT = brokerage.get("gst_pct", 6.5) / 100
        broker.STT_PCT = brokerage.get("stt_pct", 0.05) / 100
        broker.SEBI_PCT = brokerage.get("sebi_pct", 0.01) / 100
        broker.SLIPPAGE = sim_config.get("slippage_pct", 0.05)

        logger.info("Simulation broker instance created", extra={
            "broker": "simulation",
            "capital": initial_capital,
            "brokerage_per_side": broker.BROKERAGE_FLAT,
            "slippage": broker.SLIPPAGE,
            "has_feeder": data_feeder is not None
        })

        return broker

    @classmethod
    def get_all_available_broker_names(cls) -> list:
        """Return list of all configured and available brokers."""
        config = cls._load_broker_config()
        available = []

        if config.get("zerodha", {}).get("enabled", False):
            available.append("zerodha")
        if config.get("mstock", {}).get("enabled", False):
            available.append("mstock")
        if config.get("simulation", {}).get("enabled", True):
            available.append("simulation")
        if config.get("paper_trading", {}).get("enabled", True):
            available.append("paper_trading")

        return available

    @classmethod
    def reload_config(cls):
        """Clear cached instances to force reload from disk."""
        cls._instances.clear()
        logger.info("BrokerFactory config cache cleared")


# ── Convenience function ─────────────────────────────────────────────────────

_broker_instance = None


def get_broker(provider: str = None, data_feeder=None) -> object:
    """Module-level convenience function for getting a broker instance."""
    return BrokerFactory.get_broker(provider, data_feeder)


# Alias
get_default_broker = get_broker