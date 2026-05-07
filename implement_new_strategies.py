"""
New Strategy Implementation — Based on Research Findings

Key findings:
1. BB width < 0.02 is TRUE 91% of the time — squeeze condition triggers too often
2. Single-leg CE/PE FAR outperforms straddle for directional moves (1% spot = CE +219%, Straddle +69%)
3. Gap >0.75% only 0.5% of time — approach_A for strategy_002 generates very few signals
4. OTM strangle provides less premium but wider safety margin
5. Iron Condor: smallest premium but most consistent small profits on wide moves

Implementation changes:
1. Widen BB squeeze threshold for approach_A to 0.05 (catches 98.5% of data vs 91%)
2. Change strategy_003/approach_A from BUY straddle to BUY single-leg (CE or PE)
3. Add ORB-based strategy with tighter conditions to generate more trades
4. Add SELL OTM strangle variant for strategy_001 (safer than ATM straddle)
5. Lower confidence threshold to 0.55 for all strategies
"""
import sys, json, pathlib
sys.path.insert(0, 'backtests/simulation_engine')
from signal_generator import SignalGenerator, BlackScholes, TechnicalIndicators
import pandas as pd
import math

# ============================================================
# NEW STRATEGY 001 - approach_D: SELL OTM strangle (safer premium)
# ============================================================
def generate_strategy_001_approach_D(sg, price, rsi14, bb_width, bb_upper, bb_lower, regime):
    """Sell OTM strangle instead of ATM straddle - less premium but wider margin of safety."""
    if len(sg.price_history) < 30:
        return None

    atm = sg.get_atm_strike(price, 200)
    wing = 400  # OTM by 400 points (~0.7% OTM)

    # Sell strangle: CE at ATM+wing, PE at ATM-wing
    ce_strike = atm + wing
    pe_strike = atm - wing

    T = 0.5 / 365.0
    iv = sg.option_iv / 100

    ce_p = BlackScholes.call_price(price, ce_strike, T, sg.risk_free_rate, iv)
    pe_p = BlackScholes.put_price(price, pe_strike, T, sg.risk_free_rate, iv)
    total_premium = ce_p + pe_p

    if total_premium > 40:  # Minimum premium
        return {
            "action": "SELL",
            "strike": atm,
            "opt": "STRANGLE",
            "lots": 1,
            "reason": f"OTM strangle: CE={ce_strike}, PE={pe_strike}, prem={total_premium:.0f}",
            "conf": 0.65,
            "ce_strike": ce_strike,
            "pe_strike": pe_strike
        }
    return None

# ============================================================
# NEW STRATEGY 003 - approach_D: BUY single-leg instead of straddle
# ============================================================
def generate_strategy_003_approach_D(sg, price, rsi14, bb_width, bb_upper, bb_lower, regime):
    """BB squeeze but BUY single-leg CE or PE instead of straddle.

    Rationale: 1% spot move -> CE +219% vs Straddle +69%. Single leg wins.
    Use RSI to determine direction:
    - RSI < 40 -> expect bounce -> BUY CE
    - RSI > 60 -> expect drop -> BUY PE
    - Otherwise -> expect expansion both ways -> straddle (but we use single leg)
    """
    if bb_width < 0.05 and len(sg.price_history) > 30:
        atm = sg.get_atm_strike(price, 200)

        if rsi14 < 40:
            return {
                "action": "BUY",
                "strike": atm,
                "opt": "CE",
                "lots": 1,
                "reason": f"BB squeeze + oversold: w={bb_width:.3f}, RSI={rsi14:.1f}",
                "conf": 0.7,
                "ce_strike": atm,
                "pe_strike": atm
            }
        elif rsi14 > 60:
            return {
                "action": "BUY",
                "strike": atm,
                "opt": "PE",
                "lots": 1,
                "reason": f"BB squeeze + overbought: w={bb_width:.3f}, RSI={rsi14:.1f}",
                "conf": 0.7,
                "ce_strike": atm,
                "pe_strike": atm
            }
        else:
            # Middle RSI - still squeeze but neutral
            return {
                "action": "BUY",
                "strike": atm,
                "opt": "CE",  # Neutral - bias up
                "lots": 1,
                "reason": f"BB squeeze: w={bb_width:.3f}",
                "conf": 0.65,
                "ce_strike": atm,
                "pe_strike": atm
            }
    return None

