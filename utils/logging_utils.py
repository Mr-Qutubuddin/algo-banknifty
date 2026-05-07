"""
Structured Logging Utility — All system logs flow through here.
Configurable log levels, file rotation, contextual fields.

Usage:
    from utils.logging_utils import get_logger, log_trade, log_signal, log_order
    logger = get_logger("algo_agent")
    logger.info("Starting algo", extra={"strategy": "004_D", "mode": "replay"})
"""
import logging
import json
import traceback
import threading
from pathlib import Path
from datetime import datetime, date
from typing import Dict, Any, Optional, List
from logging.handlers import RotatingFileHandler


BASE_DIR = Path(__file__).parent.parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Global log level — set from config
_global_log_level = logging.INFO


class JsonFormatter(logging.Formatter):
    """Format log records as structured JSON for machine-readable logs."""

    def __init__(self, include_extra=True):
        super().__init__()
        self.include_extra = include_extra

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "thread": threading.current_thread().name,
        }

        # Add extra fields from extra={} parameter
        if self.include_extra:
            for key, value in record.__dict__.get("extra", {}).items():
                # Skip if already in log_data to avoid duplicates
                if key not in ("timestamp", "level", "logger", "message"):
                    log_data[key] = self._safe_serialize(value)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info)
            }

        # For trade/order logs, also write to separate trade log file
        if record.name in ("trade_logger", "order_logger", "signal_logger"):
            self._write_trade_log(log_data)

        return json.dumps(log_data)

    def _safe_serialize(self, value: Any) -> Any:
        """Safely serialize values for JSON."""
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, date):
            return value.isoformat()
        elif isinstance(value, dict):
            return {k: self._safe_serialize(v) for k, v in value.items()}
        elif isinstance(value, (list, tuple)):
            return [self._safe_serialize(v) for v in value]
        else:
            return str(value)


class TextFormatter(logging.Formatter):
    """Human-readable format: timestamp [LEVEL] logger: message"""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )


