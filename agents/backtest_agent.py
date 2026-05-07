"""
BacktestAgent — Runs live-simulation backtests for all strategies.
Executes strategy logic against tick-by-tick data feed with full order simulation.
"""
import os
import sys
import json
import logging
import math
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).parent.parent
STRATEGIES_DIR = BASE_DIR / "strategies" / "research"
RESULTS_DIR = BASE_DIR / "backtests" / "results"
SIM_ENGINE_DIR = BASE_DIR / "backtests" / "simulation_engine"

sys.path.insert(0, str(SIM_ENGINE_DIR))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent.parent / 'logs' / 'backtest_agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class BlackScholes:
    """Black-Scholes options pricing."""
    @staticmethod
    def norm_cdf(x: float) -> float:
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    @staticmethod
    def d1(S: float, K: float, T: float, r: float, sigma: float) -> float:
        if T <= 0 or sigma <= 0:
            return 0
        return (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))

    @staticmethod
    def d2(S: float, K: float, T: float, r: float, sigma: float) -> float:
        return BlackScholes.d1(S, K, T, r, sigma) - sigma * math.sqrt(T)

    @staticmethod
    def call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        if T <= 0:
            return max(0, S - K)
        d1 = BlackScholes.d1(S, K, T, r, sigma)
        d2 = BlackScholes.d2(S, K, T, r, sigma)
        return S * BlackScholes.norm_cdf(d1) - K * math.exp(-r * T) * BlackScholes.norm_cdf(d2)

    @staticmethod
    def put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        if T <= 0:
            return max(0, K - S)
        d1 = BlackScholes.d1(S, K, T, r, sigma)
        d2 = BlackScholes.d2(S, K, T, r, sigma)
        return K * math.exp(-r * T) * BlackScholes.norm_cdf(-d2) - S * BlackScholes.norm_cdf(-d1)


