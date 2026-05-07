"""
Strategy 003/approach_C — BB Squeeze Breakout
Entry: BUY ATM straddle when BB_width < 0.03 AND regime != 'high_vol'
Exit: 50% profit | -30% stop | 60 tick time exit
Confidence threshold: >= 0.70
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "agents"))

import pandas as pd
import math

STRATEGY_ID = "strategy_003"
APPROACH_ID = "approach_C"


class TechnicalIndicators:
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
        sma_val = closes.iloc[-period:].mean()
        std = closes.iloc[-period:].std()
        return sma_val, sma_val + (2 * std), sma_val - (2 * std)

    @staticmethod
    def bollinger_width(closes: pd.Series, period: int = 20) -> float:
        if len(closes) < period:
            return 0
        sma_val, upper, lower = TechnicalIndicators.bollinger_bands(closes, period)
        return (upper - lower) / sma_val if sma_val > 0 else 0

    @staticmethod
    def atr(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int = 14) -> float:
        if len(closes) < period + 1:
            return (highs - lows).mean() if len(highs) > 1 else 0
        tr1 = highs - lows
        tr2 = (highs - closes.shift(1)).abs()
        tr3 = (lows - closes.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.iloc[-period:].mean()


class BlackScholes:
    @staticmethod
    def norm_cdf(x: float) -> float:
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    @staticmethod
    def call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        if T <= 0:
            return max(0, S - K)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return S * BlackScholes.norm_cdf(d1) - K * math.exp(-r * T) * BlackScholes.norm_cdf(d2)

    @staticmethod
    def put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        if T <= 0:
            return max(0, K - S)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return K * math.exp(-r * T) * BlackScholes.norm_cdf(-d2) - S * BlackScholes.norm_cdf(-d1)


class Strategy003ApproachC:
    """BB Squeeze Breakout — BUY ATM straddle on Bollinger Band squeeze.

    Entry: BB_width < 0.03 AND regime != 'high_vol' → BUY ATM straddle
    Exit: 50% profit | -30% stop | 60 tick time exit
    """

    STRATEGY_ID = STRATEGY_ID
    APPROACH_ID = APPROACH_ID

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.price_history = []
        self.max_history = 100
        self.option_iv = 22.0
        self.risk_free_rate = 0.07
        self.confidence_threshold = 0.70

    def _closes(self) -> pd.Series:
        return pd.Series([t['close'] for t in self.price_history])

    def _highs(self) -> pd.Series:
        return pd.Series([t.get('high', t['close']) for t in self.price_history])

    def _lows(self) -> pd.Series:
        return pd.Series([t.get('low', t['close']) for t in self.price_history])

    def _detect_regime(self, price: float, sma20: float, rsi14: float, atr_pct: float) -> str:
        """Detect market regime based on ATR%, price position, RSI."""
        if atr_pct > 1.5:
            return 'high_vol'
        elif atr_pct < 0.5:
            return 'low_vol'
        elif price > sma20 and rsi14 > 55:
            return 'trending_up'
        elif price < sma20 and rsi14 < 45:
            return 'trending_down'
        else:
            return 'range_bound'

    def get_atm_strike(self, spot: float, step: float = 200) -> int:
        return int(round(spot / step) * step)

    def option_price(self, spot: float, strike: int, expiry_days: float, opt_type: str, iv: float = None) -> float:
        iv = iv or self.option_iv
        T = expiry_days / 365.0
        if opt_type == 'CE':
            return BlackScholes.call_price(spot, strike, T, self.risk_free_rate, iv / 100)
        else:
            return BlackScholes.put_price(spot, strike, T, self.risk_free_rate, iv / 100)

    def get_entry_signal(self, tick: dict) -> dict:
        """Generate entry signal from tick data.

        BUY ATM straddle when: BB_width < 0.03 AND regime != 'high_vol'
        """
        self.price_history.append(tick)
        if len(self.price_history) > self.max_history:
            self.price_history.pop(0)

        if len(self.price_history) < 30:
            return None

        closes = self._closes()
        highs = self._highs()
        lows = self._lows()

        price = closes.iloc[-1]
        sma20 = TechnicalIndicators.sma(closes, 20)
        rsi14 = TechnicalIndicators.rsi(closes, 14)
        atr_val = TechnicalIndicators.atr(highs, lows, closes, 14)
        bb_width = TechnicalIndicators.bollinger_width(closes, 20)

        atr_pct = (atr_val / price) * 100 if price > 0 else 0
        regime = self._detect_regime(price, sma20, rsi14, atr_pct)

        # BB squeeze breakout: BB_width < 0.03 and not high_vol regime
        if bb_width < 0.03 and regime != 'high_vol':
            atm = self.get_atm_strike(price, 200)
            ce_p = self.option_price(price, atm, 0.5, 'CE')
            pe_p = self.option_price(price, atm, 0.5, 'PE')
            total_premium = ce_p + pe_p
            if total_premium > 20:
                return {
                    "signal": "BUY",
                    "action": "BUY",
                    "strike": atm,
                    "option_type": "STRADDLE",
                    "lots": 1,
                    "confidence": 0.70,
                    "reason": f"BB squeeze: w={bb_width:.3f}, regime={regime}",
                    "ce_strike": atm,
                    "pe_strike": atm
                }

        return None

    def get_exit_signal(self, position: dict, tick: dict) -> dict:
        """Check exit conditions for open position.

        Exit rules:
        - 50% profit: P&L >= 50% of entry straddle premium
        - -30% stop loss: P&L <= -30% of entry premium
        - Time exit: 60 ticks elapsed
        """
        entry_opt_price = position.get("entry_opt_price", 0)
        entry_tick = position.get("entry_tick", 0)
        opt = position.get("option_type", "CE")
        strike = position.get("strike", 0)
        current_tick = tick.get("tick_num", 0)
        ticks_elapsed = current_tick - entry_tick

        close_price = tick.get("close", tick.get("ltp", entry_opt_price))

        # For straddle, compute both legs
        if opt == "STRADDLE":
            atm = position.get("strike", self.get_atm_strike(close_price, 200))
            ce_p = self.option_price(close_price, atm, 0.5, 'CE')
            pe_p = self.option_price(close_price, atm, 0.5, 'PE')
            current_opt_price = ce_p + pe_p
        else:
            current_opt_price = self.option_price(close_price, strike, 0.5, opt)

        if entry_opt_price > 0:
            pnl_pct = (current_opt_price - entry_opt_price) / entry_opt_price
        else:
            pnl_pct = 0

        action = position.get("action", "BUY")

        if action == "BUY":
            if pnl_pct >= 0.50:
                return {"should_exit": True, "reason": "50% profit target", "exit_price": current_opt_price}
            if pnl_pct <= -0.30:
                return {"should_exit": True, "reason": "30% stop loss", "exit_price": current_opt_price}
            if ticks_elapsed > 60 and pnl_pct < 0.10:
                return {"should_exit": True, "reason": "60 tick time exit", "exit_price": current_opt_price}

        return {"should_exit": False}

    def reset(self):
        self.price_history = []