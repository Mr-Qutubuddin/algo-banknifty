"""
Paper Trading Launcher — Real ticks with simulated order execution.
All broker selection flows through BrokerFactory — nothing hardcoded.
All events logged for traceability.

Usage:
    python run_paper_trading.py --strategy 004_D --mode replay
    python run_paper_trading.py --strategy 006_B --mode live
    python run_paper_trading.py --strategy 003_C --mode replay --speed 10
    python run_paper_trading.py --all --mode replay
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

# Setup logging FIRST
from utils.logging_utils import get_logger, log_trade, log_signal, log_order, set_log_level
import yaml

# Load log level from config
config_path = BASE_DIR / "config" / "broker_config.yaml"
if config_path.exists():
    with open(config_path, 'r', encoding='utf-8') as f:
        broker_cfg = yaml.safe_load(f) or {}
    log_level = broker_cfg.get("logging", {}).get("level", "INFO")
else:
    log_level = "INFO"
set_log_level(log_level)

logger = get_logger("run_paper_trading")

# Strategy registry
STRATEGY_MAP = {
    "004_D": {
        "strategy_id": "strategy_004",
        "approach_id": "approach_D",
        "class": "Strategy004ApproachD"
    },
    "006_B": {
        "strategy_id": "strategy_006",
        "approach_id": "approach_B",
        "class": "Strategy006ApproachB"
    },
    "003_C": {
        "strategy_id": "strategy_003",
        "approach_id": "approach_C",
        "class": "Strategy003ApproachC"
    },
}
APPROVED_STRATEGIES = list(STRATEGY_MAP.keys())


def get_strategy_class(strategy_key: str):
    """Import and return the strategy class."""
    if strategy_key == "004_D":
        from algo.core.strategy_004_approach_D import Strategy004ApproachD
        return Strategy004ApproachD
    elif strategy_key == "006_B":
        from algo.core.strategy_006_approach_B import Strategy006ApproachB
        return Strategy006ApproachB
    elif strategy_key == "003_C":
        from algo.core.strategy_003_approach_C import Strategy003ApproachC
        return Strategy003ApproachC
    else:
        raise ValueError(f"Unknown strategy: {strategy_key}")


def get_data_feeder(mode: str, config: dict):
    """Get DataFeeder for replay mode, or None for live."""
    if mode != "replay":
        return None

    from backtests.simulation_engine.data_feeder import DataFeeder

    feeds_cfg = config.get("data_feeds", {})
    primary = feeds_cfg.get("primary", {})

    path_str = primary.get("path", "data/feeds/simulation_feed_hourly.json")
    feed_path = BASE_DIR.parent / path_str
    if not feed_path.exists():
        fallback = primary.get("fallback_path", "data/feeds/simulation_feed.json")
        feed_path = BASE_DIR.parent / fallback

    if not feed_path.exists():
        logger.error(f"No feed file found at {feed_path}")
        return None

    feeder = DataFeeder(feed_path)
    logger.info(f"DataFeeder loaded: {len(feeder.data)} ticks from {feed_path.name}", extra={
        "feed_path": str(feed_path),
        "tick_count": len(feeder.data),
        "mode": mode
    })
    return feeder


def load_master_config() -> dict:
    """Load master config for capital, trading hours, etc."""
    master_path = BASE_DIR / "config" / "master_config.yaml"
    if master_path.exists():
        with open(master_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def run_paper_trading(strategy_key: str, mode: str = "replay",
                      initial_capital: float = 100000, speed: int = 1):
    """Run paper trading with real ticks and simulated fills."""

    # Load configs
    broker_config = _load_broker_config()
    master_config = load_master_config()

    # Get trading hours from config
    trading_hours = master_config.get("trading_hours", {})
    start_time = trading_hours.get("start", "09:15")
    end_time = trading_hours.get("end", "15:30")

    logger.info(f"Starting paper trading | strategy={strategy_key} | mode={mode} | capital=₹{initial_capital:,}", extra={
        "event": "start",
        "strategy": strategy_key,
        "mode": mode,
        "initial_capital": initial_capital,
        "speed": speed,
        "broker": broker_config.get("broker", {}).get("provider", "simulation")
    })

    print(f"\n{'='*60}")
    print(f"  PAPER TRADING — {strategy_key}")
    print(f"  Mode: {'Historical Replay' if mode == 'replay' else 'Live WebSocket'}")
    print(f"  Broker: {broker_config.get('broker', {}).get('provider', 'simulation')}")
    print(f"  Capital: ₹{initial_capital:,.0f}")
    print(f"  Trading hours: {start_time} – {end_time}")
    print(f"{'='*60}\n")

    # Get data feeder
    data_feeder = get_data_feeder(mode, broker_config)

    # Get broker via factory
    from algo.brokers.broker_factory import get_broker
    broker = get_broker(provider=broker_config.get("broker", {}).get("provider", "simulation"),
                        data_feeder=data_feeder)
    broker.login()

    # Initialize strategy
    strategy_class = get_strategy_class(strategy_key)
    strategy_logic = strategy_class()

    algo_config = {
        "initial_capital": initial_capital,
        "max_open_positions": 3,
        "max_daily_loss": 5000,
        "max_per_trade_loss": 3000,
        "instrument_tokens": [260105, 260106, 260107],
        "strategy_id": strategy_class.STRATEGY_ID,
        "approach_id": strategy_class.APPROACH_ID,
        "trading_hours_start": start_time,
        "trading_hours_end": end_time,
    }

    from agents.algo_agent import AlgoAgent
    algo = AlgoAgent(strategy_logic=strategy_logic, broker=broker, config=algo_config)

    logger.info(f"AlgoAgent initialized", extra={
        "strategy_id": strategy_class.STRATEGY_ID,
        "approach_id": strategy_class.APPROACH_ID,
        "confidence_threshold": strategy_logic.confidence_threshold,
        "capital": initial_capital,
        "max_positions": 3
    })

    print(f"AlgoAgent running | {strategy_logic.STRATEGY_ID}/{strategy_logic.APPROACH_ID}")
    print(f"Confidence threshold: {strategy_logic.confidence_threshold}")
    print(f"Broker: {broker_config.get('broker', {}).get('provider', 'simulation').title()}")

    if mode == "replay":
        print(f"Feed: Historical replay ({len(data_feeder.data)} ticks @ {speed}x)")
    else:
        print(f"Feed: Live WebSocket")

    # Start tick feed
    broker.connect_websocket(algo.on_tick, algo_config["instrument_tokens"])
    algo.is_running = True

    # Monitor loop
    try:
        import time
        last_report_time = 0

        while True:
            time.sleep(1)
            positions = algo.position_tracker.get_open_count()
            equity = algo.position_tracker.cash + algo.position_tracker.get_live_pnl()
            realized_pnl = sum(t.get('pnl', 0) for t in algo.position_tracker.closed_trades)

            now = time.time()
            if now - last_report_time >= 5:
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"[{timestamp}] "
                      f"Equity: ₹{equity:,.0f} | "
                      f"Open: {positions} | "
                      f"Closed: {len(algo.position_tracker.closed_trades)} | "
                      f"Realized P&L: ₹{realized_pnl:,.0f}")

                # Log heartbeat
                log_heartbeat("algo_agent", "running", {
                    "equity": round(equity, 2),
                    "open_positions": positions,
                    "closed_trades": len(algo.position_tracker.closed_trades),
                    "realized_pnl": round(realized_pnl, 2),
                    "cash": round(algo.position_tracker.cash, 2)
                })
                last_report_time = now

    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
        print("\n\nStopping paper trading...")
        broker.stop()
        algo.shutdown()

        # Final summary
        realized_pnl = sum(t.get('pnl', 0) for t in algo.position_tracker.closed_trades)
        final_equity = algo.position_tracker.cash + algo.position_tracker.get_live_pnl()

        if algo.position_tracker.closed_trades:
            wins = [t for t in algo.position_tracker.closed_trades if t.get('pnl', 0) > 0]
            losses = [t for t in algo.position_tracker.closed_trades if t.get('pnl', 0) <= 0]
            win_rate = len(wins) / len(algo.position_tracker.closed_trades) * 100
        else:
            wins, losses, win_rate = [], [], 0.0

        print(f"\n{'='*60}")
        print(f"  PAPER TRADING SUMMARY — {strategy_key}")
        print(f"{'='*60}")
        print(f"  Final equity:     ₹{final_equity:,.0f}")
        print(f"  Net P&L:          ₹{final_equity - initial_capital:,.0f}")
        print(f"  Realized P&L:     ₹{realized_pnl:,.0f}")
        print(f"  Closed trades:    {len(algo.position_tracker.closed_trades)}")
        print(f"  Win rate:         {win_rate:.1f}%")
        print(f"  Open positions:   {algo.position_tracker.get_open_count()}")
        print(f"{'='*60}")

        logger.info(f"Shutdown complete", extra={
            "event": "shutdown",
            "final_equity": round(final_equity, 2),
            "net_pnl": round(final_equity - initial_capital, 2),
            "closed_trades": len(algo.position_tracker.closed_trades),
            "win_rate": round(win_rate, 1)
        })


def _load_broker_config() -> dict:
    """Load broker configuration YAML."""
    config_path = BASE_DIR / "config" / "broker_config.yaml"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def run_all_strategies(mode: str = "replay", initial_capital: float = 100000, speed: int = 1):
    """Run all approved strategies."""
    for key in APPROVED_STRATEGIES:
        try:
            run_paper_trading(key, mode, initial_capital, speed)
        except Exception as e:
            logger.error(f"Failed to run {key}", extra={"error": str(e), "strategy": key})
            print(f"ERROR in {key}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Paper Trading — Real ticks, simulated fills")
    parser.add_argument("--strategy", type=str, help=f"Strategy: {APPROVED_STRATEGIES}")
    parser.add_argument("--all", action="store_true", help="Run all approved strategies")
    parser.add_argument("--mode", type=str, default="replay", choices=["replay", "live"],
                        help="replay=historical ticks, live=Zerodha WebSocket")
    parser.add_argument("--capital", type=float, default=100000)
    parser.add_argument("--speed", type=int, default=1, help="Replay speed multiplier")
    args = parser.parse_args()

    if args.all:
        run_all_strategies(args.mode, args.capital, args.speed)
    elif args.strategy:
        if args.strategy not in STRATEGY_MAP:
            print(f"Unknown: {args.strategy} | Available: {APPROVED_STRATEGIES}")
            sys.exit(1)
        run_paper_trading(args.strategy, args.mode, args.capital, args.speed)
    else:
        parser.print_help()
        print(f"\nApproved: {APPROVED_STRATEGIES}")
        print(f"Examples:")
        print(f"  python run_paper_trading.py --strategy 004_D --mode replay --speed 10")
        print(f"  python run_paper_trading.py --strategy 006_B --mode live")
        print(f"  python run_paper_trading.py --all --mode replay")


if __name__ == "__main__":
    main()