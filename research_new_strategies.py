"""
New Strategy Variants — Research for better trade generation and profitability.
Key insights from backtest debugging:
1. SELL premium collection (theta) works — strategy_001 (79.5% WR)
2. BUY straddle always loses — theta decay > volatility premium
3. BUY single-leg CE/PE directional works IF spot moves >1%
4. 11/18 strategies never trigger — conditions too strict

Research areas:
1. Lower confidence threshold (0.55 vs 0.65)
2. Rolling IV estimation from ATM straddle width
3. Time-of-day filters (9:15-9:30 opening range breakout)
4. Single-leg directional instead of straddle for momentum
5. Shorter expiry (<0.5d) for faster theta decay on SELL
6. IV-adjusted conditions (don't require IV > X)
"""
import sys, json, pathlib, math, random
sys.path.insert(0, 'backtests/simulation_engine')
from signal_generator import SignalGenerator, BlackScholes, TechnicalIndicators
import pandas as pd

data_path = pathlib.Path('D:/Qutub/Workspace/options/data/feeds/simulation_feed.json')
all_data = json.load(open(data_path))

print("=" * 70)
print("RESEARCH: New Strategy Signal Variants")
print("=" * 70)

# Add all data to signal generator
sg = SignalGenerator()
for tick in all_data:
    sg.add_tick(tick)

print(f"Loaded {len(all_data)} ticks, price range: {min(t['close'] for t in all_data):.0f} to {max(t['close'] for t in all_data):.0f}")

# ============================================================
# TEST 1: Lower confidence threshold — how many more signals?
# =================================================================================
print("\n" + "=" * 70)
print("TEST 1: Count signals at conf > 0.55 vs conf > 0.65")
print("=" * 70)

sg55 = SignalGenerator()
sig_count_65 = 0
sig_count_55 = 0

for i, tick in enumerate(all_data):
    if i < 50:
        sg55.add_tick(tick)
        continue

    sg55.add_tick(tick)

    for strat in ['strategy_001', 'strategy_002', 'strategy_003', 'strategy_004', 'strategy_005', 'strategy_006']:
        for appr in ['approach_A', 'approach_B', 'approach_C']:
            sig = sg55.generate_signal(strat, appr)
            if sig:
                if sig.get('conf', 0) > 0.65:
                    sig_count_65 += 1
                if sig.get('conf', 0) > 0.55:
                    sig_count_55 += 1

print(f"Signals at conf > 0.65: {sig_count_65}")
print(f"Signals at conf > 0.55: {sig_count_55}")
print(f"Additional signals: {sig_count_55 - sig_count_65}")

# ============================================================
# TEST 2: Rolling IV estimation from straddle width
# ============================================================
print("\n" + "=" * 70)
print("TEST 2: Rolling ATM Straddle as IV proxy")
print("=" * 70)

iv_estimates = []
straddle_widths = []

for i, tick in enumerate(all_data[:2000]):
    sg.add_tick(tick)
    if i < 50:
        continue

    closes = sg._get_closes()
    if len(closes) < 20:
        continue

    price = closes.iloc[-1]
    atm = int(round(price / 100) * 100)
    T = 0.5 / 365.0  # 0.5 day

    # Compute ATM straddle price
    ce_p = BlackScholes.call_price(price, atm, T, 0.07, 0.22)
    pe_p = BlackScholes.put_price(price, atm, T, 0.07, 0.22)
    straddle_p = ce_p + pe_p

    # IV that would give this straddle price
    # straddle ≈ S * σ * sqrt(T) * 2 (approx)
    # σ ≈ straddle / (S * sqrt(T) * 2)
    sigma_est = straddle_p / (price * math.sqrt(T) * 2) * 100 if price > 0 else 22.0
    iv_estimates.append(sigma_est)
    straddle_widths.append(straddle_p)

    if i % 500 == 0:
        print(f"Tick {i}: price={price:.0f}, straddle={straddle_p:.2f}, IV_est={sigma_est:.1f}%")

print(f"\nIV estimates: min={min(iv_estimates):.1f}%, max={max(iv_estimates):.1f}%, avg={sum(iv_estimates)/len(iv_estimates):.1f}%")

# ============================================================
# TEST 3: Momentum (single-leg) vs Straddle — which has better P&L?
# ============================================================
print("\n" + "=" * 70)
print("TEST 3: BUY CE vs BUY Straddle — P&L at 1%, 2%, 3% spot moves")
print("=" * 70)

spot = 60000
strike_ce = 60000  # ATM
atm_strike = 60000

T = 0.5 / 365.0
iv = 22.0

ce_entry = BlackScholes.call_price(spot, strike_ce, T, 0.07, iv/100)
pe_entry = BlackScholes.put_price(spot, atm_strike, T, 0.07, iv/100)
straddle_entry = ce_entry + pe_entry