def get_logger(name: str, level: int = None) -> logging.Logger:
    """Get a configured logger instance.

    Args:
        name: Logger name (use dotted notation: "algo.broker", "signal.engine")
        level: Override log level (defaults to global _global_log_level)

    Returns:
        Configured logging.Logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level or _global_log_level)
    logger.propagate = False

    # Only add handlers once per logger
    if not logger.handlers:
        _add_console_handler(logger)
        _add_file_handler(logger, name)

    return logger


def _add_console_handler(logger: logging.Logger):
    """Add console handler with text formatter."""
    console = logging.StreamHandler()
    console.setFormatter(TextFormatter())
    console.setLevel(_global_log_level)
    logger.addHandler(console)


def _add_file_handler(logger: logging.Logger, name: str):
    """Add rotating file handler with JSON formatter for machine-readable logs."""
    # Main log file
    log_file = LOG_DIR / f"{name.replace('.', '_')}.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB per file
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(JsonFormatter())
    file_handler.setLevel(logging.DEBUG)  # File captures everything
    logger.addHandler(file_handler)


def set_log_level(level: str):
    """Set global log level from string (DEBUG, INFO, WARNING, ERROR, CRITICAL)."""
    global _global_log_level
    _global_log_level = getattr(logging, level.upper(), logging.INFO)
    logging.getLogger().setLevel(_global_log_level)


# ── Specialized Log Functions ──────────────────────────────────────────────

def log_trade(action: str, trade_data: Dict, logger_name: str = "trade_logger"):
    """Log a trade event with full context.

    Args:
        action: "OPEN" | "CLOSE" | "MODIFY" | "CANCEL"
        trade_data: dict with instrument, side, quantity, price, pnl, etc.
        logger_name: which logger to use
    """
    logger = get_logger(logger_name)
    logger.info(
        f"Trade {action}: {trade_data.get('instrument', 'UNKNOWN')} "
        f"{trade_data.get('side', '')} {trade_data.get('quantity', 0)} lots @ "
        f"₹{trade_data.get('fill_price', 0)} | P&L: ₹{trade_data.get('pnl', 0)}",
        extra={
            "event": "trade",
            "action": action,
            "instrument": trade_data.get("instrument"),
            "side": trade_data.get("side"),
            "quantity": trade_data.get("quantity"),
            "fill_price": trade_data.get("fill_price"),
            "pnl": trade_data.get("pnl"),
            "order_id": trade_data.get("order_id"),
            "strategy_id": trade_data.get("strategy_id", ""),
            "approach_id": trade_data.get("approach_id", ""),
            "timestamp": datetime.now().isoformat(),
        }
    )


def log_signal(signal_data: Dict, logger_name: str = "signal_logger"):
    """Log a signal generated by strategy.

    Args:
        signal_data: dict with action, strike, option_type, confidence, reason
    """
    logger = get_logger(logger_name)
    logger.info(
        f"Signal: {signal_data.get('action', 'UNKNOWN')} "
        f"{signal_data.get('option_type', '')} "
        f"strike={signal_data.get('strike', 0)} "
        f"conf={signal_data.get('confidence', 0)} | {signal_data.get('reason', '')}",
        extra={
            "event": "signal",
            "action": signal_data.get("action"),
            "option_type": signal_data.get("option_type"),
            "strike": signal_data.get("strike"),
            "confidence": signal_data.get("confidence"),
            "reason": signal_data.get("reason"),
            "lots": signal_data.get("lots", 1),
        }
    )


def log_order(order_data: Dict, logger_name: str = "order_logger"):
    """Log an order placement/modification/cancellation.

    Args:
        order_data: dict with order_id, side, status, fill_price, charges
    """
    logger = get_logger(logger_name)
    order_id = order_data.get("order_id", "UNKNOWN")
    status = order_data.get("status", "UNKNOWN")
    logger.info(
        f"Order {order_id}: {order_data.get('side', '')} "
        f"{order_data.get('instrument', '')} @ ₹{order_data.get('fill_price', order_data.get('limit_price', 'LIMIT'))} "
        f"[{status}]",
        extra={
            "event": "order",
            "order_id": order_id,
            "side": order_data.get("side"),
            "instrument": order_data.get("instrument"),
            "fill_price": order_data.get("fill_price"),
            "limit_price": order_data.get("limit_price"),
            "status": status,
            "charges": order_data.get("charges", {}),
            "option_type": order_data.get("option_type"),
        }
    )


def log_broker_event(event: str, broker_name: str, data: Dict,
                     logger_name: str = "broker_logger"):
    """Log broker-level events (connection, disconnection, errors)."""
    logger = get_logger(logger_name)
    logger.info(
        f"Broker [{broker_name}]: {event}",
        extra={
            "event": "broker",
            "broker": broker_name,
            "detail": event,
            "data": data,
        }
    )


def log_error(error_message: str, context: Dict, logger_name: str = "error_logger"):
    """Log errors with full context for debugging."""
    logger = get_logger(logger_name)
    logger.error(
        error_message,
        extra={
            "event": "error",
            "message": error_message,
            "context": context,
        }
    )


def log_heartbeat(component: str, status: str, data: Dict = None):
    """Log periodic heartbeat for monitoring."""
    logger = get_logger("heartbeat")
    logger.debug(
        f"Heartbeat [{component}]: {status}",
        extra={
            "event": "heartbeat",
            "component": component,
            "status": status,
            "data": data or {},
        }
    )


# ── Log File Readers ─────────────────────────────────────────────────────────

def read_trades_log(date_filter: str = None) -> List[Dict]:
    """Read trade log file, optionally filtered by date.

    Args:
        date_filter: ISO date string like "2026-05-08" to filter logs
    """
    trade_log = LOG_DIR / "trade_logger.log"
    if not trade_log.exists():
        return []

    trades = []
    with open(trade_log, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if date_filter:
                    if entry.get('timestamp', '').startswith(date_filter):
                        trades.append(entry)
                else:
                    trades.append(entry)
            except json.JSONDecodeError:
                continue
    return trades


def get_recent_logs(logger_name: str = None, lines: int = 50) -> List[str]:
    """Get recent log lines for debugging."""
    import tailer  # fallback: manual line reading

    if logger_name:
        log_file = LOG_DIR / f"{logger_name.replace('.', '_')}.log"
    else:
        # Get most recent log file
        files = sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        log_file = files[0] if files else None

    if not log_file or not log_file.exists():
        return []

    with open(log_file, 'r', encoding='utf-8') as f:
        all_lines = f.readlines()
    return all_lines[-lines:]