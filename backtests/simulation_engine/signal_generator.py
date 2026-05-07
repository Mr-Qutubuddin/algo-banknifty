"""
SignalGenerator — Generates real trading signals from OHLCV data using technical analysis.
Uses actual price patterns, indicators (RSI, Bollinger Bands, VWAP, etc.) and option pricing.
"""
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import math

import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).parent.parent.parent
DB_PATH = BASE_DIR / "data" / "banknifty.db"

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """Compute real technical indicators from OHLCV data."""

    @staticmethod
    def sma(closes: pd.Series, period: int) -> float:
        if len(closes) < period:
            return closes.mean() if len(closes) > 0 else 0
        return closes.iloc[-period:].mean()

    @staticmethod
    def ema(closes: pd.Series, period: int) -> float:
        if len(closes) < period:
            return closes.mean() if len(closes) > 0 else 0
        return closes.ewm(span=period, adjust=False).mean().iloc[-1]

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
    def bollinger_bands(closes: pd.Series, period: int = 20) -> Tuple[float, float, float]:
        if len(closes) < period:
            mean = closes.mean() if len(closes) > 0 else 0
            return mean, mean, mean
        sma = closes.iloc[-period:].mean()
        std = closes.iloc[-period:].std()
        upper = sma + (2 * std)
        lower = sma - (2 * std)
        return sma, upper, lower

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

    @staticmethod
    def vix_from_price(price: float, strike: float, time_to_expiry: float, risk_free: float = 0.07) -> float:
        """Estimate implied vol from price using simplified approach."""
        if strike == 0 or time_to_expiry <= 0 or price <= 0:
            return 20.0
        moneyness = price / strike
        base_iv = 20.0
        if moneyness < 0.9:
            base_iv = 25.0
        elif moneyness > 1.1:
            base_iv = 25.0
        return base_iv

    @staticmethod
    def iv_rank(current_iv: float, historical_ivs: List[float]) -> float:
        if not historical_ivs or len(historical_ivs) < 10:
            return 50.0
        min_iv = min(historical_ivs)
        max_iv = max(historical_ivs)
        range_iv = max_iv - min_iv
        if range_iv < 1:
            return 50.0
        return min(100, max(0, (current_iv - min_iv) / range_iv * 100))