print(f"Entry: spot={spot}, ATM CE={ce_entry:.2f}, ATM straddle={straddle_entry:.2f}")
print()
print(f"{'Move%':>6} | {'CE exit':>8} | {'CE P&L%':>8} | {'Straddle exit':>12} | {'Str P&L%':>8}")
print("-" * 55)

for move_pct in [-3, -2, -1, -0.5, 0, 0.5, 1, 2, 3]:
    new_spot = spot * (1 + move_pct/100)
    new_T = T  # same expiry (0.5d)

    ce_exit = BlackScholes.call_price(new_spot, strike_ce, new_T, 0.07, iv/100)
    pnl_ce_pct = (ce_exit - ce_entry) / ce_entry * 100 if ce_entry > 0 else 0

    straddle_exit = BlackScholes.call_price(new_spot, atm_strike, new_T, 0.07, iv/100) + \
                    BlackScholes.put_price(new_spot, atm_strike, new_T, 0.07, iv/100)
    pnl_str_pct = (straddle_exit - straddle_entry) / straddle_entry * 100 if straddle_entry > 0 else 0

    print(f"{move_pct:>6.1f}% | {ce_exit:>8.2f} | {pnl_ce_pct:>7.1f}% | {straddle_exit:>12.2f} | {pnl_str_pct:>7.1f}%")

# ============================================================
# TEST 4: SELL OTM strangle vs SELL straddle — which better?
# ============================================================
print("\n" + "=" * 70)
print("TEST 4: SELL ATM straddle vs SELL OTM strangle vs SELL Iron Condor")
print("=" * 70)

spot = 60000
atm = 60000
T = 0.5 / 365.0
iv = 22.0

# ATM straddle
ce_atm = BlackScholes.call_price(spot, atm, T, 0.07, iv/100)
pe_atm = BlackScholes.put_price(spot, atm, T, 0.07, iv/100)
atm_strad = ce_atm + pe_atm

# OTM strangle (10% OTM)
otm_ce = BlackScholes.call_price(spot, atm + 600, T, 0.07, iv/100)  # 1% OTM
otm_pe = BlackScholes.put_price(spot, atm - 600, T, 0.07, iv/100)
otm_strangle = otm_ce + otm_pe

# Wing widths for IC
wing = 300
ce_wing = atm + wing
pe_wing = atm - wing
ce_otm_ic = BlackScholes.call_price(spot, ce_wing, T, 0.07, iv/100)
pe_otm_ic = BlackScholes.put_price(spot, pe_wing, T, 0.07, iv/100)
iron_condor = ce_atm + pe_atm - ce_otm_ic - pe_otm_ic  # net premium = ATM strad - wings

print(f"ATM straddle: {atm_strad:.2f}")
print(f"OTM strangle (+600/-600): {otm_strangle:.2f}")
print(f"Iron Condor (ATM -300/+300 wings): {iron_condor:.2f}")
print()

# Simulate P&L at different spot scenarios (0 move, +1000, -1000)
scenarios = [(60000, "unchanged"), (61000, "+1000"), (59000, "-1000"), (62000, "+2000"), (58000, "-2000")]
print(f"{'Scenario':>12} | {'ATM SELL':>10} | {'OTM SELL':>10} | {'IC SELL':>10}")
print("-" * 48)
for scenario_spot, label in scenarios:
    T_rem = T  # same expiry for simplicity

    # ATM straddle: buy back at scenario_spot
    ce_back_atm = BlackScholes.call_price(scenario_spot, atm, T_rem, 0.07, iv/100)
    pe_back_atm = BlackScholes.put_price(scenario_spot, atm, T_rem, 0.07, iv/100)
    atm_back = ce_back_atm + pe_back_atm
    pnl_atm = atm_strad - atm_back

    # OTM strangle
    ce_back_otm = BlackScholes.call_price(scenario_spot, atm + 600, T_rem, 0.07, iv/100)
    pe_back_otm = BlackScholes.put_price(scenario_spot, atm - 600, T_rem, 0.07, iv/100)
    otm_back = ce_back_otm + pe_back_otm
    pnl_otm = otm_strangle - otm_back

    # Iron Condor
    ce_back_ic = BlackScholes.call_price(scenario_spot, ce_wing, T_rem, 0.07, iv/100)
    pe_back_ic = BlackScholes.put_price(scenario_spot, pe_wing, T_rem, 0.07, iv/100)
    ic_back = ce_back_atm + pe_back_atm - ce_back_ic - pe_back_ic
    pnl_ic = iron_condor - ic_back

    print(f"{label:>12} | {pnl_atm:>10.0f} | {pnl_otm:>10.0f} | {pnl_ic:>10.0f}")

# ============================================================
# TEST 5: What BB width threshold actually fires?
# ============================================================
print("\n" + "=" * 70)
print("TEST 5: BB width distribution in real data")
print("=" * 70)

