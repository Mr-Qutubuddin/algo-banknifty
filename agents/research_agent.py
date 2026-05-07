"""
ResearchAgent — Strategy research, hypothesis formation, and approach development.
Implements and documents all trading strategies with multiple approaches.
"""
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import json

BASE_DIR = Path(__file__).parent.parent.parent
STRATEGIES_DIR = BASE_DIR / "strategies" / "research"
JOURNAL_STRATEGIES_DIR = BASE_DIR / "journal" / "strategies"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent.parent / 'logs' / 'research_agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ResearchAgent:
    """Develops and documents trading strategies."""

    STRATEGIES = [
        {
            "id": "strategy_001",
            "name": "Iron Condor / Iron Fly Variants",
            "approaches": [
                {
                    "id": "approach_A",
                    "name": "ATM Iron Fly with fixed expiry (weekly)",
                    "hypothesis": "Selling ATM straddle at weekly expiry and hedging delta exposure produces consistent theta decay capture with bounded risk.",
                    "entry_rules": [
                        "Enter at 9:30 AM IST on expiry week (Wednesday)",
                        "Sell ATM CE and ATM PE of same expiry",
                        "Width: nearest 200-point strike from ATM"
                    ],
                    "exit_rules": [
                        "Exit when P&L > 70% of max profit",
                        "Exit when P&L < -50% of max loss",
                        "Force exit at 3:20 PM IST on expiry day"
                    ],
                    "risk_rules": [
                        "Max loss per trade: ₹5000",
                        "Stop loss: 2x premium received",
                        "No new positions if daily loss > ₹8000"
                    ],
                    "indicators": ["ATM strike selection", "IV rank", "Time to expiry < 2 days"],
                    "expected_market": "Low volatility, range-bound market",
                    "failure_market": "Truncated range, sudden gap opens"
                },
                {
                    "id": "approach_B",
                    "name": "Dynamic wing adjustment based on IV percentile",
                    "hypothesis": "IV percentile signal dynamically adjusts wing width — wider wings in high IV environment captures more premium.",
                    "entry_rules": [
                        "IV Percentile > 70: wider IC, 400-point wings",
                        "IV Percentile 40-70: standard 200-point wings",
                        "IV Percentile < 40: tighter IC, 100-point wings"
                    ],
                    "exit_rules": [
                        "Take profit at 75% of premium collected",
                        "Hold through expiry unless IV percentile < 20"
                    ],
                    "risk_rules": [
                        "Dynamic stop based on IV shift",
                        "Delta-neutral rebalancing every 15 mins"
                    ],
                    "indicators": ["IV percentile", "VIX", "ATM straddle width"],
                    "expected_market": "High volatility environment",
                    "failure_market": "Low volatility, sharp directional moves"
                },
                {
                    "id": "approach_C",
                    "name": "OI-weighted strike selection",
                    "hypothesis": "Selecting strikes with highest OI buildup indicates institutional support/resistance — using these as wings improves edge.",
                    "entry_rules": [
                        "Scan top 3 strikes by OI buildup in CE and PE",
                        "Sell strangle using top CE OI + top PE OI strikes",
                        "Minimum OI: 50000 for selection"
                    ],
                    "exit_rules": [
                        "Exit if OI starts unwinding (>20% drop in 15 min)",
                        "Profit target: 60% of premium"
                    ],
                    "risk_rules": [
                        "Max loss: 3x initial premium",
                        "Width of strangle based on OI concentration"
                    ],
                    "indicators": ["OI buildup", "OI unwinding", "Strike concentration"],
                    "expected_market": "Trending with institutional involvement",
                    "failure_market": "Low volume, no clear OI support"
                }
            ]
        },
        {
            "id": "strategy_002",
            "name": "Momentum-Based Directional Options",
            "approaches": [
                {
                    "id": "approach_A",
                    "name": "9:15 gap strategy with calls/puts",
                    "hypothesis": "BankNifty frequently gaps at open — buying options in gap direction captures the fill move.",
                    "entry_rules": [
                        "Calculate overnight gap % from previous close",
                        "If gap > 0.75% (up or down):",
                        "Buy ATM CE for gap-up, ATM PE for gap-down",
                        "Entry time: 9:20 AM IST"
                    ],
                    "exit_rules": [
                        "Exit if price moves 0.5% in opposite direction",
                        "Profit target: 2x option premium",
                        "Stop loss: 50% of premium"
                    ],
                    "risk_rules": [
                        "Max loss per trade: ₹3000",
                        "Position sizing: not more than 20% of margin"
                    ],
                    "indicators": ["Gap size", "Opening price", "Previous close"],
                    "expected_market": "Strong overnight cues (global markets, FII flows)",
                    "failure_market": "Gap fill immediately, range-bound open"
                },
                {
                    "id": "approach_B",
                    "name": "5-min VWAP breakout with momentum filter",
                    "hypothesis": "VWAP breakout with high RSI (>60 or <40) filter identifies high-probability momentum trades.",
                    "entry_rules": [
                        "Wait for 9:30 AM IST candle to close",
                        "If close > VWAP + 0.5% and RSI(14) > 55: buy CE",
                        "If close < VWAP - 0.5% and RSI(14) < 45: buy PE"
                    ],
                    "exit_rules": [
                        "Exit on first candle close below VWAP",
                        "Profit target: 1.5x premium",
                        "Time stop: 11:00 AM IST"
                    ],
                    "risk_rules": [
                        "Max loss: 40% of premium",
                        "Only trade if volume > 1.5x 20-day avg"
                    ],
                    "indicators": ["VWAP", "RSI(14)", "Volume ratio", "5-min momentum"],
                    "expected_market": "Trending morning with clear direction",
                    "failure_market": "Choppy, low volume morning"
                },
                {
                    "id": "approach_C",
                    "name": "Opening Range Breakout (ORB) with options",
                    "hypothesis": "First 15-minute range breakout signals continuation — options amplify the move.",
                    "entry_rules": [
                        "Define 9:15-9:30 AM IST as opening range",
                        "Breakout: price > high of range + 0.3% for CE",
                        "Breakout: price < low of range - 0.3% for PE"
                    ],
                    "exit_rules": [
                        "Exit when price returns inside range",
                        "Profit target: 3x option premium",
                        "Time stop: 12:00 PM IST"
                    ],
                    "risk_rules": [
                        "Max loss: 100% of premium (let it expire if no stop-out)",
                        "Position: max 2 lots"
                    ],
                    "indicators": ["Opening range high/low", "15-min candle close", "Momentum"],
                    "expected_market": "Strong trending morning",
                    "failure_market": "Range-bound day, false breakouts"
                }
            ]
        },
        {
            "id": "strategy_003",
            "name": "Mean Reversion Strategies",
            "approaches": [
                {
                    "id": "approach_A",
                    "name": "BB squeeze with straddle entry",
                    "hypothesis": "Bollinger Band squeeze indicates low volatility — playing the expansion with long straddle captures the move.",
                    "entry_rules": [
                        "BB width < 20% of 20-period SMA",
                        "Wait for squeeze to release (BB width > 50% of SMA)",
                        "Buy straddle at breakout candle close"
                    ],
                    "exit_rules": [
                        "Exit if straddle profit > 100% of premium",
                        "Hold max 2 hours",
                        "Stop if move is < 0.5% after 45 mins"
                    ],
                    "risk_rules": [
                        "Max loss: 50% of premium",
                        "Only trade if ATR > 100"
                    ],
                    "indicators": ["Bollinger Band width", "ATR", "Squeeze release"],
                    "expected_market": "Low volatility periods, before news/events",
                    "failure_market": "Squeeze continues, no expansion"
                },
                {
                    "id": "approach_B",
                    "name": "IV rank-based premium selling",
                    "hypothesis": "High IV rank indicates option premiums are elevated — selling these captures mean-reversion to lower IV.",
                    "entry_rules": [
                        "IV rank > 70: sell far OTM strangle",
                        "IV rank < 30: avoid premium selling",
                        "Exit when IV rank < 40"
                    ],
                    "exit_rules": [
                        "Profit target: 70% of premium",
                        "Stop if IV rank > 85",
                        "Max hold: 4 days"
                    ],
                    "risk_rules": [
                        "Max loss: 2x premium received",
                        "Delta hedge if position delta > 0.3"
                    ],
                    "indicators": ["IV rank", "IV percentile", "Strangle width"],
                    "expected_market": "Post-earnings, post-event high IV",
                    "failure_market": "IV continues to rise, sharp directional move"
                },
                {
                    "id": "approach_C",
                    "name": "Delta-neutral adjustment strategy",
                    "hypothesis": "Maintaining delta-neutral position in volatile market captures mean-reversion while being market-direction agnostic.",
                    "entry_rules": [
                        "Entry when delta imbalance > 0.2",
                        "Sell the side with higher delta",
                        "Use 15-min rebalancing intervals"
                    ],
                    "exit_rules": [
                        "Exit when delta neutral again",
                        "Stop if position moves > ₹2000 against"
                    ],
                    "risk_rules": [
                        "Max position delta: ±0.3",
                        "Max notional: ₹200000"
                    ],
                    "indicators": ["Position delta", "Gamma", "Theta decay"],
                    "expected_market": "Range-bound with oscillating direction",
                    "failure_market": "Strong trending, delta keeps piling"
                }
            ]
        },
        {
            "id": "strategy_004",
            "name": "Event-Based Strategies",
            "approaches": [
                {
                    "id": "approach_A",
                    "name": "Expiry day theta decay (sell on Wednesday AM)",
                    "hypothesis": "Theta decay accelerates exponentially on expiry day — selling options Wednesday captures maximum time value erosion.",
                    "entry_rules": [
                        "Wednesday 10:00-11:00 AM IST: sell OTM straddle",
                        "Strike selection: 1.5-2% OTM",
                        "Collect minimum premium: ₹80"
                    ],
                    "exit_rules": [
                        "Buy back same day 2:30-3:00 PM IST",
                        "Profit target: 60% of premium",
                        "Stop loss: 80% of premium"
                    ],
                    "risk_rules": [
                        "Max loss: ₹3000 per trade",
                        "Only trade if expiry > 2 hours away"
                    ],
                    "indicators": ["Time to expiry", "ATM straddle width", "Theta decay rate"],
                    "expected_market": "Range-bound expiry day",
                    "failure_market": "Large directional move, gap through strikes"
                },
                {
                    "id": "approach_B",
                    "name": "Pre-event (RBI/Budget/results) volatility plays",
                    "hypothesis": "Pre-event IV spike creates overpriced options — selling straddle before event captures IV crush after.",
                    "entry_rules": [
                        "Enter 2 days before scheduled event",
                        "Sell ATM straddle",
                        "Minimum 5 trading days to expiry"
                    ],
                    "exit_rules": [
                        "Exit same day as event results",
                        "Profit target: 50% of premium",
                        "Stop if IV rises >20%"
                    ],
                    "risk_rules": [
                        "Max loss: 2x premium received",
                        "Hedge with far OTM strangle if IV > 30%"
                    ],
                    "indicators": ["IV before event", "Historical IV crush %", "Event type"],
                    "expected_market": "Pre-budget, pre-RBI, pre-results",
                    "failure_market": "Black swan event, massive gap"
                },
                {
                    "id": "approach_C",
                    "name": "Weekly expiry rollover arbitrage",
                    "hypothesis": "Price divergence between weekly and monthly expiry creates rollover opportunity — capture the difference.",
                    "entry_rules": [
                        "Detect >1% price difference between weekly and monthly ATM",
                        "Buy cheaper, sell expensive",
                        "Hold until Thursday expiry rollover"
                    ],
                    "exit_rules": [
                        "Exit Friday 3:00 PM IST",
                        "Profit target: 50% of divergence",
                        "Stop loss: 30% of divergence"
                    ],
                    "risk_rules": [
                        "Max loss: ₹2000 per leg",
                        "Use only for ATM strikes"
                    ],
                    "indicators": ["Expiry calendar", "Same-strike premium difference", "Volume"],
                    "expected_market": "Rollover days (Thursday/Friday)",
                    "failure_market": "No divergence, convergence trap"
                }
            ]
        },
        {
            "id": "strategy_005",
            "name": "Greeks-Based Strategies",
            "approaches": [
                {
                    "id": "approach_A",
                    "name": "Gamma scalping near ATM",
                    "hypothesis": "Near ATM options have highest gamma — rapid delta hedging captures the oscillation profit.",
                    "entry_rules": [
                        "Be long 1000 shares equivalent delta via options",
                        "Scalp when delta moves >0.15",
                        "Rebalance every 5 mins or when P&L changes ₹500"
                    ],
                    "exit_rules": [
                        "Exit when time value drops 50%",
                        "Stop if theta loss > gamma profit for 30 mins"
                    ],
                    "risk_rules": [
                        "Max daily scalping loss: ₹3000",
                        "Gamma exposure: max 0.5"
                    ],
                    "indicators": ["Gamma", "Delta", "Theta decay rate", "Realized vol"],
                    "expected_market": "High gamma, oscillating near ATM",
                    "failure_market": "Strong trending, gamma becomes liability"
                },
                {
                    "id": "approach_B",
                    "name": "Vega-neutral spread construction",
                    "hypothesis": "Long vega + short vega at different strikes creates vega-neutral spread profiting from vol of vol.",
                    "entry_rules": [
                        "Long 1 ATM straddle, short 2 OTM straddles",
                        "Net vega ≈ 0",
                        "Adjust if vega drifts >0.05"
                    ],
                    "exit_rules": [
                        "Exit when vol curve normalizes",
                        "Hold max 5 days",
                        "Profit target: 40% of max loss"
                    ],
                    "risk_rules": [
                        "Max loss: ₹5000",
                        "Vega limit: ±0.1"
                    ],
                    "indicators": ["Vega", "Volatility skew", "VIX term structure"],
                    "expected_market": "High vol environment, steep skew",
                    "failure_market": "Vol collapse, skew flattens"
                },
                {
                    "id": "approach_C",
                    "name": "Delta hedging with dynamic rebalancing",
                    "hypothesis": "Maintaining zero delta through dynamic rebalancing profits from mean-reversion of the underlying.",
                    "entry_rules": [
                        "Long 1 ATM straddle",
                        "Rebalance delta to zero when it exceeds ±0.15",
                        "Rebalance frequency: every 10 mins"
                    ],
                    "exit_rules": [
                        "Exit when straddle profit > 50%",
                        "Stop if rebalancing cost > 30% of premium"
                    ],
                    "risk_rules": [
                        "Max rebalancing cost: 60% of premium",
                        "Max position: 2 straddles"
                    ],
                    "indicators": ["Delta", "Gamma", "Straddle value", "Rebalancing cost"],
                    "expected_market": "Range-bound with regular oscillations",
                    "failure_market": "Strong trending, rebalancing costs spiral"
                }
            ]
        },
        {
            "id": "strategy_006",
            "name": "Machine Learning Assisted",
            "approaches": [
                {
                    "id": "approach_A",
                    "name": "Random Forest signal generation on options data",
                    "hypothesis": "ML model trained on historical options data (IV, OI, Greeks, price patterns) generates edge over discretionary trading.",
                    "entry_rules": [
                        "Model predicts direction + confidence",
                        "Enter if confidence > 70% and direction is BUY",
                        "Position size proportional to confidence"
                    ],
                    "exit_rules": [
                        "Exit when model signals opposite",
                        "Time exit: 1 hour",
                        "Stop loss: 30% of position"
                    ],
                    "risk_rules": [
                        "Max loss per trade: ₹4000",
                        "Daily max trades: 5",
                        "Model retrain: monthly"
                    ],
                    "indicators": ["ML prediction", "Confidence score", "Feature importance"],
                    "expected_market": "Pattern-driven, clear regime",
                    "failure_market": "Regime change, non-stationary data"
                },
                {
                    "id": "approach_B",
                    "name": "LSTM for price direction prediction",
                    "hypothesis": "LSTM model on multi-factor input (price, volume, IV, OI, VIX) predicts 5-min direction with >60% accuracy.",
                    "entry_rules": [
                        "Model generates prediction every 5 mins",
                        "If prediction probability > 0.65 and direction = up: buy CE",
                        "If prediction probability > 0.65 and direction = down: buy PE"
                    ],
                    "exit_rules": [
                        "Exit on next prediction if direction flips",
                        "Profit target: 1.5x premium",
                        "Stop loss: 40% of premium"
                    ],
                    "risk_rules": [
                        "Max loss per trade: ₹3000",
                        "Only trade if model accuracy > 58% on validation"
                    ],
                    "indicators": ["LSTM prediction", "Probability", "Feature set"],
                    "expected_market": "Trending, clear momentum",
                    "failure_market": "Choppy, low signal-to-noise"
                },
                {
                    "id": "approach_C",
                    "name": "Clustering market regimes, strategy per regime",
                    "hypothesis": "Market regimes (trending, range-bound, high vol, low vol) require different strategies — cluster-based selection improves returns.",
                    "entry_rules": [
                        "Daily cluster assignment based on VIX, ATR, trend强度",
                        "Trending + High Vol: momentum strategies",
                        "Range-bound + Low Vol: mean reversion",
                        "Trending + Low Vol: breakout strategies"
                    ],
                    "exit_rules": [
                        "Re-cluster every day at 9:20 AM IST",
                        "Switch strategy if regime changes",
                        "Exit all positions if regime unclear"
                    ],
                    "risk_rules": [
                        "Max loss per strategy session: ₹5000",
                        "Only switch if cluster confidence > 80%"
                    ],
                    "indicators": ["Regime cluster", "VIX", "ATR ratio", "Trend强度", "Cluster confidence"],
                    "expected_market": "Multi-regime, adaptive trading",
                    "failure_market": "Rapid regime switching, false clustering"
                }
            ]
        }
    ]

    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator
        logger.info("ResearchAgent initialized")

    def write_strategy_journal(self, strategy: dict):
        """Write strategy documentation to journal."""
        strategy_dir = JOURNAL_STRATEGIES_DIR / strategy["id"]
        strategy_dir.mkdir(parents=True, exist_ok=True)

        overview = f"""# {strategy['name']} — Research Overview

## Strategy ID: {strategy['id']}

### Hypothesis Summary
This strategy explores {strategy['name'].lower()} through multiple differentiated approaches.

### Approaches Developed
"""
        for approach in strategy["approaches"]:
            approach_file = strategy_dir / f"{approach['id']}_results.md"
            approach_doc = f"""# Approach {approach['id'].upper()}: {approach['name']}

## Hypothesis
{approach['hypothesis']}

## Entry Rules
{chr(10).join(f"- {rule}" for rule in approach['entry_rules'])}

## Exit Rules
{chr(10).join(f"- {rule}" for rule in approach['exit_rules'])}

## Risk Rules
{chr(10).join(f"- {rule}" for rule in approach['risk_rules'])}

## Required Indicators
{', '.join(approach['indicators'])}

## Expected Market Conditions
- **Works well in:** {approach['expected_market']}
- **Fails in:** {approach['failure_market']}

## Status
- [ ] Hypothesis documented
- [ ] Logic implemented
- [ ] Backtested
- [ ] Approved/Rejected
"""
            with open(approach_file, 'w', encoding='utf-8') as f:
                f.write(approach_doc)

            overview += f"\n### {approach['id'].upper()}: {approach['name']}\n"
            overview += f"- Hypothesis: {approach['hypothesis']}\n"
            overview += f"- Indicators: {', '.join(approach['indicators'])}\n"
            overview += f"- Expected in: {approach['expected_market']}\n"

        overview_path = strategy_dir / "overview.md"
        with open(overview_path, 'w', encoding='utf-8') as f:
            f.write(overview)

        logger.info(f"Journal written for {strategy['id']}")

    def write_strategy_logic(self, strategy: dict, approach: dict, strategy_dir: Path):
        """Write executable strategy logic to Python file."""
        strategy_path = strategy_dir / "logic.py"
        strategy_dir.mkdir(parents=True, exist_ok=True)
        strategy_file_content = f'''"""
{strategy['name']} — Approach {approach['id'].upper()} Logic
Generated by ResearchAgent. DO NOT EDIT MANUALLY — use ConfigAgent for parameter changes.
"""
from typing import Dict, Optional
from datetime import datetime, time

class StrategyLogic:
    """Executable logic for {strategy['name']} / Approach {approach['id'].upper()}."""

    STRATEGY_ID = "{strategy['id']}"
    APPROACH_ID = "{approach['id']}"
    NAME = "{approach['name']}"

    @staticmethod
    def get_entry_signal(data: Dict) -> Optional[Dict]:
        """Evaluate entry conditions and return signal if triggered."""
        # {approach['hypothesis']}
        # Entry rules:
        # {chr(10).join(f"# {i+1}. {r}" for i, r in enumerate(approach['entry_rules']))}
        pass

    @staticmethod
    def get_exit_signal(position: Dict, data: Dict) -> Optional[Dict]:
        """Evaluate exit conditions for open position."""
        # Exit rules:
        # {chr(10).join(f"# {i+1}. {r}" for i, r in enumerate(approach['exit_rules']))}
        pass

    @staticmethod
    def validate_risk(position: Dict, portfolio: Dict) -> Dict:
        """Validate risk rules before order placement."""
        # Risk rules:
        # {chr(10).join(f"# {i+1}. {r}" for i, r in enumerate(approach['risk_rules']))}
        pass

    @staticmethod
    def get_indicators() -> list:
        """Return list of required indicators for this strategy."""
        return {approach['indicators']}
'''
        with open(strategy_path, 'w', encoding='utf-8') as f:
            f.write(strategy_file_content)

    def run(self):
        """Execute research for all strategies."""
        logger.info("ResearchAgent starting strategy research...")

        for strategy in self.STRATEGIES:
            self.write_strategy_journal(strategy)

            strategy_dir = STRATEGIES_DIR / strategy["id"]
            for approach in strategy["approaches"]:
                self.write_strategy_logic(strategy, approach, strategy_dir)

        logger.info(f"ResearchAgent completed. {len(self.STRATEGIES)} strategies documented.")

        if self.orchestrator:
            self.orchestrator.route_message({
                "from": "ResearchAgent",
                "to": "JournalAgent",
                "type": "RESEARCH_COMPLETE",
                "payload": {"strategies_count": len(self.STRATEGIES)}
            })

        return {"strategies": len(self.STRATEGIES), "approaches": sum(len(s["approaches"]) for s in self.STRATEGIES)}


if __name__ == "__main__":
    agent = ResearchAgent()
    result = agent.run()
    print(f"Research complete: {result}")