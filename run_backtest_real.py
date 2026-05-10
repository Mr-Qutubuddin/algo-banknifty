import sys, json
sys.path.insert(0, '.')

from backtests.scalping_backtest import ScalpingBacktest
from algo.core.strategy_n50_scalping import Nifty50ScalpingStrategy
from load_nifty50_data import load_nifty50_from_csv

print('Loading real Nifty 50 1-minute data...', flush=True)
bars = load_nifty50_from_csv()
print(f'Data: {len(bars):,} bars', flush=True)

print('Backtest starting...', flush=True)
bt = ScalpingBacktest(initial_capital=100000.0, lot_size=75, iv=22.0)
bt.add_strategy(Nifty50ScalpingStrategy, name='nifty50')
results = bt.run(bars, '1m', 0.5, False)

with open('backtest_output.json', 'w') as f:
    json.dump(results, f, indent=2, default=str)

s = results['nifty50']['stats']
print(f'Total Trades: {s["total_trades"]}')
print(f'Win Rate: {s["win_rate"]*100:.2f}%')
print(f'Win: {s["win_count"]} | Loss: {s["loss_count"]}')
print(f'Final Equity: {s["final_equity"]:,.0f}')
print(f'Max Drawdown: {s["max_drawdown_pct"]*100:.2f}%')
print(f'Sharpe: {s["sharpe_ratio"]:.2f}')
print(f'Profit Factor: {s["profit_factor"]:.2f}')
print(f'Avg Trade: {s["avg_trade"]:.2f}')
print(f'Done', flush=True)