class TechnicalIndicators:
    """Compute technical indicators from OHLCV data."""
    @staticmethod
    def sma(closes: pd.Series, period: int) -> float:
        if len(closes) < period:
            return closes.mean() if len(closes) > 0 else 0
        return closes.iloc[-period:].mean()

    @staticmethod
    def rsi(closes: pd.Series, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        deltas = closes.diff()
        gains = deltas.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
        losses = (-deltas.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
        rs = gains / losses.replace(0, 0.0001)
        return 100 - (100 / (1 + rs)).iloc[-1]

    @staticmethod
    def bollinger_bands(closes: pd.Series, period: int = 20):
        if len(closes) < period:
            mean = closes.mean() if len(closes) > 0 else 0
            return mean, mean, mean
        sma = closes.iloc[-period:].mean()
        std = closes.iloc[-period:].std()
        return sma, sma + (2 * std), sma - (2 * std)

    @staticmethod
    def bollinger_width(closes: pd.Series, period: int = 20) -> float:
        if len(closes) < period:
            return 0
        sma, upper, lower = TechnicalIndicators.bollinger_bands(closes, period)
        return (upper - lower) / sma if sma > 0 else 0

    @staticmethod
    def atr(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int = 14) -> float:
        if len(closes) < period + 1:
            return (highs - lows).mean() if len(highs) > 1 else 0
        tr1 = highs - lows
        tr2 = (highs - closes.shift(1)).abs()
        tr3 = (lows - closes.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.iloc[-period:].mean()

    @staticmethod
    def vwap(highs: pd.Series, lows: pd.Series, closes: pd.Series, volumes: pd.Series) -> float:
        if len(closes) < 2 or volumes.sum() == 0:
            return closes.iloc[-1] if len(closes) > 0 else 0
        typical = (highs + lows + closes) / 3
        return (typical * volumes).sum() / volumes.sum()


class SignalGenerator:
    """Generates real trading signals from OHLCV data using technical analysis."""

    def __init__(self):
        self.price_history: List[Dict] = []
        self.max_history = 500
        self.option_iv = 22.0
        self.risk_free_rate = 0.07

    def reset(self):
        self.price_history = []

    def add_tick(self, tick: Dict):
        self.price_history.append(tick)
        if len(self.price_history) > self.max_history:
            self.price_history.pop(0)

    def _closes(self) -> pd.Series:
        return pd.Series([t['close'] for t in self.price_history])

    def _highs(self) -> pd.Series:
        return pd.Series([t['high'] for t in self.price_history])

    def _lows(self) -> pd.Series:
        return pd.Series([t['low'] for t in self.price_history])

    def _vols(self) -> pd.Series:
        return pd.Series([t.get('volume', 0) for t in self.price_history])

    def get_atm_strike(self, spot: float, step: float = 100) -> int:
        return int(round(spot / step) * step)

    def option_price(self, spot: float, strike: int, expiry_days: float, opt_type: str, iv: float = None) -> float:
        iv = iv or self.option_iv
        T = expiry_days / 365.0
        if opt_type == 'CE':
            return BlackScholes.call_price(spot, strike, T, self.risk_free_rate, iv / 100)
        else:
            return BlackScholes.put_price(spot, strike, T, self.risk_free_rate, iv / 100)

    def generate(self, strategy_id: str, approach_id: str) -> Optional[Dict]:
        """Generate signal based on strategy and approach using real data."""
        if len(self.price_history) < 20:
            return None

        closes = self._closes()
        highs = self._highs()
        lows = self._lows()
        vols = self._vols()

        price = closes.iloc[-1]
        prev_close = closes.iloc[-2] if len(closes) > 1 else price
        open_p = self.price_history[-1].get('open', price)

        rsi14 = TechnicalIndicators.rsi(closes, 14)
        rsi9 = TechnicalIndicators.rsi(closes, 9)
        sma20 = TechnicalIndicators.sma(closes, 20)
        sma50 = TechnicalIndicators.sma(closes, 50)
        bb_sma, bb_upper, bb_lower = TechnicalIndicators.bollinger_bands(closes, 20)
        bb_width = TechnicalIndicators.bollinger_width(closes, 20)
        atr_val = TechnicalIndicators.atr(highs, lows, closes, 14)
        vwap_val = TechnicalIndicators.vwap(highs, lows, closes, vols)

        regime = 'unknown'
        if len(closes) >= 30:
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

        # === STRATEGY 001: Iron Condor / Iron Fly ===
        if strategy_id == 'strategy_001':
            if approach_id == 'approach_A':
                # ATM Iron Fly on Wednesdays near expiry
                if len(self.price_history) > 0:
                    try:
                        dt = pd.to_datetime(self.price_history[-1]['timestamp'])
                        is_wed = dt.weekday() == 2
                    except:
                        is_wed = False
                else:
                    is_wed = False

                if is_wed and len(self.price_history) >= 50:
                    atm = self.get_atm_strike(price, 200)
                    ce_p = self.option_price(price, atm, 0.5, 'CE')
                    pe_p = self.option_price(price, atm, 0.5, 'PE')
                    if ce_p + pe_p > 80:
                        return {
                            "action": "SELL", "strike": atm, "opt": "STRADDLE",
                            "lots": 1, "reason": f"IronFly: ATM={atm}, prem={ce_p+pe_p:.0f}",
                            "conf": 0.7, "ce_strike": atm, "pe_strike": atm
                        }

            elif approach_id == 'approach_B':
                # Dynamic wing based on IV
                iv_rank = self.option_iv / 25.0 * 50
                atm = self.get_atm_strike(price, 200)
                if iv_rank > 70:
                    ww = 400
                elif iv_rank > 40:
                    ww = 200
                else:
                    ww = 100
                # Only return if IV rank is high enough to make IC worthwhile
                if iv_rank > 40:
                    return {
                        "action": "SELL", "strike": atm, "opt": "IC",
                        "lots": 1, "reason": f"DynamicIC: IV={iv_rank:.0f}, w={ww}",
                        "conf": 0.65, "ce_strike": atm + ww, "pe_strike": atm - ww
                    }
                # Fall through to approach_C if IV rank is low

            elif approach_id == 'approach_C':
                # Mean reversion on BB
                if rsi14 < 35 and price < bb_lower and len(self.price_history) > 30:
                    atm = self.get_atm_strike(price, 200)
                    pe_p = self.option_price(price, atm, 1.0, 'PE')
                    if pe_p > 100:
                        return {"action": "SELL", "strike": atm, "opt": "PE", "lots": 1,
                                "reason": f"Oversold: RSI={rsi14:.1f}", "conf": 0.7}
                elif rsi14 > 65 and price > bb_upper and len(self.price_history) > 30:
                    atm = self.get_atm_strike(price, 200)
                    ce_p = self.option_price(price, atm, 1.0, 'CE')
                    if ce_p > 100:
                        return {"action": "SELL", "strike": atm, "opt": "CE", "lots": 1,
                                "reason": f"Overbought: RSI={rsi14:.1f}", "conf": 0.7}

        # === STRATEGY 002: Momentum-Based ===
        elif strategy_id == 'strategy_002':
            if approach_id == 'approach_A':
                gap_pct = ((open_p - prev_close) / prev_close) if prev_close > 0 else 0
                if gap_pct > 0.0075 and len(self.price_history) > 20:
                    atm = self.get_atm_strike(price, 100)
                    return {"action": "BUY", "strike": atm, "opt": "CE", "lots": 1,
                            "reason": f"Gap up: {gap_pct*100:.2f}%", "conf": 0.75}
                elif gap_pct < -0.0075 and len(self.price_history) > 20:
                    atm = self.get_atm_strike(price, 100)
                    return {"action": "BUY", "strike": atm, "opt": "PE", "lots": 1,
                            "reason": f"Gap down: {gap_pct*100:.2f}%", "conf": 0.75}

            elif approach_id == 'approach_B':
                # VWAP breakout with RSI filter
                if rsi14 > 55 and price > vwap_val and price > sma20:
                    atm = self.get_atm_strike(price, 100)
                    return {"action": "BUY", "strike": atm, "opt": "CE", "lots": 1,
                            "reason": f"VWAP up: price={price:.0f}, VWAP={vwap_val:.0f}, RSI={rsi14:.1f}", "conf": 0.7}
                elif rsi14 < 45 and price < vwap_val and price < sma20:
                    atm = self.get_atm_strike(price, 100)
                    return {"action": "BUY", "strike": atm, "opt": "PE", "lots": 1,
                            "reason": f"VWAP dn: price={price:.0f}, VWAP={vwap_val:.0f}, RSI={rsi14:.1f}", "conf": 0.7}

            elif approach_id == 'approach_C':
                # Opening Range Breakout
                if len(self.price_history) > 15:
                    rng_hi = highs.iloc[-15:].max()
                    rng_lo = lows.iloc[-15:].max()
                    if price > rng_hi * 1.003:
                        atm = self.get_atm_strike(price, 100)
                        return {"action": "BUY", "strike": atm, "opt": "CE", "lots": 1,
                                "reason": f"ORB up: hi={rng_hi:.0f}", "conf": 0.7}
                    elif price < rng_lo * 0.997:
                        atm = self.get_atm_strike(price, 100)
                        return {"action": "BUY", "strike": atm, "opt": "PE", "lots": 1,
                                "reason": f"ORB dn: lo={rng_lo:.0f}", "conf": 0.7}

        # === STRATEGY 003: Mean Reversion ===
        elif strategy_id == 'strategy_003':
            if approach_id == 'approach_A':
                # BB squeeze -> expansion
                if bb_width < 0.02 and len(self.price_history) > 30:
                    atm = self.get_atm_strike(price, 200)
                    return {"action": "BUY", "strike": atm, "opt": "STRADDLE", "lots": 1,
                            "reason": f"BB squeeze: w={bb_width:.3f}", "conf": 0.7,
                            "ce_strike": atm, "pe_strike": atm}
                elif price < bb_lower and len(self.price_history) > 20:
                    atm = self.get_atm_strike(price, 200)
                    return {"action": "BUY", "strike": atm, "opt": "CE", "lots": 1,
                            "reason": f"Below BB: {price:.0f}<{bb_lower:.0f}", "conf": 0.65}
                elif price > bb_upper and len(self.price_history) > 20:
                    atm = self.get_atm_strike(price, 200)
                    return {"action": "BUY", "strike": atm, "opt": "PE", "lots": 1,
                            "reason": f"Above BB: {price:.0f}>{bb_upper:.0f}", "conf": 0.65}

            elif approach_id == 'approach_B':
                # IV rank premium selling
                if self.option_iv > 25 and rsi14 > 60:
                    atm = self.get_atm_strike(price, 200)
                    ce_p = self.option_price(price, atm + 300, 1.0, 'CE')
                    if ce_p > 80:
                        return {"action": "SELL", "strike": atm + 300, "opt": "CE", "lots": 1,
                                "reason": f"HighIV: IV={self.option_iv:.0f}, RSI={rsi14:.1f}", "conf": 0.7}
                elif self.option_iv > 25 and rsi14 < 40:
                    atm = self.get_atm_strike(price, 200)
                    pe_p = self.option_price(price, atm - 300, 1.0, 'PE')
                    if pe_p > 80:
                        return {"action": "SELL", "strike": atm - 300, "opt": "PE", "lots": 1,
                                "reason": f"HighIV: IV={self.option_iv:.0f}, RSI={rsi14:.1f}", "conf": 0.7}

            elif approach_id == 'approach_C':
                # Delta-neutral
                atm = self.get_atm_strike(price, 200)
                T = 1.0 / 365.0
                d1 = (math.log(price / atm) + (self.risk_free_rate + 0.5 * (self.option_iv/100)**2) * T) / ((self.option_iv/100) * math.sqrt(T))
                delta = BlackScholes.norm_cdf(d1) - 1
                if abs(delta) > 0.25 and len(self.price_history) > 30:
                    if delta > 0.25:
                        return {"action": "BUY", "strike": atm, "opt": "PE", "lots": 1,
                                "reason": f"Delta hedge: d={delta:.2f}", "conf": 0.6}
                    else:
                        return {"action": "BUY", "strike": atm, "opt": "CE", "lots": 1,
                                "reason": f"Delta hedge: d={delta:.2f}", "conf": 0.6}

        # === STRATEGY 004: Event-Based ===
        elif strategy_id == 'strategy_004':
            if approach_id == 'approach_A':
                # Expiry day theta
                if len(self.price_history) > 0:
                    try:
                        dt = pd.to_datetime(self.price_history[-1]['timestamp'])
                        is_wed = dt.weekday() == 2
                    except:
                        is_wed = False
                else:
                    is_wed = False
                if is_wed and len(self.price_history) > 20:
                    atm = self.get_atm_strike(price, 200)
                    otm_ce = atm + int(price * 0.015 / 100) * 100 + 200
                    otm_pe = atm - int(price * 0.015 / 100) * 100 - 200
                    ce_p = self.option_price(price, otm_ce, 0.1, 'CE')
                    pe_p = self.option_price(price, otm_pe, 0.1, 'PE')
                    if ce_p + pe_p > 60:
                        return {"action": "SELL", "strike": atm, "opt": "STRANGLE", "lots": 1,
                                "reason": f"Expiry: CE={otm_ce}, PE={otm_pe}", "conf": 0.75,
                                "ce_strike": otm_ce, "pe_strike": otm_pe}

            elif approach_id == 'approach_B':
                # Pre-event high IV
                if self.option_iv > 28 and (rsi14 > 70 or rsi14 < 30):
                    atm = self.get_atm_strike(price, 200)
                    if rsi14 > 70:
                        return {"action": "SELL", "strike": atm + 300, "opt": "CE", "lots": 1,
                                "reason": f"Pre-event IV: {self.option_iv:.0f}", "conf": 0.7}
                    else:
                        return {"action": "SELL", "strike": atm - 300, "opt": "PE", "lots": 1,
                                "reason": f"Pre-event IV: {self.option_iv:.0f}", "conf": 0.7}

            elif approach_id == 'approach_C':
                # Rollover reversal
                if len(self.price_history) > 0:
                    try:
                        dt = pd.to_datetime(self.price_history[-1]['timestamp'])
                        is_thu = dt.weekday() == 3
                        is_fri = dt.weekday() == 4
                    except:
                        is_thu = is_fri = False
                else:
                    is_thu = is_fri = False
                if (is_thu or is_fri) and len(self.price_history) > 30:
                    if rsi14 < 35 and price < sma50:
                        atm = self.get_atm_strike(price, 100)
                        return {"action": "BUY", "strike": atm, "opt": "CE", "lots": 1,
                                "reason": f"Rollover: RSI={rsi14:.1f}", "conf": 0.65}
                    elif rsi14 > 65 and price > sma50:
                        atm = self.get_atm_strike(price, 100)
                        return {"action": "BUY", "strike": atm, "opt": "PE", "lots": 1,
                                "reason": f"Rollover: RSI={rsi14:.1f}", "conf": 0.65}

        # === STRATEGY 005: Greeks-Based ===
        elif strategy_id == 'strategy_005':
            if approach_id == 'approach_A':
                # Gamma scalping near ATM
                atm = self.get_atm_strike(price, 100)
                T = 0.5 / 365.0
                d1 = (math.log(price / atm) + (self.risk_free_rate + 0.5 * (self.option_iv/100)**2) * T) / ((self.option_iv/100) * math.sqrt(T))
                delta_val = BlackScholes.norm_cdf(d1)
                if abs(delta_val - 0.5) < 0.15 and rsi14 > 50 and len(self.price_history) > 20:
                    return {"action": "BUY", "strike": atm, "opt": "STRADDLE", "lots": 1,
                            "reason": f"Gamma scalp: d={delta_val:.2f}", "conf": 0.7,
                            "ce_strike": atm, "pe_strike": atm}

            elif approach_id == 'approach_B':
                # Vega-neutral spread
                if self.option_iv > 22 and regime == 'high_vol':
                    atm = self.get_atm_strike(price, 200)
                    return {"action": "BUY", "strike": atm, "opt": "STRADDLE", "lots": 1,
                            "reason": f"Vega-neutral: IV={self.option_iv:.0f}, {regime}", "conf": 0.65,
                            "ce_strike": atm, "pe_strike": atm}

            elif approach_id == 'approach_C':
                # Delta rebalancing
                atm = self.get_atm_strike(price, 200)
                T = 1.0 / 365.0
                d1 = (math.log(price / atm) + (self.risk_free_rate + 0.5 * (self.option_iv/100)**2) * T) / ((self.option_iv/100) * math.sqrt(T))
                delta_val = BlackScholes.norm_cdf(d1) - 1
                if abs(delta_val) > 0.15:
                    if delta_val > 0.15:
                        return {"action": "SELL", "strike": atm, "opt": "PE", "lots": 1,
                                "reason": f"Delta rebal: d={delta_val:.2f}", "conf": 0.6}
                    else:
                        return {"action": "SELL", "strike": atm, "opt": "CE", "lots": 1,
                                "reason": f"Delta rebal: d={delta_val:.2f}", "conf": 0.6}

        # === STRATEGY 006: ML-Assisted / Regime ===
        elif strategy_id == 'strategy_006':
            if approach_id == 'approach_A':
                # ML trend signal
                if regime == 'trending_up' and rsi14 > 55 and price > bb_upper:
                    atm = self.get_atm_strike(price, 100)
                    return {"action": "BUY", "strike": atm, "opt": "CE", "lots": 1,
                            "reason": f"ML trend: {regime}, RSI={rsi14:.1f}", "conf": 0.75}
                elif regime == 'trending_down' and rsi14 < 45 and price < bb_lower:
                    atm = self.get_atm_strike(price, 100)
                    return {"action": "BUY", "strike": atm, "opt": "PE", "lots": 1,
                            "reason": f"ML trend: {regime}, RSI={rsi14:.1f}", "conf": 0.75}

            elif approach_id == 'approach_B':
                # LSTM momentum
                if rsi9 > 60 and rsi14 > 55 and sma20 > sma50:
                    atm = self.get_atm_strike(price, 100)
                    return {"action": "BUY", "strike": atm, "opt": "CE", "lots": 1,
                            "reason": f"LSTM: RSI9={rsi9:.1f}, RSI14={rsi14:.1f}", "conf": 0.7}
                elif rsi9 < 40 and rsi14 < 45 and sma20 < sma50:
                    atm = self.get_atm_strike(price, 100)
                    return {"action": "BUY", "strike": atm, "opt": "PE", "lots": 1,
                            "reason": f"LSTM: RSI9={rsi9:.1f}, RSI14={rsi14:.1f}", "conf": 0.7}

            elif approach_id == 'approach_C':
                # Regime clustering
                if regime == 'range_bound' and bb_width < 0.03:
                    atm = self.get_atm_strike(price, 200)
                    return {"action": "BUY", "strike": atm, "opt": "STRADDLE", "lots": 1,
                            "reason": f"Regime: {regime}, squeeze", "conf": 0.7,
                            "ce_strike": atm, "pe_strike": atm}
                elif regime == 'high_vol':
                    atm = self.get_atm_strike(price, 200)
                    return {"action": "SELL", "strike": atm, "opt": "STRANGLE", "lots": 1,
                            "reason": f"High vol regime: {regime}", "conf": 0.7,
                            "ce_strike": atm + 300, "pe_strike": atm - 300}

            elif approach_id == 'approach_D':
                # IV-adaptive regime: sell premium in low IV, buy directional in high IV
                if len(self.price_history) < 30:
                    return None

                # Approximate IV from straddle width ratio
                atm = self.get_atm_strike(price, 200)
                T = 0.5 / 365.0
                straddle_22 = BlackScholes.call_price(price, atm, T, self.risk_free_rate, 0.22) + \
                              BlackScholes.put_price(price, atm, T, self.risk_free_rate, 0.22)
                straddle_15 = BlackScholes.call_price(price, atm, T, self.risk_free_rate, 0.15) + \
                              BlackScholes.put_price(price, atm, T, self.risk_free_rate, 0.15)

                iv_ratio = straddle_22 / straddle_15 if straddle_15 > 0 else 1.0

                if regime == 'low_vol' and iv_ratio < 1.3:
                    # Low IV regime - sell ATM straddle
                    ce_p = self.option_price(price, atm, 0.5, 'CE')
                    pe_p = self.option_price(price, atm, 0.5, 'PE')
                    if ce_p + pe_p > 80:
                        return {
                            "action": "SELL", "strike": atm, "opt": "STRADDLE", "lots": 1,
                            "reason": f"LowIV: ratio={iv_ratio:.2f}", "conf": 0.70,
                            "ce_strike": atm, "pe_strike": atm
                        }
                elif regime == 'high_vol' and rsi14 > 60:
                    # High vol + overbought - sell CE OTM
                    atm2 = self.get_atm_strike(price, 200)
                    ce_p = self.option_price(price, atm2 + 200, 0.5, 'CE')
                    if ce_p > 60:
                        return {
                            "action": "SELL", "strike": atm2 + 200, "opt": "CE", "lots": 1,
                            "reason": f"HighVol: RSI={rsi14:.1f}", "conf": 0.65,
                            "ce_strike": atm2 + 200, "pe_strike": atm2 - 200
                        }
                elif regime == 'trending_up' and rsi14 > 55:
                    # Trending up - buy CE directional
                    atm2 = self.get_atm_strike(price, 100)
                    ce_p = self.option_price(price, atm2, 0.5, 'CE')
                    if ce_p > 50:
                        return {
                            "action": "BUY", "strike": atm2, "opt": "CE", "lots": 1,
                            "reason": f"TrendingUp: RSI={rsi14:.1f}", "conf": 0.65,
                            "ce_strike": atm2, "pe_strike": atm2
                        }
                elif regime == 'trending_down' and rsi14 < 45:
                    # Trending down - buy PE directional
                    atm2 = self.get_atm_strike(price, 100)
                    pe_p = self.option_price(price, atm2, 0.5, 'PE')
                    if pe_p > 50:
                        return {
                            "action": "BUY", "strike": atm2, "opt": "PE", "lots": 1,
                            "reason": f"TrendingDn: RSI={rsi14:.1f}", "conf": 0.65,
                            "ce_strike": atm2, "pe_strike": atm2
                        }

        # === STRATEGY 001: approach_D: SELL OTM strangle (safer premium) ===
        if strategy_id == 'strategy_001':
            if approach_id == 'approach_D':
                if len(self.price_history) < 20:
                    return None

                atm = self.get_atm_strike(price, 200)
                wing = 300  # OTM by 300 points (~0.5% OTM)

                ce_strike = atm + wing
                pe_strike = atm - wing
                T = 0.5 / 365.0
                iv = self.option_iv / 100

                ce_p = BlackScholes.call_price(price, ce_strike, T, self.risk_free_rate, iv)
                pe_p = BlackScholes.put_price(price, pe_strike, T, self.risk_free_rate, iv)
                total_premium = ce_p + pe_p

                if total_premium > 25:  # Minimum premium (lowered from 40)
                    return {
                        "action": "SELL", "strike": atm, "opt": "STRANGLE", "lots": 1,
                        "reason": f"OTM strangle: CE={ce_strike}, PE={pe_strike}, prem={total_premium:.0f}",
                        "conf": 0.60, "ce_strike": ce_strike, "pe_strike": pe_strike
                    }

        # === STRATEGY 002: approach_D: VWAP mean reversion (more signals) ===
        elif strategy_id == 'strategy_002':
            if approach_id == 'approach_D':
                if len(self.price_history) < 15:
                    return None

                # Sell: price above VWAP with overbought RSI
                if price > vwap_val and rsi14 > 58:
                    atm = self.get_atm_strike(price, 100)
                    pe_p = self.option_price(price, atm, 0.5, 'PE')
                    if pe_p > 30:
                        return {
                            "action": "SELL", "strike": atm, "opt": "PE", "lots": 1,
                            "reason": f"VWAP over: price={price:.0f}, VWAP={vwap_val:.0f}, RSI={rsi14:.1f}",
                            "conf": 0.60, "ce_strike": atm, "pe_strike": atm
                        }
                # Buy: price below VWAP with oversold RSI
                elif price < vwap_val and rsi14 < 42:
                    atm = self.get_atm_strike(price, 100)
                    ce_p = self.option_price(price, atm, 0.5, 'CE')
                    if ce_p > 30:
                        return {
                            "action": "BUY", "strike": atm, "opt": "CE", "lots": 1,
                            "reason": f"VWAP under: price={price:.0f}, VWAP={vwap_val:.0f}, RSI={rsi14:.1f}",
                            "conf": 0.60, "ce_strike": atm, "pe_strike": atm
                        }

        # === STRATEGY 003: approach_D: BUY single-leg on BB squeeze breakout ===
        elif strategy_id == 'strategy_003':
            if approach_id == 'approach_D':
                if bb_width < 0.05 and len(self.price_history) > 30:
                    atm = self.get_atm_strike(price, 200)

                    if rsi14 < 40:
                        ce_p = self.option_price(price, atm, 0.5, 'CE')
                        if ce_p > 30:
                            return {
                                "action": "BUY", "strike": atm, "opt": "CE", "lots": 1,
                                "reason": f"BB squeeze + oversold: w={bb_width:.3f}, RSI={rsi14:.1f}",
                                "conf": 0.70, "ce_strike": atm, "pe_strike": atm
                            }
                    elif rsi14 > 60:
                        pe_p = self.option_price(price, atm, 0.5, 'PE')
                        if pe_p > 30:
                            return {
                                "action": "BUY", "strike": atm, "opt": "PE", "lots": 1,
                                "reason": f"BB squeeze + overbought: w={bb_width:.3f}, RSI={rsi14:.1f}",
                                "conf": 0.70, "ce_strike": atm, "pe_strike": atm
                            }
                    else:
                        # Neutral RSI — still squeeze, bias toward CE (market tends up)
                        ce_p = self.option_price(price, atm, 0.5, 'CE')
                        if ce_p > 30:
                            return {
                                "action": "BUY", "strike": atm, "opt": "CE", "lots": 1,
                                "reason": f"BB squeeze: w={bb_width:.3f}", "conf": 0.65,
                                "ce_strike": atm, "pe_strike": atm
                            }

        # === STRATEGY 004: approach_D: Intraday momentum breakout ===
        elif strategy_id == 'strategy_004':
            if approach_id == 'approach_D':
                if len(self.price_history) < 20:
                    return None

                # Buy CE: price above SMA20 with strong RSI momentum
                if price > sma20 and rsi14 > 62:
                    atm = self.get_atm_strike(price, 100)
                    ce_p = self.option_price(price, atm, 0.5, 'CE')
                    if ce_p > 30:
                        return {
                            "action": "BUY", "strike": atm, "opt": "CE", "lots": 1,
                            "reason": f"Intraday long: RSI14={rsi14:.1f}, price>{sma20:.0f}",
                            "conf": 0.60, "ce_strike": atm, "pe_strike": atm
                        }
                # Buy PE: price below SMA20 with weak RSI
                elif price < sma20 and rsi14 < 38:
                    atm = self.get_atm_strike(price, 100)
                    pe_p = self.option_price(price, atm, 0.5, 'PE')
                    if pe_p > 30:
                        return {
                            "action": "BUY", "strike": atm, "opt": "PE", "lots": 1,
                            "reason": f"Intraday short: RSI14={rsi14:.1f}, price<{sma20:.0f}",
                            "conf": 0.60, "ce_strike": atm, "pe_strike": atm
                        }

        return None


class BacktestAgent:
    """Runs simulation-based backtests for all strategy approaches."""

    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator
        self.data_feeder = None
        self.order_simulator = None
        self.portfolio_tracker = None
        self.results = {}
        self._init_components()
        logger.info("BacktestAgent initialized")

    def _init_components(self):
        """Initialize simulation engine components."""
        try:
            from data_feeder import DataFeeder
            from order_simulator import OrderSimulator
            from portfolio_tracker import PortfolioTracker

            # Data is in parent/options/data/, not in banknifty_algo/data/
            data_base = BASE_DIR.parent / "data"
            # Prefer hourly feed (3 years of data May 2023 - May 2026)
            feed_path = data_base / "feeds" / "simulation_feed_hourly.json"
            if not feed_path.exists():
                feed_path = data_base / "feeds" / "simulation_feed.json"
            if not feed_path.exists():
                feed_path = data_base / "feeds" / "simulation_feed_daily.json"
            if not feed_path.exists():
                raise FileNotFoundError(f"No feed file found in {data_base / 'feeds'}")

            self.data_feeder = DataFeeder(feed_path)
            self.order_simulator = OrderSimulator()
            self.portfolio_tracker = PortfolioTracker(initial_capital=100000)
            self.signal_generator = SignalGenerator()
            logger.info(f"Simulation engine initialized with {len(self.data_feeder.data)} ticks from {feed_path.name}")
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")

    def _run_exit_logic(self, position: Dict, tick: Dict, entry_price: float) -> Tuple[bool, float]:
        """Check if position should exit. Returns (should_exit, exit_price)."""
        underlying_price = tick.get('close', tick.get('ltp', entry_price))
        opt = position.get('opt', 'CE')
        strike = position.get('strike', self.signal_generator.get_atm_strike(underlying_price) if self.signal_generator else int(underlying_price / 100) * 100)
        action = position['action']
        entry_tick = position.get('entry_tick', 0)
        current_tick = tick.get('tick_num', 0)
        initial_expiry_days = position.get('expiry_days', 0.5)
        entry_opt_price = position.get('entry_opt_price', entry_price)

        ticks_elapsed = current_tick - entry_tick
        days_elapsed = ticks_elapsed * 5.0 / (60.0 * 24.0)
        remaining_expiry = max(0.01, initial_expiry_days - days_elapsed)

        iv = self.signal_generator.option_iv if self.signal_generator else 22.0
        current_opt_price = self.signal_generator.option_price(underlying_price, strike, remaining_expiry, opt, iv) if self.signal_generator else entry_price

        if action == 'SELL':
            if current_opt_price < entry_opt_price * 0.30:
                return True, current_opt_price
            if current_opt_price < entry_opt_price * 0.50 and ticks_elapsed > 20:
                return True, current_opt_price
            if ticks_elapsed > 40:
                return True, current_opt_price
            if entry_opt_price > 0 and current_opt_price > entry_opt_price * 2.0:
                return True, current_opt_price
            return False, current_opt_price

        elif action == 'BUY':
            entry_premium = entry_opt_price
            if entry_premium > 0:
                pnl_pct = (current_opt_price - entry_premium) / entry_premium
            else:
                pnl_pct = 0

            if pnl_pct >= 0.50:
                return True, current_opt_price
            if pnl_pct <= -0.30:
                return True, current_opt_price
            if ticks_elapsed > 60 and pnl_pct < 0.10:
                return True, current_opt_price
            return False, current_opt_price

        return False, current_opt_price

    def _simulate_strategy(self, strategy_id: str, approach_id: str,
                           start_date: datetime, end_date: datetime) -> Dict:
        """Run one strategy approach through real data simulation."""
        logger.info(f"Running backtest: {strategy_id}/{approach_id}")

        if self.data_feeder is None:
            self._init_components()
        if self.data_feeder is None or self.signal_generator is None:
            logger.error("Could not initialize components")
            return {"strategy_id": strategy_id, "approach_id": approach_id, "trades": 0, "statistics": {}}

        self.data_feeder.reset()
        self.order_simulator.reset()
        self.portfolio_tracker.reset()
        self.signal_generator.reset()

        results = {
            "strategy_id": strategy_id,
            "approach_id": approach_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "trades": [],
            "equity_curve": [],
            "monthly_pnl": {},
            "statistics": {}
        }

        open_positions: List[Dict] = []
        tick_count = 0

        # Use all data (not just 500)
        all_data = self.data_feeder.data
        if not all_data:
            logger.warning(f"No data available for {strategy_id}/{approach_id}")
            return results

        logger.info(f"Processing {len(all_data)} ticks of real data")

        for tick in all_data:
            tick_count += 1
            close_price = tick.get('close', tick.get('ltp', 45000))
            instrument = tick.get('instrument', 'BANKNIFTY')

            # Update signal generator with this tick
            self.signal_generator.add_tick(tick)

            # Update portfolio
            self.data_feeder.current_index = tick_count
            self.portfolio_tracker.update_market_price(instrument, close_price)

            # Add tick_num to tick for exit logic
            tick['tick_num'] = tick_count

            # Try to generate signal (only if no open positions or on new signals periodically)
            signal = None
            if len(open_positions) < 3:
                signal = self.signal_generator.generate(strategy_id, approach_id)

            if signal and signal.get('conf', 0) >= 0.60:
                action = signal['action']
                opt = signal.get('opt', 'CE')
                strike = signal['strike']
                lots = signal.get('lots', 1)
                reason = signal.get('reason', '')
                expiry_days = 0.5 if 'STRADDLE' in opt or 'STRANGLE' in opt else 1.0

                if opt == 'STRADDLE' or opt == 'STRANGLE':
                    ce_s = signal.get('ce_strike', strike)
                    pe_s = signal.get('pe_strike', strike)
                    ce_p = self.signal_generator.option_price(close_price, ce_s, expiry_days, 'CE')
                    pe_p = self.signal_generator.option_price(close_price, pe_s, expiry_days, 'PE')
                    total_premium = ce_p + pe_p
                else:
                    total_premium = self.signal_generator.option_price(close_price, strike, expiry_days, opt)

                if total_premium > 20:  # Minimum premium threshold
                    tick_ts = tick.get('timestamp')
                    order = self.order_simulator.place_market_order(
                        f"{instrument}_{strike}_{opt}", action, lots, total_premium, opt, strike,
                        tick_timestamp=tick_ts
                    )
                    pos = {
                        "order": order,
                        "action": action,
                        "strike": strike,
                        "opt": opt,
                        "entry_price": order['fill_price'],
                        "entry_opt_price": total_premium,
                        "entry_tick": tick_count,
                        "reason": reason,
                        "lots": lots,
                        "ce_strike": signal.get('ce_strike'),
                        "pe_strike": signal.get('pe_strike'),
                        "expiry_days": expiry_days,
                        "_orig_order": dict(order)  # preserve original order data
                    }
                    open_positions.append(pos)
                    self.portfolio_tracker.open_position(order)

            # Check exits for open positions
            positions_to_close = []
            for i, pos in enumerate(open_positions):
                should_exit, exit_price = self._run_exit_logic(pos, tick, pos['entry_price'])
                if should_exit:
                    orig_order = pos.get('_orig_order', pos['order'])
                    exit_tick_ts = tick.get('timestamp')
                    exit_order = self.order_simulator.place_market_order(
                        f"{instrument}_{pos['strike']}_{pos['opt']}",
                        "SELL" if pos['action'] == "BUY" else "BUY",
                        pos['lots'], exit_price, pos['opt'], pos['strike'],
                        tick_timestamp=exit_tick_ts
                    )
                    self.portfolio_tracker.close_position(orig_order, exit_order['fill_price'], exit_order['charges'], exit_timestamp=exit_tick_ts)
                    positions_to_close.append(i)

            for i in reversed(positions_to_close):
                open_positions.pop(i)

            # Record equity curve every 50 ticks
            if tick_count % 50 == 0:
                self.portfolio_tracker.record_equity_snapshot(tick.get('timestamp'))
                stats = self.portfolio_tracker.get_statistics()
                results["equity_curve"].append({
                    "tick": tick_count,
                    "equity": self.portfolio_tracker.get_equity(),
                    "drawdown": self.portfolio_tracker.get_current_drawdown()
                })

        # Close any remaining positions at last price
        last_price = all_data[-1].get('close', 45000) if all_data else 45000
        last_tick_ts = all_data[-1].get('timestamp') if all_data else None
        for pos in open_positions:
            # Compute realistic exit price via Black-Scholes
            iv = self.signal_generator.option_iv if self.signal_generator else 22.0
            expiry_d = pos.get('expiry_days', 0.5)
            exit_opt_price = self.signal_generator.option_price(last_price, pos['strike'], expiry_d, pos['opt'], iv) if self.signal_generator else pos['entry_price'] * 0.5
            exit_order = self.order_simulator.place_market_order(
                f"{instrument}_{pos['strike']}_{pos['opt']}",
                "SELL" if pos['action'] == "BUY" else "BUY",
                pos['lots'], exit_opt_price, pos['opt'], pos['strike'],
                tick_timestamp=last_tick_ts
            )
            self.portfolio_tracker.close_position(pos['order'], exit_order['fill_price'], exit_order['charges'], exit_timestamp=last_tick_ts)

        results["trades"] = len(self.portfolio_tracker.closed_trades)
        results["statistics"] = self.portfolio_tracker.get_statistics()
        results["equity_curve"] = results["equity_curve"][:200]
        results["closed_trades"] = self.portfolio_tracker.closed_trades

        logger.info(f"Backtest {strategy_id}/{approach_id}: {results['trades']} trades, "
                    f"Sharpe: {results['statistics'].get('sharpe_ratio', 0):.3f}, "
                    f"P&L: {results['statistics'].get('total_pnl', 0):.0f}")

        return results

    def _save_results(self, strategy_id: str, approach_id: str, results: Dict):
        """Save backtest results to file."""
        result_dir = RESULTS_DIR / f"{strategy_id}_{approach_id}"
        result_dir.mkdir(parents=True, exist_ok=True)

        result_file = result_dir / "backtest_results.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, default=str)

        equity_df = pd.DataFrame(results.get("equity_curve", []))
        if not equity_df.empty:
            equity_df.to_csv(result_dir / "equity_curve.csv", index=False)

        stats = results.get("statistics", {})
        summary = {
            "strategy_id": strategy_id,
            "approach_id": approach_id,
            "total_trades": stats.get("total_trades", 0),
            "win_rate": stats.get("win_rate", 0),
            "sharpe_ratio": stats.get("sharpe_ratio", 0),
            "max_drawdown_pct": stats.get("max_drawdown_pct", 0),
            "profit_factor": stats.get("profit_factor", 0),
            "avg_trade": stats.get("avg_trade", 0),
            "total_pnl": stats.get("total_pnl", 0)
        }
        with open(result_dir / "summary.json", 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Results saved to {result_dir}")

    def run_backtest_for_strategy(self, strategy_id: str, approach_id: str) -> Dict:
        """Run backtest for a specific strategy+approach."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)

        results = self._simulate_strategy(strategy_id, approach_id, start_date, end_date)
        self._save_results(strategy_id, approach_id, results)
        return results

    def run_all_backtests(self):
        """Run backtests for all strategies and approaches."""
        logger.info("Starting backtest run for all strategies with REAL data...")

        strategies = [
            ("strategy_001", "approach_A"), ("strategy_001", "approach_B"), ("strategy_001", "approach_C"), ("strategy_001", "approach_D"),
            ("strategy_002", "approach_A"), ("strategy_002", "approach_B"), ("strategy_002", "approach_C"), ("strategy_002", "approach_D"),
            ("strategy_003", "approach_A"), ("strategy_003", "approach_B"), ("strategy_003", "approach_C"), ("strategy_003", "approach_D"),
            ("strategy_004", "approach_A"), ("strategy_004", "approach_B"), ("strategy_004", "approach_C"), ("strategy_004", "approach_D"),
            ("strategy_005", "approach_A"), ("strategy_005", "approach_B"), ("strategy_005", "approach_C"),
            ("strategy_006", "approach_A"), ("strategy_006", "approach_B"), ("strategy_006", "approach_C"), ("strategy_006", "approach_D"),
        ]

        all_results = {}
        for strategy_id, approach_id in strategies:
            results = self.run_backtest_for_strategy(strategy_id, approach_id)
            all_results[f"{strategy_id}_{approach_id}"] = results

        logger.info(f"All backtests complete. Total strategies tested: {len(all_results)}")
        return all_results

    def generate_comparison_report(self):
        """Generate master comparison report across all strategies."""
        report_path = BASE_DIR / "backtests" / "comparison" / "strategy_comparison_report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)

        comparisons = []
        for result_dir in RESULTS_DIR.iterdir():
            if result_dir.is_dir():
                summary_file = result_dir / "summary.json"
                if summary_file.exists():
                    with open(summary_file) as f:
                        comparisons.append(json.load(f))

        comparisons.sort(key=lambda x: x.get("sharpe_ratio", 0), reverse=True)

        report = "# Strategy Comparison Report\n\n"
        report += "| Strategy | Approach | Trades | Win Rate | Sharpe | MaxDD | PF | Avg Trade | P&L |\n"
        report += "|----------|----------|--------|----------|--------|-------|---|-----------|-------|\n"

        for c in comparisons:
            report += f"| {c['strategy_id']} | {c['approach_id']} | {c['total_trades']} | "
            report += f"{c['win_rate']*100:.1f}% | {c['sharpe_ratio']:.3f} | {c['max_drawdown_pct']:.1f}% | "
            report += f"{c['profit_factor']:.2f} | {c['avg_trade']:.2f} | {c['total_pnl']:.0f} |\n"

        report += f"\n**Total strategies tested:** {len(comparisons)}\n"
        if comparisons:
            report += f"**Top performer:** {comparisons[0]['strategy_id']}/{comparisons[0]['approach_id']} (Sharpe: {comparisons[0]['sharpe_ratio']:.3f})\n"

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)

        logger.info(f"Comparison report saved to {report_path}")
        return report


if __name__ == "__main__":
    agent = BacktestAgent()
    results = agent.run_all_backtests()
    print(f"Backtests completed: {len(results)} strategies tested")