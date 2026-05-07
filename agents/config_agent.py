"""
ConfigAgent — Manages configuration files and dynamic parameter updates.
Handles strategy config, broker config, risk config with live reload capability.
"""
import os
import json
import logging
import yaml
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

BASE_DIR = Path(__file__).parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
JOURNAL_CONFIG_LOG = BASE_DIR / "journal" / "config_change_log.md"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.FileHandler(Path(__file__).parent.parent / 'logs' / 'config_agent.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class ConfigAgent:
    """Manages all configuration files with live reload support."""

    def __init__(self):
        self.configs: Dict[str, dict] = {}
        self._load_all_configs()
        logger.info("ConfigAgent initialized")

    def _load_all_configs(self):
        """Load all YAML configuration files."""
        config_files = [
            "master_config.yaml",
            "strategy_config.yaml",
            "broker_config.yaml",
            "risk_config.yaml",
            "data_sources.yaml"
        ]

        for cf in config_files:
            path = CONFIG_DIR / cf
            if path.exists():
                with open(path, 'r') as f:
                    config_name = cf.replace(".yaml", "")
                    self.configs[config_name] = yaml.safe_load(f) or {}
                    logger.info(f"Loaded {cf}")
            else:
                self.configs[cf.replace(".yaml", "")] = {}
                logger.warning(f"Config file not found: {cf} — using defaults")

    def get(self, config_name: str, key: str = None, default: Any = None) -> Any:
        """Get config value by name and optional key."""
        config = self.configs.get(config_name, {})
        if key is None:
            return config
        keys = key.split(".")
        value = config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def set(self, config_name: str, key: str, value: Any, reason: str = "") -> bool:
        """Set a config value with change logging."""
        old_value = self.get(config_name, key)

        if config_name not in self.configs:
            self.configs[config_name] = {}

        keys = key.split(".")
        config = self.configs[config_name]
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

        self._save_config(config_name)
        self._log_change(config_name, key, old_value, value, reason)

        logger.info(f"Config updated: {config_name}.{key} = {value} (was {old_value})")
        return True

    def _save_config(self, config_name: str):
        """Save config back to YAML file."""
        path = CONFIG_DIR / f"{config_name}.yaml"
        with open(path, 'w') as f:
            yaml.dump(self.configs[config_name], f, default_flow_style=False)

    def _log_change(self, config_name: str, key: str, old_value: Any, new_value: Any, reason: str):
        """Log configuration change to journal."""
        if not JOURNAL_CONFIG_LOG.exists():
            JOURNAL_CONFIG_LOG.parent.mkdir(parents=True, exist_ok=True)
            JOURNAL_CONFIG_LOG.write_text("# Configuration Change Log\n\n"
                                          "| Timestamp | Config | Parameter | Old Value | New Value | Reason |\n"
                                          "|------------|--------|-----------|-----------|-----------|--------|\n")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(JOURNAL_CONFIG_LOG, 'a') as f:
            f.write(f"| {timestamp} | {config_name} | {key} | {old_value} | {new_value} | {reason} |\n")

    def reload(self, config_name: str = None):
        """Reload configuration from disk."""
        if config_name:
            path = CONFIG_DIR / f"{config_name}.yaml"
            if path.exists():
                with open(path, 'r') as f:
                    self.configs[config_name] = yaml.safe_load(f) or {}
                logger.info(f"Reloaded {config_name}")
        else:
            self._load_all_configs()
            logger.info("All configs reloaded")

    def export_to_json(self, config_name: str, output_path: Path = None) -> str:
        """Export config to JSON format."""
        config = self.configs.get(config_name, {})
        output = output_path or (CONFIG_DIR / f"{config_name}.json")
        with open(output, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info(f"Config exported to {output}")
        return str(output)

    def get_strategy_config(self) -> Dict:
        """Get the active strategy configuration."""
        return self.configs.get("strategy_config", {})

    def get_broker_config(self) -> Dict:
        """Get broker configuration."""
        return self.configs.get("broker_config", {})

    def get_risk_config(self) -> Dict:
        """Get risk management configuration."""
        return self.configs.get("risk_config", {})


class ConfigUpdaterCLI:
    """CLI tool for updating config parameters in real-time."""

    def __init__(self):
        self.agent = ConfigAgent()

    def update_param(self, config: str, param: str, value: Any, reason: str = ""):
        """Update a single parameter."""
        self.agent.set(config, param, value, reason)
        print(f"Updated {config}.{param} = {value}")

    def batch_update(self, updates: list):
        """Apply multiple updates at once."""
        for update in updates:
            config = update.get("config")
            param = update.get("param")
            value = update.get("value")
            reason = update.get("reason", "")
            self.agent.set(config, param, value, reason)

    def validate_config(self, config_name: str) -> bool:
        """Validate configuration structure."""
        config = self.agent.configs.get(config_name, {})
        required_fields = {
            "strategy_config": ["strategy_id", "approach_id", "stop_loss"],
            "broker_config": ["api_key", "trading_mode"],
            "risk_config": ["max_daily_loss", "max_open_positions"]
        }

        if config_name in required_fields:
            for field in required_fields[config_name]:
                if field not in config:
                    logger.error(f"Missing required field: {config_name}.{field}")
                    return False
        return True


def main():
    parser = argparse.ArgumentParser(description="ConfigAgent CLI — Update parameters in real-time")
    parser.add_argument("--config", type=str, help="Config name (e.g., strategy_config)")
    parser.add_argument("--param", type=str, help="Parameter key (supports dot notation: stop_loss, risk.max_loss)")
    parser.add_argument("--value", type=str, help="New value")
    parser.add_argument("--reason", type=str, default="", help="Reason for change")
    parser.add_argument("--list", action="store_true", help="List all current configs")
    parser.add_argument("--reload", type=str, help="Reload config from disk")

    args = parser.parse_args()
    cli = ConfigUpdaterCLI()

    if args.list:
        for name, config in cli.agent.configs.items():
            print(f"\n=== {name} ===")
            print(yaml.dump(config, default_flow_style=False))
        return

    if args.reload:
        cli.agent.reload(args.reload)
        print(f"Reloaded {args.reload}")
        return

    if args.config and args.param and args.value is not None:
        value = args.value
        if value.lower() in ["true", "false"]:
            value = value.lower() == "true"
        elif value.isdigit():
            value = int(value)
        elif "." in value and value.replace(".", "").isdigit():
            value = float(value)

        cli.update_param(args.config, args.param, value, args.reason)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()