# Nifty 50 Scalping Strategy — Nifty50_Scalping

## Overview
**Strategy ID**: approach_F_scalping
**Instrument**: Nifty 50 Options (Weekly Expiry)
**Timeframe**: 1-Minute
**Execution Window**: 09:20 – 15:15

## Strategy Description
Intraday momentum breakout scalping on Nifty 50 using SMA20 and RSI14 indicators.
Entry signals are confirmed by volume surges to reduce false breakouts.

---

## Entry Rules

### Call Entry (Buy CE)
- **Trend**: Close > SMA(20, 1min)
- **Momentum**: RSI(14) > 60 OR Volume > 1.5× previous volume
- **Strike Selection**: 1 step OTM (50-point step above ATM)
- **Lot Size**: 1 lot (Nifty lot = 75 contracts)

### Put Entry (Buy PE)
- **Trend**: Close < SMA(20, 1min)
- **Momentum**: RSI(14) < 40 OR price breaking below recent 1-min support
- **Strike Selection**: 1 step OTM (50-point step below ATM)
- **Lot Size**: 1 lot (Nifty lot = 75 contracts)

---

## Exit Rules (Priority Order)

| Priority | Condition | Action |
|----------|-----------|--------|
| 1 | +5 points on option premium | Take Profit (TP) |
| 2 | -15% on entry premium | Stop Loss (SL) |
| 3 | Price crosses SMA20 against position | SMA Reversal Exit |
| 4 | 15:15 End of Day | Hard Exit (EOD) |

### Exit Reason Definitions
- **TP hit**: When option premium increases by 5 or more points from entry
- **SL hit**: When option premium falls to 85% of entry premium (15% loss)
- **SMA reversal**: Call exits when price < SMA20; Put exits when price > SMA20
- **EOD**: Forced square-off at 15:15

---

## Brokerage & Charges

Per side (both buy and sell):
- **Flat Brokerage**: ₹5 per trade
- **GST**: 6.5% on brokerage
- **STT (Securities Transaction Tax)**: 0.05% on sell turnover
- **SEBI Charges**: 0.01% on turnover
- **Stamp Duty**: 0.05% on buy turnover
- **Slippage**: 0.05% applied to fill price

---

## Position Management
- **Sizing**: 1 lot per trade (fixed)
- **Strike**: OTM by 1 step (50-point Nifty step)
- **Expiry Assumption**: 0.5 days (weekly expiry used for BS pricing)
- **Margin Required**: ~20% of notional value

---

## Technical Implementation

- **Execution model**: Signal at bar i → fill at bar (i+1) OPEN for entries; exit at current bar CLOSE for exits (TradeTron-consistent)
- **Option Pricing**: Black-Scholes with 22% IV, 7% risk-free rate
- **Data Source**: Real Nifty 50 1-minute OHLCV from Kaggle (2015–2026, CC0 license) — data/NIFTY 50_minute.csv
- **Backtest Period**: 2025-01-02 to 2026-04-08 (~15 months, 110,840 bars)

### Backtest Results (Real Data, 5-Point TP)
```
  Initial Capital   : Rs.  100,000.00
  Final Equity      : Rs.   130,287.63
  Net P&L           : Rs.    30,287.63  (+30.3%)
  Total Trades      :       12,071
  Win Rate          :       47.69%
  Profit Factor     :        1.14
  Max Drawdown      :       86.00%
  Sharpe Ratio     :        0.29
  Best Trade        :   Rs.  4,823.51
  Worst Trade       :   Rs. -3,381.23
  Avg Trade         :   Rs.     10.42
```

### Exit Reason Breakdown
- **TP hits (5-point)**: 5,559 trades (46.1%)
- **SMA reversal**: 4,605 trades (38.1%)
- **SL hits (15%)**: 1,721 trades (14.3%)
- **EOD hard exit**: 186 trades (1.5%)

### Key Realizations
- 5-point TP is hit frequently (46% of trades), but the 15% SL combined with SMA reversals (38%) creates a mixed outcome.
- Exit fill at next-bar OPEN gave option-like fill prices (spot prices). Fixed to BS-computed option price at current bar close.
- Synthetic data produced 100% win rate. Real Kaggle data shows realistic 47.7% win rate.
- **Critical bug found**: `_within_window()` parsed only strings, rejecting pandas Timestamp objects directly — all entries were silently skipped until fixed.

### Backtest Parameters
- **Period**: 2025-01-02 to 2026-04-30 (~15 months)
- **Bars**: 123,176 (filtered to 09:20–15:15 window)
- **Initial Capital**: ₹100,000
- **Lot Size**: 75 contracts

---

## Files

| File | Description |
|------|-------------|
| `algo/core/strategy_n50_scalping.py` | Strategy implementation with SMA20+RSI14 entry/exit |
| `backtests/scalping_backtest.py` | Scalping backtest engine (shared by all strategies) |
| `run_backtest.py` | Entry point to run the backtest |
| `backtest_output.json` | Full results: trades, stats, equity curve |
| `backtest_output.txt` | Run log |

---

## Disclaimer

**Synthetic Data Notice**: This backtest uses regime-based synthetic 1-minute data for Nifty 50.
Real trading results will differ significantly. Not a guarantee of future performance.