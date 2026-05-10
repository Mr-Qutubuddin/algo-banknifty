"""
ScalpingBacktest — Reusable backtest agent framework for options strategies.
Supports BANKNIFTY ATM options, Nifty 50 OTM scalping, multiple strategies,
and realistic brokerage modeling.

Usage:
    from backtests.scalping_backtest import ScalpingBacktest, ScalpingStrategy

    # Define your strategy
    class MyStrategy(ScalpingStrategy):
        def get_entry_signal(self, tick, position, portfolio):
            # Return dict with keys: action, strike, option_type, lots, reason
            # Or None to stay flat
            pass

        def get_exit_signal(self, tick, position, portfolio):
            # Return dict with keys: should_exit, reason, exit_price
            pass

    # Run backtest
    bt = ScalpingBacktest(initial_capital=100_000)
    bt.add_strategy(MyStrategy, name="my_strategy")
    results = bt.run(data_feed, timeframe="1m")
    bt.print_stats()
    bt.plot_equity()
"""
import logging
import math
import operator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable, Any

import pandas as pd
import numpy as np

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "scalping_backtest.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Black-Scholes (shared)
# ──────────────────────────────────────────────────────────────────────────────

class BlackScholes:
    IV_DEFAULT = 22.0  # percent

    @staticmethod
    def norm_cdf(x: float) -> float:
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    @staticmethod
    def call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        if T <= 0:
            return max(0.0, S - K)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return S * BlackScholes.norm_cdf(d1) - K * math.exp(-r * T) * BlackScholes.norm_cdf(d2)

    @staticmethod
    def put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        if T <= 0:
            return max(0.0, K - S)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return K * math.exp(-r * T) * BlackScholes.norm_cdf(-d2) - S * BlackScholes.norm_cdf(-d1)


# ──────────────────────────────────────────────────────────────────────────────
# Brokerage Model
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class BrokerageCharges:
    """Brokerage & govt charges breakdown per trade (one side)."""
    brokerage: float = 0.0
    gst: float = 0.0
    stt: float = 0.0      # charged on sell side only
    sebi: float = 0.0
    stamp_duty: float = 0.0
    total: float = 0.0

    def total_charges(self) -> float:
        return self.total


class BrokerageModel:
    """
    Realistic Indian broker charges:
    - Rs.5 flat per side (buy or sell)
    - 6.5% GST on brokerage
    - 0.05% STT on sell turnover only
    - 0.01% SEBI on total turnover
    - 0.05% stamp duty on buy turnover (NSE)
    - 0.05% slippage (applied separately as price impact)
    """
    BROKERAGE_FLAT = 5.0           # Rs.5 per side
    GST_PCT        = 0.065         # 6.5%
    STT_PCT        = 0.0005        # 0.05% on sell turnover
    SEBI_PCT       = 0.0001        # 0.01% on total turnover
    STAMP_PCT      = 0.0005        # 0.05% stamp duty on buy turnover
    SLIPPAGE_PCT   = 0.0005        # 0.05% price slippage

    def __init__(self, lot_size: int = 15):
        self.lot_size = lot_size

    def calculate_charges(self, price: float, qty: int, side: str) -> BrokerageCharges:
        """
        Calculate all charges for a single-side execution.
        `side` is "BUY" or "SELL".
        """
        turnover = price * qty * self.lot_size
        brokerage = self.BROKERAGE_FLAT
        gst = brokerage * self.GST_PCT
        stt = (turnover * self.STT_PCT) if side == "SELL" else 0.0
        sebi = turnover * self.SEBI_PCT
        stamp = (turnover * self.STAMP_PCT) if side == "BUY" else 0.0
        total = brokerage + gst + stt + sebi + stamp
        return BrokerageCharges(
            brokerage=round(brokerage, 2),
            gst=round(gst, 2),
            stt=round(stt, 2),
            sebi=round(sebi, 2),
            stamp_duty=round(stamp, 2),
            total=round(total, 2),
        )

    def apply_slippage(self, price: float, side: str) -> float:
        """Return fill price after slippage."""
        slip = price * self.SLIPPAGE_PCT
        return price + slip if side == "BUY" else price - slip

    def round_lot(self, price: float) -> float:
        """Round price to nearest 0.05 (NSE option price tick)."""
        return round(price / 0.05) * 0.05


# ──────────────────────────────────────────────────────────────────────────────
# Option Strike Selector
# ──────────────────────────────────────────────────────────────────────────────

class StrikeSelector:
    """Select ATM / OTM strikes for BANKNIFTY and Nifty 50 options."""

    BANKNIFTY_STEP = 100
    NIFTY50_STEP   = 50

    @classmethod
    def get_atm_strike(cls, spot: float, instrument: str = "BANKNIFTY") -> int:
        step = cls.BANKNIFTY_STEP if instrument == "BANKNIFTY" else cls.NIFTY50_STEP
        return int(round(spot / step) * step)

    @classmethod
    def get_otm_strike(cls, spot: float, delta: int, instrument: str = "BANKNIFTY") -> int:
        """
        Get OTM strike offset by `delta` steps from ATM.
        delta > 0 → OTM Call / PUT PE side
        delta < 0 → ITM Put / Call side
        """
        step = cls.BANKNIFTY_STEP if instrument == "BANKNIFTY" else cls.NIFTY50_STEP
        atm = cls.get_atm_strike(spot, instrument)
        return atm + (delta * step)

    @classmethod
    def get_option_price(
        cls, spot: float, strike: int, expiry_days: float,
        option_type: str, iv: float = None, r: float = 0.07
    ) -> float:
        iv = iv if iv is not None else BlackScholes.IV_DEFAULT
        T = max(expiry_days, 1e-6) / 365.0
        sigma = iv / 100.0
        if option_type.upper() == "CE":
            return BlackScholes.call_price(spot, strike, T, r, sigma)
        else:
            return BlackScholes.put_price(spot, strike, T, r, sigma)