# ============================================================
# NEW STRATEGY 002 - approach_D: VWAP mean reversion (more signals)
# ============================================================
def generate_strategy_002_approach_D(sg, price, rsi14, vwap_val, sma20):
    """VWAP mean reversion - more frequent than gap or ORB strategies.

    Entry: price > VWAP + 0.5% AND RSI > 60 -> sell
    Entry: price < VWAP - 0.5% AND RSI < 40 -> buy
    """
    if len(sg.price_history) < 20:
        return None

    if price > vwap_val * 1.005 and rsi14 > 60:
        atm = sg.get_atm_strike(price, 100)
        return {
            "action": "SELL",
            "strike": atm,
            "opt": "PE",
            "lots": 1,
            "reason": f"VWAP over: price={price:.0f}, VWAP={vwap_val:.0f}, RSI={rsi14:.1f}",
            "conf": 0.65,
            "ce_strike": atm,
            "pe_strike": atm
        }
    elif price < vwap_val * 0.995 and rsi14 < 40:
        atm = sg.get_atm_strike(price, 100)
        return {
            "action": "BUY",
            "strike": atm,
            "opt": "CE",
            "lots": 1,
            "reason": f"VWAP under: price={price:.0f}, VWAP={vwap_val:.0f}, RSI={rsi14:.1f}",
            "conf": 0.65,
            "ce_strike": atm,
            "pe_strike": atm
        }
    return None

# ============================================================
# NEW STRATEGY 004 - approach_D: Intraday momentum
# ============================================================
def generate_strategy_004_approach_D(sg, price, rsi14, rsi9, sma20):
    """Intraday momentum with RSI confirmation.

    Entry: price > SMA20 AND RSI(9) > 65 -> BUY CE
    Entry: price < SMA20 AND RSI(9) < 35 -> BUY PE
    """
    if len(sg.price_history) < 20:
        return None

    if price > sma20 and rsi9 > 65:
        atm = sg.get_atm_strike(price, 100)
        return {
            "action": "BUY",
            "strike": atm,
            "opt": "CE",
            "lots": 1,
            "reason": f"Intraday long: RSI9={rsi9:.1f}, price>{sma20:.0f}",
            "conf": 0.65,
            "ce_strike": atm,
            "pe_strike": atm
        }
    elif price < sma20 and rsi9 < 35:
        atm = sg.get_atm_strike(price, 100)
        return {
            "action": "BUY",
            "strike": atm,
            "opt": "PE",
            "lots": 1,
            "reason": f"Intraday short: RSI9={rsi9:.1f}, price<{sma20:.0f}",
            "conf": 0.65,
            "ce_strike": atm,
            "pe_strike": atm
        }
    return None

# ============================================================
# NEW STRATEGY 006 - approach_D: Low IV regime (sell premium when IV is low)
# ============================================================
def generate_strategy_006_approach_D(sg, price, bb_width, regime, rsi14):
    """When IV is low AND regime is low_vol: sell premium.

    When IV is high AND regime is high_vol: buy directional.
    """
    if len(sg.price_history) < 30:
        return None

    # Approximate IV from straddle width
    atm = sg.get_atm_strike(price, 200)
    T = 0.5 / 365.0
    straddle_22 = BlackScholes.call_price(price, atm, T, sg.risk_free_rate, 0.22) + \
                   BlackScholes.put_price(price, atm, T, sg.risk_free_rate, 0.22)
    straddle_15 = BlackScholes.call_price(price, atm, T, sg.risk_free_rate, 0.15) + \
                   BlackScholes.put_price(price, atm, T, sg.risk_free_rate, 0.15)

    # If straddle at 22% IV is close to straddle at 15% IV, IV is LOW
    # (meaning actual IV is low, so options are cheap to sell)
    iv_ratio = straddle_22 / straddle_15 if straddle_15 > 0 else 1.0

    if regime == 'low_vol' and iv_ratio < 1.3:
        # Low IV regime - sell premium
        atm = sg.get_atm_strike(price, 200)
        return {
            "action": "SELL",
            "strike": atm,
            "opt": "STRADDLE",
            "lots": 1,
            "reason": f"Low IV regime: ratio={iv_ratio:.2f}",
            "conf": 0.70,
            "ce_strike": atm,
            "pe_strike": atm
        }
    elif regime == 'high_vol' and rsi14 > 60:
        # High vol + overbought - sell CE
        atm = sg.get_atm_strike(price, 200)
        return {
            "action": "SELL",
            "strike": atm + 200,
            "opt": "CE",
            "lots": 1,
            "reason": f"High vol regime: RSI={rsi14:.1f}",
            "conf": 0.65,
            "ce_strike": atm + 200,
            "pe_strike": atm - 200
        }
    return None