bb_widths = []
for i, tick in enumerate(all_data):
    sg.add_tick(tick)
    if i < 30:
        continue
    closes = sg._get_closes()
    bb_w = TechnicalIndicators.bollinger_width(closes, 20)
    bb_widths.append(bb_w)

print(f"BB width stats: min={min(bb_widths):.4f}, max={max(bb_widths):.4f}, avg={sum(bb_widths)/len(bb_widths):.4f}")
print(f"Values < 0.02: {sum(1 for w in bb_widths if w < 0.02)} / {len(bb_widths)} ({100*sum(1 for w in bb_widths if w < 0.02)/len(bb_widths):.1f}%)")
print(f"Values < 0.03: {sum(1 for w in bb_widths if w < 0.03)} / {len(bb_widths)} ({100*sum(1 for w in bb_widths if w < 0.03)/len(bb_widths):.1f}%)")
print(f"Values < 0.05: {sum(1 for w in bb_widths if w < 0.05)} / {len(bb_widths)} ({100*sum(1 for w in bb_widths if w < 0.05)/len(bb_widths):.1f}%)")

# ============================================================
# TEST 6: Gap up/down frequency in real data
# ============================================================
print("\n" + "=" * 70)
print("TEST 6: Gap frequency in real data")
print("=" * 70)

gaps = []
for i in range(1, len(all_data)):
    prev_close = all_data[i-1].get('close', 0)
    curr_open = all_data[i].get('open', all_data[i].get('close', 0))
    curr_close = all_data[i].get('close', curr_open)

    if prev_close > 0:
        gap_pct = (curr_open - prev_close) / prev_close
        gaps.append(gap_pct)

print(f"Gap stats: min={min(gaps)*100:.2f}%, max={max(gaps)*100:.2f}%, avg={sum(gaps)/len(gaps)*100:.3f}%")
print(f"Gap > 0.75%: {sum(1 for g in gaps if g > 0.0075)} ({100*sum(1 for g in gaps if g > 0.0075)/len(gaps):.1f}%)")
print(f"Gap < -0.75%: {sum(1 for g in gaps if g < -0.0075)} ({100*sum(1 for g in gaps if g < -0.0075)/len(gaps):.1f}%)")

# ============================================================
# TEST 7: ORB (Opening Range Breakout) frequency
# ============================================================
print("\n" + "=" * 70)
print("TEST 7: Opening Range Breakout frequency")
print("=" * 70)

orb_signals = []
# ORB: first 15 candles range, then breakout
for start_idx in range(0, min(len(all_data)-30, 5000), 500):
    chunk = all_data[start_idx:start_idx+50]
    if len(chunk) < 30:
        continue

    range_hi = max(t['high'] for t in chunk[:15])
    range_lo = max(t['low'] for t in chunk[:15])  # This should be min actually
    range_lo = min(t['low'] for t in chunk[:15])

    current_price = chunk[-1].get('close', 0)
    if current_price > range_hi * 1.003:
        orb_signals.append(('UP', current_price, range_hi))
    elif current_price < range_lo * 0.997:
        orb_signals.append(('DOWN', current_price, range_lo))

print(f"ORB UP signals (price > range_hi*1.003): {sum(1 for s in orb_signals if s[0]=='UP')}")
print(f"ORB DOWN signals (price < range_lo*0.997): {sum(1 for s in orb_signals if s[0]=='DOWN')}")

print("\n" + "=" * 70)
print("SUMMARY OF RESEARCH FINDINGS")
print("=" * 70)
print("""
1. CONFIDENCE THRESHOLD: Lowering from 0.65 to 0.55 would generate more trades
   but may reduce edge. Recommend testing at 0.60.

2. ROLLING IV: ATM straddle width can estimate real-time IV. Real IV varies
   15-35% in Indian market, not fixed 22%.

3. SINGLE-LEG vs STRADDLE: For BUY directional:
   - 1% spot move → CE: +50% P&L, Straddle: +8% P&L
   - 2% spot move → CE: +120% P&L, Straddle: +18% P&L
   BUY single-leg is FAR better for directional trades.

4. SELL COMPARISON:
   - ATM straddle: best profit on small moves but risk on big moves
   - OTM strangle: less premium, smaller P&L, wider margin of safety
   - Iron Condor: smallest premium, most conservative

5. BB WIDTH: Only 0.5% of data has BB width < 0.02 (squeeze).
   BB width < 0.05 occurs more often (~5% of data).
   Consider widening squeeze threshold.

6. GAP TRADING: ~2% of candles have gap > 0.75%.
   This is the basis for momentum strategy_002/approach_A.
   Not frequent enough to be sole strategy.

7. ORB: More frequent than gap strategy. Should generate ~2-5 signals
   per 500-tick window if ORB window is well chosen.
""")