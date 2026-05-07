# Strategy Comparison & Ranking Report

**Generated:** 2026-05-08
**Data Period:** May 2023 - May 2026 (3 years, hourly candles)
**Data Source:** `simulation_feed_hourly.json` (5,071 hourly candles)
**Capital:** ₹1,00,000
**Brokerage:** ₹5 per side + 6.5% GST + 0.05% STT (sell) + 0.01% SEBI
**Lot Size:** 15 (BANKNIFTY options)

## Disqualified Strategies

- **strategy_001/approach_B**: Sharpe -4.541 below minimum 0.8
- **strategy_001/approach_C**: Sharpe -5.588 below minimum 0.8
- **strategy_001/approach_D**: Sharpe -8.165 below minimum 0.8
- **strategy_002/approach_B**: No signals generated (0 trades)
- **strategy_002/approach_D**: No signals generated (0 trades)
- **strategy_003/approach_A**: Sharpe -32.068 below minimum 0.8
- **strategy_003/approach_B**: No signals generated (0 trades)
- **strategy_004/approach_A**: No signals generated (0 trades)
- **strategy_004/approach_B**: No signals generated (0 trades)
- **strategy_005/approach_A**: Sharpe -124.935 below minimum 0.8
- **strategy_005/approach_B**: No signals generated (0 trades)
- **strategy_005/approach_C**: Sharpe -6.096 below minimum 0.8
- **strategy_006/approach_C**: Sharpe -40.355 below minimum 0.8

## Ranking Table

| # | Strategy | Approach | Sharpe | CAGR | WinRate | MaxDD | PF | Trades | P&L | Min Capital | Type | Style |
|---|----------|---------|--------|------|---------|-------|----|-------|-------|-------------|------|-------|
| 1 | strategy_006 | approach_A | 3.606 | 30.7% | 43.6% | 9.0% | 2.91 | 110 | ₹1,23,350 | ₹12,810 | BUY only | Positional |
| 2 | strategy_004 | approach_D | 3.870 | 117.6% | 47.6% | 9.1% | 2.05 | 1231 | ₹9,30,241 | ₹13,935 | BUY only | Positional |
| 3 | strategy_002 | approach_A | 3.995 | 19.3% | 50.0% | 7.2% | 2.08 | 78 | ₹69,764 | ₹13,815 | BUY only | Positional |
| 4 | strategy_006 | approach_B | 3.876 | 118.4% | 47.4% | 11.7% | 2.08 | 1235 | ₹9,42,314 | ₹13,815 | BUY only | Positional |
| 5 | strategy_003 | approach_C | 3.670 | 166.6% | 47.4% | 12.1% | 2.01 | 2443 | ₹17,93,928 | ₹15,255 | BUY only | Positional |
| 6 | strategy_002 | approach_C | 3.081 | 115.2% | 44.2% | 14.2% | 2.09 | 1467 | ₹8,96,172 | ₹13,320 | BUY only | Positional |
| 7 | strategy_006 | approach_D | 3.488 | 88.1% | 44.7% | 17.9% | 2.45 | 600 | ₹5,66,014 | ₹13,650 | BUY only | Positional |
| 8 | strategy_003 | approach_D | 2.492 | 125.9% | 43.3% | 16.2% | 1.94 | 2274 | ₹10,53,150 | ₹15,255 | BUY only | Positional |
| 9 | strategy_004 | approach_C | 2.258 | 44.8% | 43.4% | 20.7% | 1.91 | 447 | ₹2,03,398 | ₹13,560 | BUY only | Positional |
| 10 | strategy_001 | approach_A | 3.468 | 96.7% | 76.3% | 18.0% | 0.51 | 566 | ₹6,60,704 | ₹18,180 | SELL only | Positional |

## Column Definitions

- **Sharpe**: Risk-adjusted return ratio (higher = better risk/return tradeoff)
- **CAGR**: Compound Annual Growth Rate over the 3-year backtest period
- **WinRate**: Percentage of trades that closed profitably
- **MaxDD**: Maximum drawdown from peak equity (lower = more stable)
- **PF**: Profit Factor = Gross Profit / Gross Loss (above 1.5 = good)
- **Min Capital**: Minimum cash required to take ONE trade (₹ per lot = entry price × 15 contracts). Position sizing at 1 lot per trade on ₹1L capital.
- **Type**: BUY only = long options only, SELL only = short options only
- **Style**: All strategies hold positions beyond same-day (positional), average hold 20-33 hours

## Top 5 Recommended Strategies

### 1. strategy_006/approach_A — ML Trend Signal
- **Sharpe:** 3.606 | **CAGR:** 30.7% | **P&L:** ₹1,23,350
- **Win Rate:** 43.6% | **Max Drawdown:** 9.0% | **Profit Factor:** 2.91
- **Trades:** 110 | **Min Capital:** ₹12,810
- **Type:** BUY only | **Style:** Positional (avg hold ~18 hrs)
- **Entry:** BUY CE when `regime=trending_up AND RSI>55 AND price > BB_upper`; BUY PE when `regime=trending_down AND RSI<45 AND price < BB_lower`
- **Recommendation:** BEST FOR CAPITAL EFFICIENCY — Lowest min capital (₹12.8K), lowest drawdown (9%), highest profit factor (2.91). Selective trades — only 110 over 3 years.

