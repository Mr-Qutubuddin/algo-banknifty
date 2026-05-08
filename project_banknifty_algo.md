---
name: project_banknifty_algo
description: BANKNIFTY options algo trading system repo
type: project
originSessionId: fd118ae9-dfbf-42e7-87a2-aeb764227350
---
**Repo**: `D:\Qutub\Workspace\options\algo-banknifty\` (git branch `init`)
**GitHub**: https://github.com/Mr-Qutubuddin/algo-banknifty.git

## Approved Strategies (3 of 21)
- **004/approach_D**: Intraday Momentum Breakout — SMA20+RSI14, BUY CE when price>SMA20 AND RSI>62, BUY PE when price<SMA20 AND RSI<38
- **006/approach_B**: LSTM Momentum — dual RSI+SMAs, BUY CE when RSI(9)>60 AND RSI(14)>55 AND SMA20>SMA50
- **003/approach_C**: BB Squeeze Breakout — BUY ATM straddle when BB_width < 0.03 AND regime != high_vol

## Exit Rules (all strategies)
- 50% profit target
- 30% stop loss
- 60-tick time exit
- Avg hold time: ~25 hours (positional, not intraday)

## Broker Setup
- `config/broker_config.yaml`: single config for all brokers (zerodha, mstock, simulation, paper_trading)
- `algo/brokers/simulation_broker.py`: real tick feed + simulated fills
- `algo/brokers/mstock.py`: Motilal Oswal mStock (needs real credentials)
- `algo/brokers/broker_factory.py`: dynamic broker instantiation from YAML

## Key Files
- `run_paper_trading.py`: paper trading entry point (--mode replay|live, --strategy, --all)
- `generate_reports.py`: approved strategies Excel + Word reports
- `generate_disqualified_reports.py`: disqualified strategies archive reports
- `utils/logging_utils.py`: structured JSON logging
- `data/`: simulation feeds + banknifty.db (excluded from git via .gitignore)

## Reports Generated
- Approved: `BankNifty_Algo_Strategy_Report.docx` + `BankNifty_Algo_Report.xlsx`
- Disqualified: `BankNifty_Algo_Disqualified_Report.docx` + `BankNifty_Algo_Disqualified_Archive.xlsx`

## Current Status (2026-05-08)
- All code committed and pushed to GitHub
- Empty directories cleaned up from banknifty_algo/
- data/ directory excluded from git (large binary files)
- Two empty stubs remain in options root: `banknifty/` and `reports/` (process-locked, harmless)