# ──────────────────────────────────────────────────────────────────────────────
# ScalpingStrategy — base class for all strategies
# ──────────────────────────────────────────────────────────────────────────────

class ScalpingStrategy:
    """
    Base class for strategies used in ScalpingBacktest.

    Subclasses must implement:
        get_entry_signal(tick, position, portfolio) -> dict | None
        get_exit_signal(tick, position, portfolio)  -> dict | None

    Entry signal dict:
        action       (str): "BUY" or "SELL"
        strike       (int): strike price (ATM auto-computed if 0)
        option_type  (str): "CE" or "PE"
        lots         (int): number of lots
        reason       (str): human-readable reason
        confidence   (float): 0.0–1.0 (optional)

    Exit signal dict:
        should_exit  (bool): True → close position
        reason       (str): exit reason
        exit_price   (float): override exit price (optional)
    """

    STRATEGY_ID   = "base"
    APPROACH_ID   = "base"
    IV            = 22.0
    RISK_FREE     = 0.07
    INSTRUMENT    = "BANKNIFTY"

    def __init__(self, config: dict = None):
        self.config = config or {}
        self._price_history: List[Dict] = []
        self._max_history = 500
        self._tick_count  = 0

    # ── price history helpers ──────────────────────────────────────────────────

    def _closes(self) -> pd.Series:
        return pd.Series([t["close"] for t in self._price_history])

    def _highs(self) -> pd.Series:
        return pd.Series([t.get("high", t["close"]) for t in self._price_history])

    def _lows(self) -> pd.Series:
        return pd.Series([t.get("low", t["close"]) for t in self._price_history])

    def _vols(self) -> pd.Series:
        return pd.Series([t.get("volume", 0) for t in self._price_history])

    # ── required overrides ─────────────────────────────────────────────────────

    def get_entry_signal(self, tick: dict, position: dict, portfolio: "PortfolioState") -> Optional[dict]:
        """Return entry signal dict or None."""
        raise NotImplementedError

    def get_exit_signal(self, tick: dict, position: dict, portfolio: "PortfolioState") -> dict:
        """Return exit signal dict."""
        raise NotImplementedError

    # ── optional overrides ──────────────────────────────────────────────────────

    def on_bar(self, tick: dict, portfolio: "PortfolioState") -> None:
        """Called once per bar/tick after processing. Override for custom logic."""
        pass

    def reset(self) -> None:
        """Reset internal state between runs."""
        self._price_history = []
        self._tick_count = 0

    # ── internal ───────────────────────────────────────────────────────────────

    def _push_tick(self, tick: dict) -> None:
        self._price_history.append(tick)
        if len(self._price_history) > self._max_history:
            self._price_history.pop(0)
        self._tick_count += 1

    @property
    def tick_count(self) -> int:
        return self._tick_count


# ──────────────────────────────────────────────────────────────────────────────
# Portfolio State (read-only snapshot passed to strategies)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PortfolioState:
    """Read-only snapshot of portfolio state for strategy decision-making."""
    equity: float
    cash: float
    unrealized_pnl: float
    realized_pnl: float
    open_positions: int
    total_trades: int
    win_count: int
    loss_count: int
    max_drawdown_pct: float


# ──────────────────────────────────────────────────────────────────────────────
# Trade Log Entry
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TradeLog:
    """Full details of a closed trade."""
    trade_id: str
    strategy_id: str
    instrument: str
    option_type: str
    strike: int
    side: str
    entry_time: str
    exit_time: str
    duration_minutes: float
    lots: int
    entry_price: float
    exit_price: float
    pnl_gross: float       # before charges
    pnl_net: float         # after all charges
    brokerage: float
    gst: float
    stt: float
    sebi: float
    stamp_duty: float
    total_charges: float
    exit_reason: str
    confidence: float = 0.0
    # ── equity curve ────────────────────────────────────────────────────────────
    equity_at_entry: float = 0.0
    equity_at_exit:  float = 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Position (in-memory, per-strategy)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ActivePosition:
    """An active position being tracked in the backtest."""
    position_id: str
    strategy_id: str
    instrument: str
    option_type: str
    strike: int
    side: str
    lots: int
    entry_price: float
    entry_time: str
    entry_charges: BrokerageCharges
    entry_tick: int = 0
    confidence: float = 0.0
    reason: str = ""

    def margin_required(self, margin_pct: float = 0.20) -> float:
        return self.entry_price * self.lots * 15 * margin_pct

    def unrealized_pnl(self, current_price: float) -> float:
        mult = 1 if self.side == "BUY" else -1
        return mult * (current_price - self.entry_price) * self.lots * 15


# ──────────────────────────────────────────────────────────────────────────────
# Equity Recorder
# ──────────────────────────────────────────────────────────────────────────────