# ============================================================
# Test new strategies on real data
# ============================================================
print("=" * 70)
print("Testing New Strategy Variants on Real Data")
print("=" * 70)

data_path = pathlib.Path('D:/Qutub/Workspace/options/data/feeds/simulation_feed.json')
all_data = json.load(open(data_path))

new_strategies = {
    ('strategy_001', 'approach_D'): lambda sg, p, r, bw, bu, bl, reg: generate_strategy_001_approach_D(sg, p, r, bw, bu, bl, reg),
    ('strategy_003', 'approach_D'): lambda sg, p, r, bw, bu, bl, reg: generate_strategy_003_approach_D(sg, p, r, bw, bu, bl, reg),
    ('strategy_002', 'approach_D'): lambda sg, p, r, bw, bu, bl, reg: generate_strategy_002_approach_D(sg, p, r, bw, bu, bl, reg),
    ('strategy_004', 'approach_D'): lambda sg, p, r, bw, bu, bl, reg: generate_strategy_004_approach_D(sg, p, r, bw, bu, bl, reg),
    ('strategy_006', 'approach_D'): lambda sg, p, r, bw, bu, bl, reg: generate_strategy_006_approach_D(sg, p, r, bw, reg),
}

for (strat, appr), gen_func in new_strategies.items():
    print(f"\n{strat}/{appr}:")

    sg_test = SignalGenerator()
    sig_count = 0

    for i, tick in enumerate(all_data):
        sg_test.add_tick(tick)
        if i < 50:
            continue

        closes = sg_test._get_closes()
        highs = sg_test._get_highs()
        lows = sg_test._get_lows()

        if len(closes) < 20:
            continue

        price = closes.iloc[-1]
        rsi14 = TechnicalIndicators.rsi(closes, 14)
        rsi9 = TechnicalIndicators.rsi(closes, 9)
        bb_sma, bb_upper, bb_lower = TechnicalIndicators.bollinger_bands(closes, 20)
        bb_width = TechnicalIndicators.bollinger_width(closes, 20)
        atr_val = TechnicalIndicators.atr(highs, lows, closes, 14)
        vwap_val = TechnicalIndicators.vwap(highs, lows, closes, sg_test._get_volumes())
        sma20 = TechnicalIndicators.sma(closes, 20)

        atr_pct = (atr_val / price) * 100 if price > 0 else 0
        if atr_pct > 1.5:
            regime = 'high_vol'
        elif atr_pct < 0.5:
            regime = 'low_vol'
        elif price > sma20 and rsi14 > 55:
            regime = 'trending_up'
        elif price < sma20 and rsi14 < 45:
            regime = 'trending_down'
        else:
            regime = 'range_bound'

        sig = gen_func(sg_test, price, rsi14, bb_width, bb_upper, bb_lower, regime)
        if sig and sig.get('conf', 0) > 0.60:
            sig_count += 1
            if sig_count <= 3:
                print(f"  Signal {sig_count}: {sig['action']} {sig['opt']} @ strike={sig['strike']} ({sig['reason']})")

    print(f"  Total signals (conf > 0.60): {sig_count}")