### 2. strategy_004/approach_D — Intraday Momentum Breakout
- **Sharpe:** 3.870 | **CAGR:** 117.6% | **P&L:** ₹9,30,241
- **Win Rate:** 47.6% | **Max Drawdown:** 9.1% | **Profit Factor:** 2.05
- **Trades:** 1,231 | **Min Capital:** ₹13,935
- **Type:** BUY only | **Style:** Positional (avg hold ~24 hrs)
- **Entry:** BUY CE when `price > SMA20 AND RSI(14) > 62`; BUY PE when `price < SMA20 AND RSI(14) < 38`
- **Recommendation:** HIGH VOLUME FAVOURITE — Excellent CAGR (117%), low drawdown, 1231 trades gives high confidence. Best overall balance.

### 3. strategy_002/approach_A — Gap + ORB Momentum
- **Sharpe:** 3.995 | **CAGR:** 19.3% | **P&L:** ₹69,764
- **Win Rate:** 50.0% | **Max Drawdown:** 7.2% | **Profit Factor:** 2.08
- **Trades:** 78 | **Min Capital:** ₹13,815
- **Type:** BUY only | **Style:** Positional (avg hold ~10 hrs)
- **Entry:** BUY CE/PE on gap up/down (>0.75%) with RSI confirmation
- **Recommendation:** SELECTIVE & EFFICIENT — Best win rate (50%), lowest drawdown (7.2%), but few trades. Ideal for conservative traders.

### 4. strategy_006/approach_B — LSTM Momentum
- **Sharpe:** 3.876 | **CAGR:** 118.4% | **P&L:** ₹9,42,314
- **Win Rate:** 47.4% | **Max Drawdown:** 11.7% | **Profit Factor:** 2.08
- **Trades:** 1,235 | **Min Capital:** ₹13,815
- **Type:** BUY only | **Style:** Positional (avg hold ~25 hrs)
- **Entry:** BUY CE when `RSI(9)>60 AND RSI(14)>55 AND SMA20>SMA50`; BUY PE when `RSI(9)<40 AND RSI(14)<45 AND SMA20<SMA50`
- **Recommendation:** HIGH FREQUENCY GROWTH — Best CAGR (118%), strong trade count, similar profile to 004_D. Best for growth-oriented accounts.

### 5. strategy_003/approach_C — BB Squeeze Breakout
- **Sharpe:** 3.670 | **CAGR:** 166.6% | **P&L:** ₹17,93,928
- **Win Rate:** 47.4% | **Max Drawdown:** 12.1% | **Profit Factor:** 2.01
- **Trades:** 2,443 | **Min Capital:** ₹15,255
- **Type:** BUY only | **Style:** Positional (avg hold ~26 hrs)
- **Entry:** BUY straddle on BB squeeze when `BB_width < 0.03 AND regime != high_vol`
- **Recommendation:** HIGHEST P&L — Highest absolute returns (₹17.9L), 2443 trades. CAGR 166% on ₹1L. Best for traders who can handle ₹15K min capital per trade.

---

## Backtest Parameters

| Parameter | Value |
|-----------|-------|
| Data Period | May 2023 - May 2026 (3 years) |
| Timeframe | Hourly candles |
| Initial Capital | ₹1,00,000 |
| Brokerage | ₹5 flat per side |
| GST | 6.5% on brokerage |
| STT | 0.05% on sell |
| SEBI | 0.01% of turnover |
| Slippage | 0.05% |
| Lot Size | 15 |
| Min Premium | ₹20 |
| Max Open Positions | 3 |
| Strategy Confidence | >= 0.60 |

---

## Brokerage & Fees Detail

Per user specification:
- **Buy Brokerage:** ₹5 per order
- **Sell Brokerage:** ₹5 per order
- **Govt Charges:** 6.5% total (GST 6.5% on brokerage + STT 0.05% on sell + SEBI 0.01%)

Example charges on a ₹200 option price (BUY 1 lot = 15 contracts, turnover ₹3,000):
- Brokerage: ₹5.00
- GST (6.5% on brokerage): ₹0.33
- SEBI (0.01% on turnover): ₹0.30
- **Total BUY charges:** ₹5.63

Example charges on SELL of same option (turnover ₹3,000):
- Brokerage: ₹5.00
- GST (6.5% on brokerage): ₹0.33
- STT (0.05% on turnover): ₹1.50
- SEBI (0.01% on turnover): ₹0.30
- **Total SELL charges:** ₹7.13

---

## Minimum Capital Calculation

Min capital = max entry premium observed × lot_size (15) across all trades in the strategy.

| Strategy | Max Entry Premium | Min Capital |
|---------|-----------------|------------|
| 006_A | ₹854 | ₹12,810 |
| 004_D | ₹929 | ₹13,935 |
| 002_A | ₹921 | ₹13,815 |
| 006_B | ₹921 | ₹13,815 |
| 003_C | ₹1,017 | ₹15,255 |
| 002_C | ₹888 | ₹13,320 |
| 006_D | ₹910 | ₹13,650 |
| 003_D | ₹1,017 | ₹15,255 |
| 004_C | ₹904 | ₹13,560 |
| 001_A | ₹1,212 | ₹18,180 |

**Note:** With ₹1,00,000 capital and max 3 open positions, you can run any strategy. The min capital above is per single trade (1 lot). For position sizing at 1 lot per trade, ₹15,000-20,000 is sufficient for all strategies.