class EquityRecorder:
    """Records equity curve snapshots throughout backtest run."""

    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.equity_curve: List[Dict] = []
        self.peak_equity = initial_capital
        self.max_drawdown = 0.0

    def snapshot(self, timestamp: str, equity: float, cash: float,
                 unrealized_pnl: float, open_pos: int) -> None:
        if equity > self.peak_equity:
            self.peak_equity = equity
        drawdown = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0
        self.max_drawdown = max(self.max_drawdown, drawdown)
        self.equity_curve.append({
            "timestamp":     timestamp,
            "equity":        round(equity, 2),
            "cash":          round(cash, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "drawdown":       round(drawdown, 4),
            "open_positions": open_pos,
        })

    def get_series(self, key: str = "equity") -> pd.Series:
        return pd.Series([e[key] for e in self.equity_curve],
                         index=pd.to_datetime([e["timestamp"] for e in self.equity_curve]))


# ──────────────────────────────────────────────────────────────────────────────
# Statistics Calculator
# ──────────────────────────────────────────────────────────────────────────────

class StatsCalculator:
    """Compute performance metrics from closed trades."""

    @classmethod
    def compute(cls, trades: List[TradeLog], initial_capital: float,
                risk_free: float = 0.07) -> Dict:
        if not trades:
            return cls._empty_stats()

        pnls = [t.pnl_net for t in trades]
        gross_pnls = [t.pnl_gross for t in trades]

        wins       = [p for p in pnls if p > 0]
        losses     = [p for p in pnls if p <= 0]
        total      = len(trades)
        win_rate   = len(wins) / total if total else 0.0

        avg_win  = sum(wins) / len(wins)   if wins   else 0.0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
        pf = avg_win / avg_loss if avg_loss > 0 else 0.0

        total_pnl   = sum(pnls)
        total_gross = sum(gross_pnls)
        total_charges = sum(t.total_charges for t in trades)

        # ── Sharpe (daily returns) ─────────────────────────────────────────────
        daily_returns = [t.pnl_net / initial_capital for t in trades]
        avg_ret = sum(daily_returns) / len(daily_returns) if daily_returns else 0
        std_ret = (sum((r - avg_ret) ** 2 for r in daily_returns) / max(len(daily_returns) - 1, 1)) ** 0.5
        sharpe  = (avg_ret / std_ret * (252 ** 0.5)) if std_ret > 0 else 0.0

        # ── Max drawdown ───────────────────────────────────────────────────────
        cum = 0.0
        peak = initial_capital
        max_dd = 0.0
        for t in trades:
            cum += t.pnl_net
            equity = initial_capital + cum
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        avg_trade    = total_pnl / total if total else 0
        avg_duration = sum(t.duration_minutes for t in trades) / total if total else 0
        best_trade   = max(pnls) if pnls else 0
        worst_trade  = min(pnls) if pnls else 0

        return {
            "total_trades":       total,
            "win_rate":           round(win_rate, 4),
            "profit_factor":      round(pf, 2),
            "avg_trade":          round(avg_trade, 2),
            "avg_duration_min":   round(avg_duration, 1),
            "sharpe_ratio":       round(sharpe, 3),
            "max_drawdown_pct":   round(max_dd * 100, 2),
            "total_pnl_net":      round(total_pnl, 2),
            "total_pnl_gross":    round(total_gross, 2),
            "total_charges":      round(total_charges, 2),
            "best_trade":         round(best_trade, 2),
            "worst_trade":        round(worst_trade, 2),
            "win_count":          len(wins),
            "loss_count":         len(losses),
            "initial_capital":    initial_capital,
            "final_equity":       round(initial_capital + total_pnl, 2),
            "equity_return_pct":  round((total_pnl / initial_capital) * 100, 2),
        }

    @classmethod
    def _empty_stats(cls) -> Dict:
        return {
            "total_trades": 0, "win_rate": 0, "profit_factor": 0,
            "avg_trade": 0, "avg_duration_min": 0, "sharpe_ratio": 0,
            "max_drawdown_pct": 0, "total_pnl_net": 0, "total_pnl_gross": 0,
            "total_charges": 0, "best_trade": 0, "worst_trade": 0,
            "win_count": 0, "loss_count": 0, "initial_capital": 0,
            "final_equity": 0, "equity_return_pct": 0,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Scalping Backtest Engine
# ──────────────────────────────────────────────────────────────────────────────

class ScalpingBacktest:
    """
    Reusable backtest engine for options scalping strategies.

    Parameters
    ----------
    initial_capital : float  — starting capital (default Rs.1,00,000)
    lot_size        : int    — contract lot size (default 15 for BANKNIFTY)
    iv              : float  — implied vol for BS pricing (default 22%)
    risk_free       : float  — risk-free rate for BS (default 7%)

    Example
    -------
    >>> bt = ScalpingBacktest(initial_capital=100_000, lot_size=15)
    >>> bt.add_strategy(MyStrategy, name="gap_up")
    >>> results = bt.run(ohlcv_data, timeframe="1m")
    >>> bt.print_stats()
    """

    SUPPORTED_TIMEFRAMES = {"1m", "5m", "15m", "30m", "60m", "1h", "daily"}

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        lot_size: int = 15,
        iv: float = 22.0,
        risk_free: float = 0.07,
    ):
        self.initial_capital = initial_capital
        self.lot_size        = lot_size
        self.iv              = iv
        self.risk_free       = risk_free

        self._brokerage  = BrokerageModel(lot_size=lot_size)
        self._strike_sel = StrikeSelector()

        # Registered strategies: name -> strategy_instance
        self._strategies: Dict[str, ScalpingStrategy] = {}
        self._strategy_names: List[str] = []

        # Per-strategy state
        self._active_positions: Dict[str, List[ActivePosition]] = {}  # name -> positions
        self._closed_trades:    Dict[str, List[TradeLog]]       = {}
        self._equity_recorders: Dict[str, EquityRecorder]        = {}

        # Global cash (shared across strategies to simulate shared capital)
        self._cash = initial_capital

        # Book-keeping
        self._trade_counter = 0
        self._all_trades: List[TradeLog] = []

        # Results cache
        self._results: Dict[str, Any] = {}

    # ── strategy registration ─────────────────────────────────────────────────

    def add_strategy(self, strategy_cls: type, name: str = None,
                     config: dict = None) -> "ScalpingBacktest":
        """
        Register a strategy class with the engine.

        Parameters
        ----------
        strategy_cls : type (subclass of ScalpingStrategy)
        name         : str  — unique identifier for this strategy instance
        config       : dict — passed to strategy __init__

        Returns self for chaining.
        """
        if not issubclass(strategy_cls, ScalpingStrategy):
            raise TypeError(f"{strategy_cls.__name__} must inherit from ScalpingStrategy")

        name = name or strategy_cls.STRATEGY_ID
        if name in self._strategies:
            raise ValueError(f"Strategy '{name}' already registered")

        strategy = strategy_cls(config=config)
        strategy.IV = self.iv
        strategy.RISK_FREE = self.risk_free

        self._strategies[name] = strategy
        self._strategy_names.append(name)
        self._active_positions[name] = []
        self._closed_trades[name]    = []
        self._equity_recorders[name] = EquityRecorder(self.initial_capital)

        logger.info(f"Registered strategy: {name} ({strategy_cls.__name__})")
        return self

    # ── main run loop ──────────────────────────────────────────────────────────

    def run(self, data_feed: List[Dict], timeframe: str = "1m",
            expiry_days: float = 0.5, verbose: bool = False) -> Dict[str, Dict]:
        """
        Run backtest over `data_feed` (list of OHLCV dicts with timestamp).

        Parameters
        ----------
        data_feed   : List[Dict] — each dict has: timestamp, open, high, low, close, volume (optional)
        timeframe  : str         — "1m", "5m", "15m", "30m", "60m"/"1h", "daily"
        expiry_days: float      — days to expiration for BS option pricing (default 0.5 ≈ weekly)
        verbose    : bool       — if True, log every tick (expensive)

        Returns
        -------
        Dict[str, Dict] — keyed by strategy name; each value has:
            stats, trades, equity_curve
        """
        if timeframe not in self.SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe}. "
                              f"Allowed: {self.SUPPORTED_TIMEFRAMES}")

        logger.info(f"Starting backtest — {len(data_feed)} bars, timeframe={timeframe}, "
                    f"strategies={self._strategy_names}")

        # Reset state
        self._cash = self.initial_capital
        self._trade_counter = 0
        self._all_trades = []
        for name in self._strategy_names:
            self._strategies[name].reset()
            self._active_positions[name] = []
            self._closed_trades[name] = []
            self._equity_recorders[name] = EquityRecorder(self.initial_capital)

        # ── main bar loop ───────────────────────────────────────────────────────
        # IMPORTANT: Signals generated at bar i use bar i data.
        # But fill prices use bar (i+1) OPEN price — this is the "next-bar execution"
        # model used by professional platforms like TradeTron.
        # This eliminates look-ahead bias and gives realistic fills.
        for bar_idx in range(len(data_feed) - 1):
            tick         = data_feed[bar_idx]
            next_bar     = data_feed[bar_idx + 1]
            ts           = tick.get("timestamp", "")
            close_price  = tick.get("close", tick.get("ltp", 0))
            next_open    = next_bar.get("open", next_bar.get("close", close_price))

            # Build portfolio state snapshot (shared equity)
            realized  = sum(t.pnl_net for t in self._all_trades)
            unrealized = sum(
                pos.unrealized_pnl(close_price)
                for pos_list in self._active_positions.values()
                for pos in pos_list
            )
            equity    = self._cash + unrealized

            win_count  = sum(1 for t in self._all_trades if t.pnl_net > 0)
            loss_count = sum(1 for t in self._all_trades if t.pnl_net <= 0)

            max_dd = 0.0
            if self._equity_recorders:
                max_dd = max(r.max_drawdown for r in self._equity_recorders.values())

            port_state = PortfolioState(
                equity         = equity,
                cash           = self._cash,
                unrealized_pnl = unrealized,
                realized_pnl   = realized,
                open_positions = sum(len(v) for v in self._active_positions.values()),
                total_trades   = len(self._all_trades),
                win_count      = win_count,
                loss_count     = loss_count,
                max_drawdown_pct = max_dd * 100,
            )

            # ── per strategy processing ────────────────────────────────────────
            for name in self._strategy_names:
                strategy  = self._strategies[name]
                positions = self._active_positions[name]

                # 1. Push tick into strategy for indicator computation
                strategy._push_tick(tick)

                # 2. Check exit signals for all open positions
                # Exit fill price = NEXT bar OPEN (realistic execution)
                self._check_exits(name, bar_idx, tick, next_bar, close_price,
                                  expiry_days, port_state, verbose)

                # 3. Check entry signal if no open position
                # Entry fill price = NEXT bar OPEN (realistic execution)
                if not self._active_positions[name]:
                    entry_sig = strategy.get_entry_signal(tick, {}, port_state)
                    if entry_sig:
                        self._execute_entry(
                            name, strategy, entry_sig, tick,
                            next_open, expiry_days, bar_idx, verbose
                        )

                # 4. Per-bar hook
                strategy.on_bar(tick, port_state)

                # 5. Record equity at bar close
                self._equity_recorders[name].snapshot(
                    ts, equity, self._cash, unrealized,
                    len(self._active_positions[name])
                )

            if verbose and bar_idx % 5000 == 0:
                logger.info(f"Bar {bar_idx}/{len(data_feed)} | Equity: {equity:.2f} | "
                            f"Trades: {len(self._all_trades)}")

        # ── square off any remaining positions at last close ──────────────────
        # Use last bar OPEN for square-off fill (consistent with next-bar execution model)
        last_tick  = data_feed[-1] if data_feed else {}
        last_open  = last_tick.get("open", last_tick.get("close", 0))
        last_ts    = last_tick.get("timestamp", "")

        for name in self._strategy_names:
            for pos in list(self._active_positions[name]):
                self._close_position(
                    name, pos, last_open, last_ts, expiry_days,
                    "EOD square-off", len(data_feed), verbose
                )

        # ── compute stats ────────────────────────────────────────────────────
        results = {}
        for name in self._strategy_names:
            trades = self._closed_trades[name]
            stats  = StatsCalculator.compute(trades, self.initial_capital, self.risk_free)
            self._results[name] = {
                "stats":         stats,
                "trades":        trades,
                "equity_curve":  self._equity_recorders[name].equity_curve,
            }

        self._results["_all"] = {
            "stats":        StatsCalculator.compute(self._all_trades, self.initial_capital, self.risk_free),
            "trades":       self._all_trades,
            "equity_curve": (pd.DataFrame([
                {"timestamp": e["timestamp"], "equity": e["equity"]}
                for e in self._equity_recorders[self._strategy_names[0]].equity_curve
                if self._strategy_names
            ]) if self._strategy_names else pd.DataFrame()),
        }

        logger.info(f"Backtest complete — {len(self._all_trades)} total trades")
        return self._results

    # ── entry / exit execution ─────────────────────────────────────────────────

    def _execute_entry(
        self, name: str, strategy: ScalpingStrategy,
        signal: dict, tick: Dict,
        close_price: float, expiry_days: float,
        bar_idx: int, verbose: bool,
    ) -> None:
        """Execute entry order from signal."""
        action      = signal.get("action", "BUY")
        strike      = signal.get("strike", 0)
        opt_type    = signal.get("option_type", "CE")
        lots        = signal.get("lots", 1)
        reason      = signal.get("reason", "")
        confidence  = signal.get("confidence", 0.0)
        instrument  = signal.get("instrument", strategy.INSTRUMENT)

        # Auto ATM strike if not specified
        if strike == 0:
            strike = StrikeSelector.get_atm_strike(close_price, instrument)

        # Compute option price via Black-Scholes
        opt_price = StrikeSelector.get_option_price(
            close_price, strike, expiry_days, opt_type, self.iv, self.risk_free
        )
        opt_price = self._brokerage.round_lot(opt_price)
        if opt_price < 1.0:
            opt_price = 1.0  # floor at Rs.1

        # Apply slippage
        fill_price = self._brokerage.apply_slippage(opt_price, action)

        # Compute charges (BUY side)
        charges = self._brokerage.calculate_charges(fill_price, lots, action)

        # Margin check
        margin_needed = fill_price * lots * self.lot_size * 0.20
        if self._cash < margin_needed:
            logger.warning(f"[{name}] Insufficient margin {self._cash:.2f} < {margin_needed:.2f} — skipped")
            return

        # Deduct margin + charges from cash
        self._cash -= (margin_needed + charges.total)

        self._trade_counter += 1
        pos_id = f"T{self._trade_counter:05d}_{name}"

        pos = ActivePosition(
            position_id   = pos_id,
            strategy_id   = name,
            instrument    = instrument,
            option_type   = opt_type,
            strike        = strike,
            side          = action,
            lots          = lots,
            entry_price   = fill_price,
            entry_time    = tick.get("timestamp", ""),
            entry_charges = charges,
            entry_tick    = bar_idx,
            confidence    = confidence,
            reason        = reason,
        )
        self._active_positions[name].append(pos)

        if verbose:
            logger.info(f"[{name}] ENTER {action} {lots}L {opt_type} @{strike} → "
                        f"fill Rs.{fill_price:.2f} | charges Rs.{charges.total:.2f} | {reason}")

    def _check_exits(
        self, name: str, bar_idx: int,
        tick: Dict, next_bar: Dict, close_price: float,
        expiry_days: float, port_state: PortfolioState,
        verbose: bool,
    ) -> None:
        """Check exit signals for all open positions of a strategy.

        Exit fill price = next bar OPEN (realistic execution, no look-ahead bias).
        If next_bar is unavailable (last bar), use current close as fallback.
        """
        strategy  = self._strategies[name]
        positions = self._active_positions[name]

        # Exit fill price = next bar open (or close if last bar)
        exit_fill_price = next_bar.get("open", next_bar.get("close", close_price)) if next_bar else close_price

        for pos in list(positions):
            # Current option price (for PnL tracking) = current bar close
            current_opt_price = StrikeSelector.get_option_price(
                close_price, pos.strike, expiry_days, pos.option_type, self.iv, self.risk_free
            )

            # Build position dict for strategy
            pos_dict = {
                "position_id":   pos.position_id,
                "strike":        pos.strike,
                "option_type":   pos.option_type,
                "side":          pos.side,
                "lots":          pos.lots,
                "entry_price":   pos.entry_price,
                "entry_time":    pos.entry_time,
                "entry_tick":    pos.entry_tick,
                "current_price": current_opt_price,
                "unrealized_pnl": pos.unrealized_pnl(current_opt_price),
            }

            exit_sig = strategy.get_exit_signal(tick, pos_dict, port_state)

            if exit_sig and exit_sig.get("should_exit", False):
                # Use next bar OPEN for fill price (realistic execution, no look-ahead)
                exit_price = self._brokerage.apply_slippage(
                    self._brokerage.round_lot(exit_fill_price),
                    "SELL" if pos.side == "BUY" else "BUY"
                )
                self._close_position(
                    name, pos, exit_price, tick.get("timestamp", ""),
                    expiry_days, exit_sig.get("reason", "signal"), bar_idx, verbose
                )

    def _close_position(
        self, name: str, pos: ActivePosition,
        exit_price: float, exit_ts: str,
        expiry_days: float, exit_reason: str,
        bar_idx: int, verbose: bool,
    ) -> None:
        """Close a position and record the trade."""
        # Sell side charges
        charges_sell = self._brokerage.calculate_charges(exit_price, pos.lots, "SELL")

        # P&L
        mult  = 1 if pos.side == "BUY" else -1
        gross = mult * (exit_price - pos.entry_price) * pos.lots * self.lot_size
        net   = gross - pos.entry_charges.total - charges_sell.total

        # Release margin + net P&L
        margin_release = pos.entry_price * pos.lots * self.lot_size * 0.20
        self._cash += margin_release + net

        # Duration
        try:
            edt = datetime.fromisoformat(pos.entry_time.replace("Z", "+00:00"))
            xdt = datetime.fromisoformat(exit_ts.replace("Z", "+00:00"))
            dur = (xdt - edt).total_seconds() / 60
        except Exception:
            dur = 0.0

        self._trade_counter += 1
        trade = TradeLog(
            trade_id        = f"T{self._trade_counter:05d}_{name}",
            strategy_id     = name,
            instrument      = pos.instrument,
            option_type     = pos.option_type,
            strike          = pos.strike,
            side            = pos.side,
            entry_time      = pos.entry_time,
            exit_time       = exit_ts,
            duration_minutes = round(dur, 2),
            lots            = pos.lots,
            entry_price     = pos.entry_price,
            exit_price      = exit_price,
            pnl_gross       = round(gross, 2),
            pnl_net         = round(net, 2),
            brokerage       = round(pos.entry_charges.brokerage + charges_sell.brokerage, 2),
            gst             = round(pos.entry_charges.gst + charges_sell.gst, 2),
            stt             = round(pos.entry_charges.stt + charges_sell.stt, 2),
            sebi            = round(pos.entry_charges.sebi + charges_sell.sebi, 2),
            stamp_duty      = round(pos.entry_charges.stamp_duty + charges_sell.stamp_duty, 2),
            total_charges   = round(pos.entry_charges.total + charges_sell.total, 2),
            exit_reason     = exit_reason,
            confidence      = pos.confidence,
            equity_at_entry = self.initial_capital + sum(t.pnl_net for t in self._all_trades),
            equity_at_exit  = 0.0,  # filled below
        )
        trade.equity_at_exit = trade.equity_at_entry + net

        self._all_trades.append(trade)
        self._closed_trades[name].append(trade)
        self._active_positions[name].remove(pos)

        if verbose:
            logger.info(f"[{name}] EXIT {pos.side} {pos.lots}L {pos.option_type} "
                        f"@{pos.strike} → exit Rs.{exit_price:.2f} | P&L Rs.{net:.2f} | {exit_reason}")

    # ── results helpers ────────────────────────────────────────────────────────

    def get_stats(self, name: str = "_all") -> Dict:
        """Return statistics dict for a strategy or all strategies combined."""
        return self._results.get(name, {}).get("stats", StatsCalculator._empty_stats())

    def get_trades(self, name: str = "_all") -> List[TradeLog]:
        """Return list of TradeLog objects."""
        return self._results.get(name, {}).get("trades", [])

    def get_equity_curve(self, name: str = "_all") -> pd.DataFrame:
        """Return equity curve as DataFrame."""
        ec = self._results.get(name, {}).get("equity_curve", [])
        if isinstance(ec, pd.DataFrame):
            return ec
        return pd.DataFrame(ec)

    def print_stats(self, name: str = "_all") -> None:
        """Print formatted statistics to console."""
        stats = self.get_stats(name)
        trades = self.get_trades(name)

        print("\n" + "=" * 65)
        print(f"  BACKTEST RESULTS — {name.upper()}")
        print("=" * 65)
        print(f"  Initial Capital   : Rs.{self.initial_capital:>12,.2f}")
        print(f"  Final Equity     : Rs.{stats.get('final_equity', 0):>12,.2f}")
        print(f"  Net P&L          : Rs.{stats.get('total_pnl_net', 0):>12,.2f} "
              f"({stats.get('equity_return_pct', 0):+.2f}%)")
        print(f"  Gross P&L        : Rs.{stats.get('total_pnl_gross', 0):>12,.2f}")
        print(f"  Total Charges    : Rs.{stats.get('total_charges', 0):>12,.2f}")
        print("-" * 65)
        print(f"  Total Trades     : {stats.get('total_trades', 0):>12}")
        print(f"  Win Rate         : {stats.get('win_rate', 0)*100:>11.2f}%")
        print(f"  Win Count        : {stats.get('win_count', 0):>12}  |  Loss Count: {stats.get('loss_count', 0)}")
        print(f"  Profit Factor    : {stats.get('profit_factor', 0):>12.2f}")
        print(f"  Avg Trade        : Rs.{stats.get('avg_trade', 0):>12,.2f}")
        print(f"  Best Trade       : Rs.{stats.get('best_trade', 0):>12,.2f}  |  Worst Trade: Rs.{stats.get('worst_trade', 0):,.2f}")
        print(f"  Avg Duration     : {stats.get('avg_duration_min', 0):>11.1f} min")
        print("-" * 65)
        print(f"  Sharpe Ratio     : {stats.get('sharpe_ratio', 0):>12.3f}")
        print(f"  Max Drawdown     : {stats.get('max_drawdown_pct', 0):>11.2f}%")
        print("=" * 65)

        # ── per-strategy breakdown ───────────────────────────────────────────────
        if name == "_all" and len(self._strategy_names) > 1:
            for sname in self._strategy_names:
                s = self.get_stats(sname)
                print(f"\n  [{sname}]  Trades={s['total_trades']}  "
                      f"WR={s['win_rate']*100:.1f}%  "
                      f"P&L=Rs.{s['total_pnl_net']:,.0f}  "
                      f"Sharpe={s['sharpe_ratio']:.2f}  "
                      f"MaxDD={s['max_drawdown_pct']:.2f}%")

    def plot_equity(self, name: str = "_all") -> None:
        """Plot equity curve using matplotlib."""
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            logger.warning("matplotlib not available — skipping plot")
            return

        ec = self.get_equity_curve(name)
        if ec.empty:
            logger.warning("No equity curve data to plot")
            return

        ts = pd.to_datetime(ec["timestamp"])
        equity = ec["equity"]

        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(ts, equity, label="Equity", color="navy")
        ax.fill_between(ts, self.initial_capital, equity,
                        where=(equity >= self.initial_capital),
                        color="green", alpha=0.2)
        ax.fill_between(ts, self.initial_capital, equity,
                        where=(equity < self.initial_capital),
                        color="red", alpha=0.2)
        ax.axhline(self.initial_capital, color="black", linestyle="--", linewidth=0.8)
        ax.set_title(f"Equity Curve — {name.upper()}")
        ax.set_xlabel("Time")
        ax.set_ylabel("Equity (Rs.)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()

    def export_trades(self, path: str = "trades_export.csv", name: str = "_all") -> None:
        """Export trades to CSV."""
        trades = self.get_trades(name)
        if not trades:
            logger.warning("No trades to export")
            return

        rows = []
        for t in trades:
            rows.append({
                "trade_id":        t.trade_id,
                "strategy_id":     t.strategy_id,
                "instrument":      t.instrument,
                "option_type":     t.option_type,
                "strike":          t.strike,
                "side":            t.side,
                "entry_time":      t.entry_time,
                "exit_time":       t.exit_time,
                "duration_min":    t.duration_minutes,
                "lots":            t.lots,
                "entry_price":     t.entry_price,
                "exit_price":      t.exit_price,
                "pnl_gross":       t.pnl_gross,
                "pnl_net":         t.pnl_net,
                "brokerage":       t.brokerage,
                "gst":             t.gst,
                "stt":             t.stt,
                "sebi":            t.sebi,
                "stamp_duty":      t.stamp_duty,
                "total_charges":   t.total_charges,
                "exit_reason":     t.exit_reason,
                "confidence":      t.confidence,
                "equity_at_entry": t.equity_at_entry,
                "equity_at_exit":  t.equity_at_exit,
            })

        df = pd.DataFrame(rows)
        df.to_csv(path, index=False)
        logger.info(f"Exported {len(rows)} trades to {path}")


# ──────────────────────────────────────────────────────────────────────────────
# Demo / Reference Implementations
# ──────────────────────────────────────────────────────────────────────────────

class BANKNIFTY_Momentum_Strategy(ScalpingStrategy):
    """
    BANKNIFTY ATM options momentum breakout.
    Entry: BUY CE when price > SMA20 AND RSI(14) > 62; BUY PE when price < SMA20 AND RSI(14) < 38
    Exit:  50% profit | -30% stop | 60-tick time exit
    Confidence threshold: >= 0.60
    """
    STRATEGY_ID = "bn_momentum"
    APPROACH_ID = "approach_A"
    INSTRUMENT  = "BANKNIFTY"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.sma_period   = self.config.get("sma_period", 20)
        self.rsi_period   = self.config.get("rsi_period", 14)
        self.conf_thresh  = self.config.get("confidence_threshold", 0.60)
        self.profit_target = self.config.get("profit_target", 0.50)
        self.stop_loss    = self.config.get("stop_loss", -0.30)
        self.max_ticks    = self.config.get("max_ticks", 60)

    @staticmethod
    def _sma(closes: pd.Series, n: int) -> float:
        return closes.iloc[-n:].mean() if len(closes) >= n else closes.mean()

    @staticmethod
    def _rsi(closes: pd.Series, n: int = 14) -> float:
        if len(closes) < n + 1:
            return 50.0
        deltas = closes.diff()
        gains = deltas.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
        losses = (-deltas.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
        rs = gains / losses.replace(0, 0.0001)
        return (100 - (100 / (1 + rs))).iloc[-1]

    def get_entry_signal(self, tick: dict, position: dict, portfolio: PortfolioState) -> Optional[dict]:
        if len(self._price_history) < self.sma_period:
            return None

        closes = self._closes()
        price  = closes.iloc[-1]
        sma20  = self._sma(closes, self.sma_period)
        rsi14  = self._rsi(closes, self.rsi_period)

        if price > sma20 and rsi14 > 62:
            return {
                "action":      "BUY",
                "strike":      0,  # ATM auto
                "option_type": "CE",
                "lots":        1,
                "reason":      f"RSI={rsi14:.1f} > 62, price>{sma20:.0f}",
                "confidence":  0.60,
            }
        if price < sma20 and rsi14 < 38:
            return {
                "action":      "BUY",
                "strike":      0,
                "option_type": "PE",
                "lots":        1,
                "reason":      f"RSI={rsi14:.1f} < 38, price<{sma20:.0f}",
                "confidence":  0.60,
            }
        return None

    def get_exit_signal(self, tick: dict, position: dict, portfolio: PortfolioState) -> dict:
        entry_price  = position.get("entry_price", 0)
        entry_opt_p = position.get("entry_opt_price", entry_price)
        entry_tick  = position.get("entry_tick", 0)
        current_tick = self._tick_count
        ticks_elapsed = current_tick - entry_tick

        opt_type = position.get("option_type", "CE")
        strike   = position.get("strike", 0)
        close_p  = tick.get("close", tick.get("ltp", entry_price))

        current_opt_p = StrikeSelector.get_option_price(
            close_p, strike, 0.5, opt_type, self.IV, self.RISK_FREE
        )

        if entry_opt_p > 0:
            pnl_pct = (current_opt_p - entry_opt_p) / entry_opt_p
        else:
            pnl_pct = 0.0

        if pnl_pct >= self.profit_target:
            return {"should_exit": True, "reason": "50% profit target", "exit_price": current_opt_p}
        if pnl_pct <= self.stop_loss:
            return {"should_exit": True, "reason": "30% stop loss",    "exit_price": current_opt_p}
        if ticks_elapsed > self.max_ticks and pnl_pct < 0.10:
            return {"should_exit": True, "reason": "60-tick time exit", "exit_price": current_opt_p}

        return {"should_exit": False}


class Nifty50_Scalp_Strategy(ScalpingStrategy):
    """
    Nifty 50 OTM options scalping with tight TP/SL.
    Uses 50-step OTM strikes, 15% profit target, 10% stop loss, max 20 ticks.
    """
    STRATEGY_ID = "nifty50_scalp"
    APPROACH_ID = "approach_A"
    INSTRUMENT  = "NIFTY50"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.otm_delta    = self.config.get("otm_delta", -2)   # -2 = 2 steps OTM
        self.profit_pct   = self.config.get("profit_pct", 0.15)   # 15% TP
        self.stop_pct     = self.config.get("stop_pct", -0.10)    # 10% SL
        self.max_ticks    = self.config.get("max_ticks", 20)
        self.rsi_period   = self.config.get("rsi_period", 9)
        self.conf_thresh  = self.config.get("confidence_threshold", 0.65)

    @staticmethod
    def _rsi(closes: pd.Series, n: int = 9) -> float:
        if len(closes) < n + 1:
            return 50.0
        deltas = closes.diff()
        gains = deltas.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
        losses = (-deltas.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
        rs = gains / losses.replace(0, 0.0001)
        return (100 - (100 / (1 + rs))).iloc[-1]

    def get_entry_signal(self, tick: dict, position: dict, portfolio: PortfolioState) -> Optional[dict]:
        if len(self._price_history) < 20:
            return None

        closes = self._closes()
        price  = closes.iloc[-1]
        rsi9   = self._rsi(closes, self.rsi_period)

        # Long on RSI bounce from oversold
        if rsi9 < 35:
            strike = StrikeSelector.get_otm_strike(price, self.otm_delta, "NIFTY50")
            return {
                "action":      "BUY",
                "strike":      strike,
                "option_type": "CE",
                "lots":        1,
                "reason":      f"RSI9={rsi9:.1f} oversold bounce",
                "confidence":  self.conf_thresh,
            }
        # Short on RSI drop from overbought
        if rsi9 > 65:
            strike = StrikeSelector.get_otm_strike(price, abs(self.otm_delta), "NIFTY50")
            return {
                "action":      "BUY",
                "strike":      strike,
                "option_type": "PE",
                "lots":        1,
                "reason":      f"RSI9={rsi9:.1f} overbought drop",
                "confidence":  self.conf_thresh,
            }
        return None

    def get_exit_signal(self, tick: dict, position: dict, portfolio: PortfolioState) -> dict:
        entry_price = position.get("entry_price", 0)
        entry_tick  = position.get("entry_tick", 0)
        ticks_el    = self._tick_count - entry_tick
        opt_type    = position.get("option_type", "CE")
        strike      = position.get("strike", 0)
        close_p     = tick.get("close", tick.get("ltp", entry_price))

        current_opt_p = StrikeSelector.get_option_price(close_p, strike, 0.5, opt_type, self.IV, self.RISK_FREE)

        pnl_pct = (current_opt_p - entry_price) / entry_price if entry_price > 0 else 0.0

        if pnl_pct >= self.profit_pct:
            return {"should_exit": True, "reason": "15% profit target", "exit_price": current_opt_p}
        if pnl_pct <= self.stop_pct:
            return {"should_exit": True, "reason": "10% stop loss",    "exit_price": current_opt_p}
        if ticks_el > self.max_ticks:
            return {"should_exit": True, "reason": "20-tick time exit", "exit_price": current_opt_p}

        return {"should_exit": False}


# ──────────────────────────────────────────────────────────────────────────────
# Data Generator (synthetic OHLCV for testing)
# ──────────────────────────────────────────────────────────────────────────────

def generate_synthetic_feed(
    n_bars: int = 500,
    start_price: float = 52000,
    start_ts: str = "2026-05-01 09:15:00",
    timeframe: str = "1m",
    volatility: float = 0.0015,
    seed: int = 42,
) -> List[Dict]:
    """
    Generate synthetic OHLCV candles for backtest demonstration.

    Parameters
    ----------
    n_bars      : int    — number of candles
    start_price : float  — starting spot price
    start_ts    : str    — ISO timestamp of first candle
    timeframe   : str    — "1m", "5m", etc.
    volatility  : float  — per-bar return std dev
    seed        : int    — random seed for reproducibility
    """
    import random
    random.seed(seed)
    np.random.seed(seed)

    df_freq = {"1m": "1min", "5m": "5min", "15m": "15min",
               "30m": "30min", "60m": "1h", "1h": "1h", "daily": "1D"}[timeframe]

    timestamps = pd.date_range(start=start_ts, periods=n_bars, freq=df_freq)

    price = start_price
    data  = []
    for ts in timestamps:
        open_p  = price * (1 + np.random.uniform(-0.0005, 0.0005))
        high_p  = max(open_p, price) * (1 + abs(np.random.uniform(0, volatility)))
        low_p   = min(open_p, price) * (1 - abs(np.random.uniform(0, volatility)))
        close_p = price * (1 + np.random.uniform(-volatility, volatility))
        volume  = int(np.random.uniform(800_000, 2_000_000))

        data.append({
            "timestamp": ts.isoformat(),
            "open":      round(open_p, 2),
            "high":      round(high_p, 2),
            "low":       round(low_p, 2),
            "close":     round(close_p, 2),
            "volume":    volume,
        })
        price = close_p

    return data


# ──────────────────────────────────────────────────────────────────────────────
# Usage Example
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Generating synthetic feed...")
    feed = generate_synthetic_feed(n_bars=2000, start_price=52000, volatility=0.002)

    bt = ScalpingBacktest(initial_capital=100_000, lot_size=15, iv=22.0)

    # BANKNIFTY momentum strategy
    bt.add_strategy(BANKNIFTY_Momentum_Strategy, name="bn_momentum")

    # Nifty50 scalping strategy
    bt.add_strategy(Nifty50_Scalp_Strategy, name="nifty50_scalp")

    results = bt.run(feed, timeframe="1m", expiry_days=0.5, verbose=False)

    bt.print_stats("_all")
    # bt.plot_equity("_all")
    # bt.export_trades("trades_export.csv", "_all")

    print("\nPer-strategy breakdown:")
    for name in bt._strategy_names:
        bt.print_stats(name)
