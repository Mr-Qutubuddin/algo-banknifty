# BankNifty Options Trading — Autonomous Agentic Research & Algo System

## Overview

A multi-agent autonomous system for researching, backtesting, and executing BankNifty options trading strategies. The system uses specialized agents for data collection, strategy research, backtesting, review, and live trading.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR AGENT                         │
│               (Coordinates all sub-agents)                      │
└─────────────────────────────────────────────────────────────────┘
         │    │    │    │    │    │    │    │
    ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐
    │Data│ │Res.│ │Back│ │Rev.│ │Jrnl│ │Algo│ │Conf│ │Mon.│
    │Agent│ │Age.│ │test│ │iew │ │Age.│ │Age.│ │Age.│ │Age.│
    └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘
```

## Folder Structure

```
banknifty_algo/
├── agents/          # All agent implementations
├── algo/            # Live trading system
│   ├── core/        # Data collection, signal engine, order management
│   ├── brokers/     # Broker integrations (Zerodha, PaperTrading)
│   └── storage/     # Database, trade logging, export
├── backtests/       # Simulation engine and results
├── config/          # All YAML configuration files
├── data/            # Raw, processed, feeds
├── dashboard/       # HTML monitoring dashboards
├── journal/         # Research journals and reports
├── strategies/      # Strategy research and approved strategies
└── tests/           # Unit tests
```

## Installation

```bash
cd banknifty_algo
pip install -r requirements.txt
```

## Running the System

### Start the full system:
```bash
python run.py
```

### Run individual agents:
```bash
python agents/data_agent.py
python agents/research_agent.py
python agents/backtest_agent.py
```

### Update configuration:
```bash
python agents/config_agent.py --config strategy_config --param stop_loss --value 50 --reason "Increased due to volatility"
```

## Phases

1. **Phase 1**: Project scaffolding (DONE)
2. **Phase 2**: Data collection — DataAgent (DONE)
3. **Phase 3**: Strategy research — ResearchAgent (DONE)
4. **Phase 4**: Backtesting — BacktestAgent (DONE)
5. **Phase 5**: Review & ranking — ReviewAgent (DONE) ⏸️ **PAUSE for user approval**
6. **Phase 6**: Algo system build (pending)
7. **Phase 7**: Config-driven updates (pending)
8. **Phase 8**: Live simulation (pending)
9. **Phase 9**: Dashboard (pending)

## Strategies Implemented

- **Strategy 001**: Iron Condor / Iron Fly Variants (3 approaches)
- **Strategy 002**: Momentum-Based Directional Options (3 approaches)
- **Strategy 003**: Mean Reversion Strategies (3 approaches)
- **Strategy 004**: Event-Based Strategies (3 approaches)
- **Strategy 005**: Greeks-Based Strategies (3 approaches)
- **Strategy 006**: Machine Learning Assisted (3 approaches)

Total: 6 strategies × 3 approaches = 18 strategy variations

## Configuration

All configuration is managed through YAML files in `config/`:
- `master_config.yaml` — System-wide settings
- `strategy_config.yaml` — Active strategy parameters
- `broker_config.yaml` — Broker API credentials
- `risk_config.yaml` — Risk management parameters
- `data_sources.yaml` — Data source endpoints

## Trading Hours

- **IST**: 9:15 AM to 3:30 PM (Monday-Friday)
- Auto square-off at 3:20 PM IST

## Broker Support

- **Zerodha Kite Connect** — Live trading
- **Paper Trading** — Simulation mode (default)

## Disclaimer

This system is for research and simulation purposes. Options trading involves substantial risk of loss. Always use paper trading mode for testing before any live deployment.