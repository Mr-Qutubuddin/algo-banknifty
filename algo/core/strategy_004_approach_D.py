"""
Strategy 004/approach_D — Intraday Momentum Breakout
Entry: BUY CE when price > SMA20 AND RSI(14) > 62; BUY PE when price < SMA20 AND RSI(14) < 38
Exit: 50% profit | -30% stop | 60 tick time exit
Confidence threshold: >= 0.60
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "agents"))

import pandas as pd
import math

STRATEGY_ID = "strategy_004"
APPROACH_ID = "approach_D"


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


class Strategy004ApproachD:
    """Intraday Momentum Breakout — BUY on SMA20 + RSI14 crossover."""

    STRATEGY_ID = STRATEGY_ID
    APPROACH_ID = APPROACH_ID

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.price_history = []
        self.max_history = 100
        self.option_iv = 22.0
        self.risk_free_rate = 0.07
        self.confidence_threshold = 0.60

    def _closes(self) -> pd.Series:
        return pd.Series([t['close'] for t in self.price_history])

    def _highs(self) -> pd.Series:
        return pd.Series([t.get('high', t['close']) for t in self.price_history])

    def _lows(self) -> pd.Series:
        return pd.Series([t.get('low', t['close']) for t in self.price_history])

    def get_atm_strike(self, spot: float, step: float = 100) -> int:
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

        BUY CE when: price > SMA20 AND RSI(14) > 62
        BUY PE when: price < SMA20 AND RSI(14) < 38
        """
        self.price_history.append(tick)
        if len(self.price_history) > self.max_history:
            self.price_history.pop(0)

        if len(self.price_history) < 20:
            return None

        closes = self._closes()
        price = closes.iloc[-1]
        sma20 = TechnicalIndicators.sma(closes, 20)
        rsi14 = TechnicalIndicators.rsi(closes, 14)

        # Buy CE: price above SMA20 with strong RSI momentum
        if price > sma20 and rsi14 > 62:
            atm = self.get_atm_strike(price, 100)
            ce_p = self.option_price(price, atm, 0.5, 'CE')
            if ce_p > 30:
                return {
                    "signal": "BUY",
                    "action": "BUY",
                    "strike": atm,
                    "option_type": "CE",
                    "lots": 1,
                    "confidence": 0.60,
                    "reason": f"Intraday long: RSI14={rsi14:.1f}, price>{sma20:.0f}"
                }

        # Buy PE: price below SMA20 with weak RSI
        if price < sma20 and rsi14 < 38:
            atm = self.get_atm_strike(price, 100)
            pe_p = self.option_price(price, atm, 0.5, 'PE')
            if pe_p > 30:
                return {
                    "signal": "BUY",
                    "action": "BUY",
                    "strike": atm,
                    "option_type": "PE",
                    "lots": 1,
                    "confidence": 0.60,
                    "reason": f"Intraday short: RSI14={rsi14:.1f}, price<{sma20:.0f}"
                }

        return None

    def get_exit_signal(self, position: dict, tick: dict) -> dict:
        """Check exit conditions for open position.

        Exit rules:
        - 50% profit: P&L >= 50% of entry premium
        - -30% stop loss: P&L <= -30% of entry premium
        - Time exit: 60 ticks elapsed
        """
        entry_price = position.get("entry_price", 0)
        entry_opt_price = position.get("entry_opt_price", entry_price)
        entry_tick = position.get("entry_tick", 0)
        opt = position.get("option_type", "CE")
        strike = position.get("strike", 0)
        current_tick = tick.get("tick_num", 0)
        ticks_elapsed = current_tick - entry_tick

        # Compute current option price
        close_price = tick.get("close", tick.get("ltp", entry_price))
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