# Strategy Documentation

**Generated:** 2026-05-07
**Capital:** ₹1,00,000 | **Lot Size:** 15 | **Brokerage:** ₹5/side + 6.5% GST + 0.05% STT + 0.01% SEBI

---

## strategy_004/approach_D — Intraday Momentum Breakout

### Entry Logic
```
IF price > SMA20 AND RSI(14) > 62:
    BUY ATM CE
IF price < SMA20 AND RSI(14) < 38:
    BUY ATM PE
```

### Indicators Used
- SMA20: 20-period simple moving average of close
- RSI(14): 14-period Relative Strength Index

### Exit Logic
- **50% profit:** Close if P&L >= 50% of entry premium
- **-30% stop loss:** Close if P&L <= -30% of entry premium
- **Time exit:** After 60 ticks (60 hours on hourly data)

### Stats (3yr backtest)
| Metric | Value |
|--------|-------|
| Trades | 1,231 |
| Sharpe | 3.870 |
| Win Rate | 45.4% |
| Max Drawdown | 16.0% |
| Profit Factor | 2.15 |
| P&L | ₹930,241 |

### Trade Log
`journal/trade_logs/strategy_004_approach_D.json`

---

## strategy_006/approach_B — LSTM Momentum

### Entry Logic
```
IF RSI(9) > 60 AND RSI(14) > 55 AND SMA20 > SMA50:
    BUY ATM CE
IF RSI(9) < 40 AND RSI(14) < 45 AND SMA20 < SMA50:
    BUY ATM PE
```

### Indicators Used
- RSI(9): 9-period Relative Strength Index (fast)
- RSI(14): 14-period Relative Strength Index (slow)
- SMA20: 20-period simple moving average
- SMA50: 50-period simple moving average

### Exit Logic
- **50% profit:** Close if P&L >= 50% of entry premium
- **-30% stop loss:** Close if P&L <= -30% of entry premium
- **Time exit:** After 60 ticks

### Stats (3yr backtest)
| Metric | Value |
|--------|-------|
| Trades | 1,235 |
| Sharpe | 3.876 |
| Win Rate | 47.2% |
| Max Drawdown | 15.6% |
| Profit Factor | 2.08 |
| P&L | ₹942,314 |

### Trade Log
`journal/trade_logs/strategy_006_approach_B.json`

---

## strategy_006/approach_A — ML Trend Signal

### Entry Logic
```
IF regime == 'trending_up' AND RSI(14) > 55 AND price > BB_upper:
    BUY ATM CE
IF regime == 'trending_down' AND RSI(14) < 45 AND price < BB_lower:
    BUY ATM PE
```

### Indicators Used
- Regime: Classified as trending_up/down/range_bound based on ATR%, price vs SMA20, RSI
- RSI(14): 14-period Relative Strength Index
- Bollinger Bands (BB_upper, BB_lower): 20-period

### Regime Detection
```
ATR% > 1.5%  → 'high_vol'
ATR% < 0.5%  → 'low_vol'
price > SMA20 AND RSI > 55 → 'trending_up'
price < SMA20 AND RSI < 45 → 'trending_down'
otherwise → 'range_bound'
```

### Exit Logic
- **50% profit:** Close if P&L >= 50% of entry premium
- **-30% stop loss:** Close if P&L <= -30% of entry premium
- **Time exit:** After 60 ticks

### Stats (3yr backtest)
| Metric | Value |
|--------|-------|
| Trades | 110 |
| Sharpe | 3.606 |
| Win Rate | 42.7% |
| Max Drawdown | 21.3% |
| Profit Factor | 1.97 |
| P&L | ₹123,350 |

### Trade Log
`journal/trade_logs/strategy_006_approach_A.json`

---

## strategy_003/approach_C — BB Squeeze Breakout

### Entry Logic
```
IF BB_width < 0.03 (squeeze) AND regime != 'high_vol':
    BUY ATM straddle
ELIF regime == 'high_vol':
    SELL ATM strangle
```

### Indicators Used
- BB_width: Bollinger Band width < 0.03 (squeeze condition)
- Regime: As defined above

### Exit Logic
- **50% profit:** Close if P&L >= 50% of entry premium
- **-30% stop loss:** Close if P&L <= -30% of entry premium
- **Time exit:** After 60 ticks

### Stats (3yr backtest)
| Metric | Value |
|--------|-------|
| Trades | 2,443 |
| Sharpe | 3.670 |
| Win Rate | 48.2% |
| Max Drawdown | 19.2% |
| Profit Factor | 2.01 |
| P&L | ₹1,793,928 |

### Trade Log
`journal/trade_logs/strategy_003_approach_C.json`

---

## strategy_006/approach_D — IV-Adaptive Regime

### Entry Logic
```
IF regime == 'low_vol' AND IV_ratio < 1.3:
    SELL ATM straddle  (low IV = cheap options to sell)
IF regime == 'high_vol' AND RSI(14) > 60:
    SELL OTM CE
IF regime == 'trending_up' AND RSI(14) > 55:
    BUY ATM CE
IF regime == 'trending_down' AND RSI(14) < 45:
    BUY ATM PE
```

### Indicators Used
- IV_ratio: Straddle price at 22% IV / Straddle price at 15% IV (IV regime proxy)
- Regime: As defined above
- RSI(14): 14-period Relative Strength Index

### Exit Logic
- **50% profit:** Close if P&L >= 50% of entry premium
- **-30% stop loss:** Close if P&L <= -30% of entry premium
- **Time exit:** After 60 ticks

### Stats (3yr backtest)
| Metric | Value |
|--------|-------|
| Trades | 600 |
| Sharpe | 3.488 |
| Win Rate | 46.8% |
| Max Drawdown | 20.1% |
| Profit Factor | 1.94 |
| P&L | ₹566,014 |

### Trade Log
`journal/trade_logs/strategy_006_approach_D.json`

---

## Common Parameters (All Strategies)

| Parameter | Value |
|-----------|-------|
| Min premium to enter | ₹20 |
| Max open positions | 3 |
| Option expiry (T) | 0.5 days (half-day expiry) |
| Strike rounding | Nearest 100 |
| ATM strike | Nearest 100 to spot price |
| Confidence threshold | >= 0.60 |
| Black-Scholes IV | 22% (fixed) |
| Risk-free rate | 7% |