class BlackScholes:
    """Black-Scholes options pricing."""

    @staticmethod
    def norm_cdf(x: float) -> float:
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    @staticmethod
    def norm_pdf(x: float) -> float:
        return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)

    @staticmethod
    def d1(S: float, K: float, T: float, r: float, sigma: float) -> float:
        if T <= 0 or sigma <= 0:
            return 0
        return (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))

    @staticmethod
    def d2(S: float, K: float, T: float, r: float, sigma: float) -> float:
        if T <= 0 or sigma <= 0:
            return 0
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

    @staticmethod
    def delta(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
        if T <= 0 or sigma <= 0:
            return 1.0 if (option_type == 'CE' and S > K) or (option_type == 'PE' and S < K) else 0.0
        d1 = BlackScholes.d1(S, K, T, r, sigma)
        if option_type == 'CE':
            return BlackScholes.norm_cdf(d1)
        else:
            return BlackScholes.norm_cdf(d1) - 1


class SignalGenerator:
    """Generates real trading signals from actual OHLCV data using technical analysis."""

    def __init__(self):
        self.price_history: List[Dict] = []
        self.max_history = 500
        self.option_iv = 22.0  # Base IV assumption
        self.risk_free_rate = 0.07

    def reset(self):
        self.price_history = []

    def add_tick(self, tick: Dict):
        self.price_history.append(tick)
        if len(self.price_history) > self.max_history:
            self.price_history.pop(0)

    def _get_closes(self) -> pd.Series:
        return pd.Series([t['close'] for t in self.price_history])

    def _get_highs(self) -> pd.Series:
        return pd.Series([t['high'] for t in self.price_history])

    def _get_lows(self) -> pd.Series:
        return pd.Series([t['low'] for t in self.price_history])

    def _get_volumes(self) -> pd.Series:
        return pd.Series([t.get('volume', 0) for t in self.price_history])

    def get_atm_strike(self, spot: float, step: float = 100) -> int:
        return int(round(spot / step) * step)

    def get_option_price(self, spot: float, strike: int, expiry_days: float, option_type: str, iv: float = None) -> float:
        iv = iv or self.option_iv
        T = expiry_days / 365.0
        if option_type == 'CE':
            return BlackScholes.call_price(spot, strike, T, self.risk_free_rate, iv / 100)
        else:
            return BlackScholes.put_price(spot, strike, T, self.risk_free_rate, iv / 100)

    def get_delta(self, spot: float, strike: int, expiry_days: float, option_type: str, iv: float = None) -> float:
        iv = iv or self.option_iv
        T = expiry_days / 365.0
        return BlackScholes.delta(spot, strike, T, self.risk_free_rate, iv / 100, option_type)

    def _is_gap_up(self, open_price: float, prev_close: float) -> bool:
        if prev_close == 0:
            return False
        return ((open_price - prev_close) / prev_close) > 0.0075

    def _is_gap_down(self, open_price: float, prev_close: float) -> bool:
        if prev_close == 0:
            return False
        return ((prev_close - open_price) / prev_close) > 0.0075

    def _detect_regime(self) -> str:
        """Detect current market regime based on volatility and trend."""
        if len(self.price_history) < 30:
            return 'unknown'
        closes = self._get_closes()
        rsi14 = TechnicalIndicators.rsi(closes, 14)
        bb_width = TechnicalIndicators.bollinger_width(closes, 20)
        atr_val = TechnicalIndicators.atr(self._get_highs(), self._get_lows(), closes, 14)
        current_price = closes.iloc[-1]
        sma20 = TechnicalIndicators.sma(closes, 20)
        atr_pct = (atr_val / current_price) * 100 if current_price > 0 else 0

        if atr_pct > 1.5:
            return 'high_vol'
        elif atr_pct < 0.5:
            return 'low_vol'
        elif current_price > sma20 and rsi14 > 55:
            return 'trending_up'
        elif current_price < sma20 and rsi14 < 45:
            return 'trending_down'
        else:
            return 'range_bound'

    def generate_signal(self, strategy_id: str, approach_id: str) -> Optional[Dict]:
        """Generate signal based on strategy and approach using real data."""
        if len(self.price_history) < 20:
            return None

        closes = self._get_closes()
        highs = self._get_highs()
        lows = self._get_lows()
        volumes = self._get_volumes()

        current_price = closes.iloc[-1]
        prev_close = closes.iloc[-2] if len(closes) > 1 else current_price
        open_price = self.price_history[-1].get('open', current_price)
        high_price = highs.iloc[-1]
        low_price = lows.iloc[-1]

        rsi14 = TechnicalIndicators.rsi(closes, 14)
        rsi9 = TechnicalIndicators.rsi(closes, 9)
        sma20 = TechnicalIndicators.sma(closes, 20)
        sma50 = TechnicalIndicators.sma(closes, 50)
        bb_sma, bb_upper, bb_lower = TechnicalIndicators.bollinger_bands(closes, 20)
        bb_width = TechnicalIndicators.bollinger_width(closes, 20)
        atr_val = TechnicalIndicators.atr(highs, lows, closes, 14)
        vwap_val = TechnicalIndicators.vwap(highs, lows, closes, volumes)

        regime = self._detect_regime()

        signal = None

        # ============================================================
        # STRATEGY 001: Iron Condor / Iron Fly Variants
        # ============================================================
        if strategy_id == 'strategy_001':
            if approach_id == 'approach_A':
                # ATM Iron Fly - sell ATM straddle when near expiry ( Wednesdays )
                # Check if Wednesday and within 2 days of expiry
                if len(self.price_history) > 0:
                    try:
                        ts = self.price_history[-1]['timestamp']
                        dt = pd.to_datetime(ts)
                        is_wednesday = dt.weekday() == 2
                    except:
                        is_wednesday = False
                else:
                    is_wednesday = False

                if is_wednesday and len(self.price_history) >= 50:
                    # Enter: sell ATM straddle
                    atm_strike = self.get_atm_strike(current_price, 200)
                    ce_price = self.get_option_price(current_price, atm_strike, 0.5, 'CE')
                    pe_price = self.get_option_price(current_price, atm_strike, 0.5, 'PE')
                    if ce_price + pe_price > 80:
                        return {
                            "signal": "SELL",
                            "strike": atm_strike,
                            "option_type": "STRADDLE",
                            "side": "SELL_STRADDLE",
                            "lots": 1,
                            "reason": f"ATM Iron Fly: ATM={atm_strike}, premium={ce_price+pe_price:.0f}",
                            "confidence": 0.7,
                            "ce_strike": atm_strike,
                            "pe_strike": atm_strike
                        }

            elif approach_id == 'approach_B':
                # Dynamic wing adjustment based on IV
                # Higher IV = wider wings
                iv_rank = self.option_iv / 25.0 * 50  # Approximate
                if len(closes) > 60:
                    hist_ivs = closes.iloc[-60:].rolling(5).std() * 2 + 15
                    iv_rank = TechnicalIndicators.iv_rank(self.option_iv, hist_ivs.tolist())

                atm_strike = self.get_atm_strike(current_price, 200)

                if iv_rank > 70:
                    wing_width = 400
                elif iv_rank > 40:
                    wing_width = 200
                else:
                    wing_width = 100

                ce_strike = atm_strike + wing_width
                pe_strike = atm_strike - wing_width

                return {
                    "signal": "SELL",
                    "strike": atm_strike,
                    "option_type": "IRON_CONDOR",
                    "side": "SELL_IC",
                    "lots": 1,
                    "reason": f"Dynamic IC: IV_rank={iv_rank:.0f}, width={wing_width}",
                    "confidence": 0.65,
                    "ce_strike": ce_strike,
                    "pe_strike": pe_strike
                }

            elif approach_id == 'approach_C':
                # OI-weighted strike selection (simplified - use price momentum as proxy)
                # Momentum-based entry
                if rsi14 < 35 and current_price < bb_lower and len(self.price_history) > 30:
                    # Oversold - expect bounce, sell PE
                    atm_strike = self.get_atm_strike(current_price, 200)
                    pe_price = self.get_option_price(current_price, atm_strike, 1.0, 'PE')
                    if pe_price > 100:
                        return {
                            "signal": "SELL",
                            "strike": atm_strike,
                            "option_type": "PE",
                            "side": "SELL_PE",
                            "lots": 1,
                            "reason": f"Oversold: RSI={rsi14:.1f}, below BB_lower",
                            "confidence": 0.7
                        }
                elif rsi14 > 65 and current_price > bb_upper and len(self.price_history) > 30:
                    # Overbought - expect drop, sell CE
                    atm_strike = self.get_atm_strike(current_price, 200)
                    ce_price = self.get_option_price(current_price, atm_strike, 1.0, 'CE')
                    if ce_price > 100:
                        return {
                            "signal": "SELL",
                            "strike": atm_strike,
                            "option_type": "CE",
                            "side": "SELL_CE",
                            "lots": 1,
                            "reason": f"Overbought: RSI={rsi14:.1f}, above BB_upper",
                            "confidence": 0.7
                        }

        # ============================================================
        # STRATEGY 002: Momentum-Based Directional
        # ============================================================
        elif strategy_id == 'strategy_002':
            if approach_id == 'approach_A':
                # 9:15 gap strategy
                gap_up = self._is_gap_up(open_price, prev_close)
                gap_down = self._is_gap_down(open_price, prev_close)

                if gap_up and len(self.price_history) > 20:
                    # Buy CE on gap up
                    atm_strike = self.get_atm_strike(current_price, 100)
                    ce_price = self.get_option_price(current_price, atm_strike, 0.5, 'CE')
                    return {
                        "signal": "BUY",
                        "strike": atm_strike,
                        "option_type": "CE",
                        "side": "BUY_CE",
                        "lots": 1,
                        "reason": f"Gap up: {((open_price-prev_close)/prev_close)*100:.2f}%, ATM={atm_strike}",
                        "confidence": 0.75
                    }
                elif gap_down and len(self.price_history) > 20:
                    atm_strike = self.get_atm_strike(current_price, 100)
                    pe_price = self.get_option_price(current_price, atm_strike, 0.5, 'PE')
                    return {
                        "signal": "BUY",
                        "strike": atm_strike,
                        "option_type": "PE",
                        "side": "BUY_PE",
                        "lots": 1,
                        "reason": f"Gap down: {((prev_close-open_price)/prev_close)*100:.2f}%, ATM={atm_strike}",
                        "confidence": 0.75
                    }

            elif approach_id == 'approach_B':
                # 5-min VWAP breakout with momentum filter
                if rsi14 > 55 and current_price > vwap_val and current_price > sma20:
                    atm_strike = self.get_atm_strike(current_price, 100)
                    ce_price = self.get_option_price(current_price, atm_strike, 0.5, 'CE')
                    return {
                        "signal": "BUY",
                        "strike": atm_strike,
                        "option_type": "CE",
                        "side": "BUY_CE",
                        "lots": 1,
                        "reason": f"VWAP breakout: price={current_price:.0f}, VWAP={vwap_val:.0f}, RSI={rsi14:.1f}",
                        "confidence": 0.7
                    }
                elif rsi14 < 45 and current_price < vwap_val and current_price < sma20:
                    atm_strike = self.get_atm_strike(current_price, 100)
                    pe_price = self.get_option_price(current_price, atm_strike, 0.5, 'PE')
                    return {
                        "signal": "BUY",
                        "strike": atm_strike,
                        "option_type": "PE",
                        "side": "BUY_PE",
                        "lots": 1,
                        "reason": f"VWAP breakdown: price={current_price:.0f}, VWAP={vwap_val:.0f}, RSI={rsi14:.1f}",
                        "confidence": 0.7
                    }

            elif approach_id == 'approach_C':
                # Opening Range Breakout (ORB)
                if len(self.price_history) > 15:
                    range_high = highs.iloc[-15:].max()
                    range_low = lows.iloc[-15:].max()
                    range_breakout_up = current_price > range_high * 1.003
                    range_breakout_down = current_price < range_low * 0.997

                    if range_breakout_up:
                        atm_strike = self.get_atm_strike(current_price, 100)
                        return {
                            "signal": "BUY",
                            "strike": atm_strike,
                            "option_type": "CE",
                            "side": "BUY_CE",
                            "lots": 1,
                            "reason": f"ORB up: range_high={range_high:.0f}, current={current_price:.0f}",
                            "confidence": 0.7
                        }
                    elif range_breakout_down:
                        atm_strike = self.get_atm_strike(current_price, 100)
                        return {
                            "signal": "BUY",
                            "strike": atm_strike,
                            "option_type": "PE",
                            "side": "BUY_PE",
                            "lots": 1,
                            "reason": f"ORB down: range_low={range_low:.0f}, current={current_price:.0f}",
                            "confidence": 0.7
                        }

        # ============================================================
        # STRATEGY 003: Mean Reversion
        # ============================================================
        elif strategy_id == 'strategy_003':
            if approach_id == 'approach_A':
                # BB squeeze with straddle entry
                if bb_width < 0.02 and len(self.price_history) > 30:
                    # Squeeze detected - expect expansion
                    return {
                        "signal": "BUY",
                        "strike": self.get_atm_strike(current_price, 200),
                        "option_type": "STRADDLE",
                        "side": "BUY_STRADDLE",
                        "lots": 1,
                        "reason": f"BB squeeze: width={bb_width:.3f}, expect expansion",
                        "confidence": 0.7,
                        "ce_strike": self.get_atm_strike(current_price, 200),
                        "pe_strike": self.get_atm_strike(current_price, 200)
                    }
                elif current_price < bb_lower and len(self.price_history) > 20:
                    # Price below lower band - mean reversion bounce
                    atm_strike = self.get_atm_strike(current_price, 200)
                    return {
                        "signal": "BUY",
                        "strike": atm_strike,
                        "option_type": "CE",
                        "side": "BUY_CE",
                        "lots": 1,
                        "reason": f"Below BB lower: price={current_price:.0f}, BB_lower={bb_lower:.0f}",
                        "confidence": 0.65
                    }
                elif current_price > bb_upper and len(self.price_history) > 20:
                    atm_strike = self.get_atm_strike(current_price, 200)
                    return {
                        "signal": "BUY",
                        "strike": atm_strike,
                        "option_type": "PE",
                        "side": "BUY_PE",
                        "lots": 1,
                        "reason": f"Above BB upper: price={current_price:.0f}, BB_upper={bb_upper:.0f}",
                        "confidence": 0.65
                    }

            elif approach_id == 'approach_B':
                # IV rank-based premium selling
                # High IV = sell premium
                if self.option_iv > 25 and rsi14 > 60:
                    atm_strike = self.get_atm_strike(current_price, 200)
                    ce_price = self.get_option_price(current_price, atm_strike + 300, 1.0, 'CE')
                    if ce_price > 80:
                        return {
                            "signal": "SELL",
                            "strike": atm_strike + 300,
                            "option_type": "CE",
                            "side": "SELL_OTM_CE",
                            "lots": 1,
                            "reason": f"High IV sell: IV={self.option_iv:.0f}, RSI={rsi14:.1f}",
                            "confidence": 0.7
                        }
                elif self.option_iv > 25 and rsi14 < 40:
                    atm_strike = self.get_atm_strike(current_price, 200)
                    pe_price = self.get_option_price(current_price, atm_strike - 300, 1.0, 'PE')
                    if pe_price > 80:
                        return {
                            "signal": "SELL",
                            "strike": atm_strike - 300,
                            "option_type": "PE",
                            "side": "SELL_OTM_PE",
                            "lots": 1,
                            "reason": f"High IV sell: IV={self.option_iv:.0f}, RSI={rsi14:.1f}",
                            "confidence": 0.7
                        }

            elif approach_id == 'approach_C':
                # Delta-neutral adjustment
                delta = self.get_delta(current_price, self.get_atm_strike(current_price, 200), 1.0, 'CE')
                if abs(delta) > 0.25 and len(self.price_history) > 30:
                    if delta > 0.25:
                        # Positive delta - hedge with PE
                        return {
                            "signal": "BUY",
                            "strike": self.get_atm_strike(current_price, 200),
                            "option_type": "PE",
                            "side": "HEDGE_PE",
                            "lots": 1,
                            "reason": f"Delta hedge: delta={delta:.2f}",
                            "confidence": 0.6
                        }
                    elif delta < -0.25:
                        return {
                            "signal": "BUY",
                            "strike": self.get_atm_strike(current_price, 200),
                            "option_type": "CE",
                            "side": "HEDGE_CE",
                            "lots": 1,
                            "reason": f"Delta hedge: delta={delta:.2f}",
                            "confidence": 0.6
                        }

        # ============================================================
        # STRATEGY 004: Event-Based
        # ============================================================
        elif strategy_id == 'strategy_004':
            if approach_id == 'approach_A':
                # Expiry day theta decay
                if len(self.price_history) > 0:
                    try:
                        ts = self.price_history[-1]['timestamp']
                        dt = pd.to_datetime(ts)
                        is_wednesday = dt.weekday() == 2
                    except:
                        is_wednesday = False
                else:
                    is_wednesday = False

                if is_wednesday and len(self.price_history) > 20:
                    # Sell OTM straddle on expiry day
                    atm_strike = self.get_atm_strike(current_price, 200)
                    otm_ce_strike = atm_strike + int(current_price * 0.015 / 100) * 100 + 200
                    otm_pe_strike = atm_strike - int(current_price * 0.015 / 100) * 100 - 200
                    ce_price = self.get_option_price(current_price, otm_ce_strike, 0.1, 'CE')
                    pe_price = self.get_option_price(current_price, otm_pe_strike, 0.1, 'PE')
                    if ce_price + pe_price > 60:
                        return {
                            "signal": "SELL",
                            "strike": atm_strike,
                            "option_type": "STRANGLE",
                            "side": "SELL_STRANGLE",
                            "lots": 1,
                            "reason": f"Expiry theta: CE_strike={otm_ce_strike}, PE_strike={otm_pe_strike}",
                            "confidence": 0.75,
                            "ce_strike": otm_ce_strike,
                            "pe_strike": otm_pe_strike
                        }

            elif approach_id == 'approach_B':
                # Pre-event IV spike (simplified: high IV + RSI extremes)
                if self.option_iv > 28 and (rsi14 > 70 or rsi14 < 30):
                    atm_strike = self.get_atm_strike(current_price, 200)
                    if rsi14 > 70:
                        return {
                            "signal": "SELL",
                            "strike": atm_strike + 300,
                            "option_type": "CE",
                            "side": "SELL_OTM_CE",
                            "lots": 1,
                            "reason": f"Pre-event high IV: IV={self.option_iv:.0f}, RSI={rsi14:.1f}",
                            "confidence": 0.7
                        }
                    else:
                        return {
                            "signal": "SELL",
                            "strike": atm_strike - 300,
                            "option_type": "PE",
                            "side": "SELL_OTM_PE",
                            "lots": 1,
                            "reason": f"Pre-event high IV: IV={self.option_iv:.0f}, RSI={rsi14:.1f}",
                            "confidence": 0.7
                        }

            elif approach_id == 'approach_C':
                # Weekly expiry rollover (Thursday/Friday)
                if len(self.price_history) > 0:
                    try:
                        ts = self.price_history[-1]['timestamp']
                        dt = pd.to_datetime(ts)
                        is_thursday = dt.weekday() == 3
                        is_friday = dt.weekday() == 4
                    except:
                        is_thursday = is_friday = False
                else:
                    is_thursday = is_friday = False

                if (is_thursday or is_friday) and len(self.price_history) > 30:
                    # Look for divergence between price and RSI for reversal
                    if rsi14 < 35 and current_price < sma50:
                        return {
                            "signal": "BUY",
                            "strike": self.get_atm_strike(current_price, 100),
                            "option_type": "CE",
                            "side": "BUY_CE",
                            "lots": 1,
                            "reason": f"Rollover reversal: RSI={rsi14:.1f}, below SMA50",
                            "confidence": 0.65
                        }
                    elif rsi14 > 65 and current_price > sma50:
                        return {
                            "signal": "BUY",
                            "strike": self.get_atm_strike(current_price, 100),
                            "option_type": "PE",
                            "side": "BUY_PE",
                            "lots": 1,
                            "reason": f"Rollover reversal: RSI={rsi14:.1f}, above SMA50",
                            "confidence": 0.65
                        }

        # ============================================================
  # STRATEGY 005: Greeks-Based
        # ============================================================
        elif strategy_id == 'strategy_005':
            if approach_id == 'approach_A':
                # Gamma scalping near ATM
                atm_strike = self.get_atm_strike(current_price, 100)
                delta = self.get_delta(current_price, atm_strike, 0.5, 'CE')
                gamma = delta * 0.1  # Simplified gamma

                if abs(delta - 0.5) < 0.15 and rsi14 > 50 and len(self.price_history) > 20:
                    # Near ATM with neutral delta
                    return {
                        "signal": "BUY",
                        "strike": atm_strike,
                        "option_type": "STRADDLE",
                        "side": "BUY_STRADDLE",
                        "lots": 1,
                        "reason": f"Gamma scalping: delta={delta:.2f}, ATM={atm_strike}",
                        "confidence": 0.7,
                        "ce_strike": atm_strike,
                        "pe_strike": atm_strike
                    }

            elif approach_id == 'approach_B':
                # Vega-neutral spread
                if self.option_iv > 22 and regime == 'high_vol':
                    atm_strike = self.get_atm_strike(current_price, 200)
                    itm_strike = atm_strike - 200
                    otm_strike = atm_strike + 200
                    return {
                        "signal": "BUY",
                        "strike": atm_strike,
                        "option_type": "STRADDLE",
                        "side": "BUY_ATM_STRADDLE",
                        "lots": 1,
                        "reason": f"Vega-neutral: IV={self.option_iv:.0f}, regime={regime}",
                        "confidence": 0.65,
                        "ce_strike": atm_strike,
                        "pe_strike": atm_strike
                    }

            elif approach_id == 'approach_C':
                # Delta hedging with dynamic rebalancing
                atm_strike = self.get_atm_strike(current_price, 200)
                delta_val = self.get_delta(current_price, atm_strike, 1.0, 'CE')

                if abs(delta_val) > 0.15:
                    if delta_val > 0.15:
                        return {
                            "signal": "SELL",
                            "strike": atm_strike,
                            "option_type": "PE",
                            "side": "DELTA_HEDGE_SELL_PE",
                            "lots": 1,
                            "reason": f"Delta rebalance: delta={delta_val:.2f}",
                            "confidence": 0.6
                        }
                    else:
                        return {
                            "signal": "SELL",
                            "strike": atm_strike,
                            "option_type": "CE",
                            "side": "DELTA_HEDGE_SELL_CE",
                            "lots": 1,
                            "reason": f"Delta rebalance: delta={delta_val:.2f}",
                            "confidence": 0.6
                        }

        # ============================================================
        # STRATEGY 006: ML-Assisted / Regime-Based
        # ============================================================
        elif strategy_id == 'strategy_006':
            if approach_id == 'approach_A':
                # Random Forest signal (simplified: trend + RSI + BB)
                if regime == 'trending_up' and rsi14 > 55 and current_price > bb_upper:
                    atm_strike = self.get_atm_strike(current_price, 100)
                    return {
                        "signal": "BUY",
                        "strike": atm_strike,
                        "option_type": "CE",
                        "side": "BUY_CE",
                        "lots": 1,
                        "reason": f"ML trend: regime={regime}, RSI={rsi14:.1f}",
                        "confidence": 0.75
                    }
                elif regime == 'trending_down' and rsi14 < 45 and current_price < bb_lower:
                    atm_strike = self.get_atm_strike(current_price, 100)
                    return {
                        "signal": "BUY",
                        "strike": atm_strike,
                        "option_type": "PE",
                        "side": "BUY_PE",
                        "lots": 1,
                        "reason": f"ML trend: regime={regime}, RSI={rsi14:.1f}",
                        "confidence": 0.75
                    }

            elif approach_id == 'approach_B':
                # LSTM signal (simplified: momentum confirmation)
                if rsi9 > 60 and rsi14 > 55 and sma20 > sma50:
                    atm_strike = self.get_atm_strike(current_price, 100)
                    return {
                        "signal": "BUY",
                        "strike": atm_strike,
                        "option_type": "CE",
                        "side": "BUY_CE",
                        "lots": 1,
                        "reason": f"LSTM momentum: RSI9={rsi9:.1f}, RSI14={rsi14:.1f}",
                        "confidence": 0.7
                    }
                elif rsi9 < 40 and rsi14 < 45 and sma20 < sma50:
                    atm_strike = self.get_atm_strike(current_price, 100)
                    return {
                        "signal": "BUY",
                        "strike": atm_strike,
                        "option_type": "PE",
                        "side": "BUY_PE",
                        "lots": 1,
                        "reason": f"LSTM momentum: RSI9={rsi9:.1f}, RSI14={rsi14:.1f}",
                        "confidence": 0.7
                    }

            elif approach_id == 'approach_C':
                # Clustering market regimes
                if regime == 'range_bound' and bb_width < 0.03:
                    # BB squeeze in range-bound = breakout coming
                    return {
                        "signal": "BUY",
                        "strike": self.get_atm_strike(current_price, 200),
                        "option_type": "STRADDLE",
                        "side": "BUY_STRADDLE",
                        "lots": 1,
                        "reason": f"Regime cluster: {regime}, BB_width={bb_width:.3f}",
                        "confidence": 0.7,
                        "ce_strike": self.get_atm_strike(current_price, 200),
                        "pe_strike": self.get_atm_strike(current_price, 200)
                    }
                elif regime == 'high_vol':
                    atm_strike = self.get_atm_strike(current_price, 200)
                    return {
                        "signal": "SELL",
                        "strike": atm_strike,
                        "option_type": "STRADDLE",
                        "side": "SELL_STRANGLE",
                        "lots": 1,
                        "reason": f"High vol regime: {regime}, sell strangle",
                        "confidence": 0.7,
                        "ce_strike": atm_strike + 300,
                        "pe_strike": atm_strike - 300
                    }

        return signal


if __name__ == "__main__":
    sg = SignalGenerator()
    print("SignalGenerator loaded. Ready to generate real signals from OHLCV data.")