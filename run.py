"""
Master launcher for BankNifty Options Trading System.
Orchestrates all phases and agents based on configuration.
"""
import os
import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(BASE_DIR / 'logs' / 'run.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def setup_environment():
    """Ensure all directories and baseline files exist."""
    dirs = [
        'logs', 'data/raw/banknifty_ohlcv', 'data/raw/options_chain', 'data/raw/vix',
        'data/processed/features', 'data/processed/signals', 'data/feeds',
        'data/live', 'strategies/research', 'strategies/approved',
        'backtests/simulation_engine', 'backtests/results', 'backtests/comparison',
        'algo/core', 'algo/brokers', 'algo/subscriptions', 'algo/storage',
        'config', 'journal/strategies', 'journal/backtest_results', 'journal/review_reports',
        'dashboard', 'tests'
    ]

    for d in dirs:
        Path(BASE_DIR / d).mkdir(parents=True, exist_ok=True)

    logger.info("Environment setup complete")


def run_phase(phase: int, agents: list):
    """Run a specific phase with specified agents."""
    logger.info(f"=== PHASE {phase} STARTING ===")
    from agents.orchestrator import OrchestratorAgent

    orch = OrchestratorAgent()

    if 2 in phase:
        from agents.data_agent import DataAgent
        logger.info("Starting DataAgent...")
        data_agent = DataAgent(orch)
        data_agent.run()

    if 3 in phase:
        from agents.research_agent import ResearchAgent
        logger.info("Starting ResearchAgent...")
        research_agent = ResearchAgent(orch)
        research_agent.run()

    if 4 in phase:
        from agents.backtest_agent import BacktestAgent
        logger.info("Starting BacktestAgent...")
        backtest_agent = BacktestAgent(orch)
        backtest_agent.run_all_backtests()
        backtest_agent.generate_comparison_report()

    if 5 in phase:
        from agents.review_agent import ReviewAgent
        logger.info("Starting ReviewAgent...")
        review_agent = ReviewAgent(orch)
        review_agent.run()
        logger.info("=== PHASE 5 COMPLETE — Awaiting user approval for Phase 6 ===")

    logger.info(f"=== PHASE {phase} COMPLETE ===")


def main():
    parser = argparse.ArgumentParser(description="BankNifty Options Trading System")
    parser.add_argument("--phase", type=int, default=5,
                        help="Phase to run (2-9). Default: 5 (Review)")
    parser.add_argument("--strategy", type=str, help="Specific strategy to run")
    parser.add_argument("--all", action="store_true", help="Run all phases sequentially")
    parser.add_argument("--quick", action="store_true", help="Run quick demo with synthetic data")
    args = parser.parse_args()

    setup_environment()

    if args.quick:
        logger.info("Running QUICK demo mode...")
        from agents.data_agent import DataAgent
        from agents.research_agent import ResearchAgent
        from agents.backtest_agent import BacktestAgent

        data = DataAgent()
        data.run()

        research = ResearchAgent()
        research.run()

        backtest = BacktestAgent()
        backtest.run_all_backtests()
        backtest.generate_comparison_report()
        logger.info("Quick demo complete!")
        return

    if args.all:
        for phase in range(2, 10):
            run_phase(phase, [])
            if phase == 5:
                logger.info("=== PAUSE: Awaiting user approval ===")
                break
        return

    run_phase(args.phase, [])


if __name__ == "__main__":
    print("BankNifty Options Trading System v1.0")
    print("=" * 50)
    main()