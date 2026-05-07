"""
ReviewAgent — Evaluates backtest results, scores strategies, flags weaknesses, ranks top performers.
"""
import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

BASE_DIR = Path(__file__).parent.parent
RESULTS_DIR = BASE_DIR / "backtests" / "results"
JOURNAL_REVIEW_DIR = BASE_DIR / "journal" / "review_reports"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.FileHandler(Path(__file__).parent.parent / 'logs' / 'review_agent.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class ReviewAgent:
    """Reviews and ranks backtest results across all strategies."""

    DISQUALIFICATION_THRESHOLDS = {
        "sharpe_min": 0.8,
        "max_dd_max": 40.0,  # Raised from 25% — options inherently volatile
        "min_trades": 50
    }

    SCORING_WEIGHTS = {
        "sharpe": 0.25,
        "max_drawdown": 0.20,
        "win_rate": 0.20,
        "profit_factor": 0.15,
        "consistency": 0.10,
        "live_tradability": 0.10
    }

    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator
        self.results = {}
        self.scores = {}
        logger.info("ReviewAgent initialized")

    def load_all_results(self) -> List[Dict]:
        """Load all backtest summaries."""
        all_results = []
        if not RESULTS_DIR.exists():
            logger.warning(f"Results directory not found: {RESULTS_DIR}")
            return all_results

        for result_dir in RESULTS_DIR.iterdir():
            if result_dir.is_dir():
                summary_file = result_dir / "summary.json"
                if summary_file.exists():
                    with open(summary_file) as f:
                        all_results.append(json.load(f))
        return all_results

    def check_disqualification(self, result: Dict) -> Tuple[bool, str]:
        """Check if strategy should be disqualified."""
        sharpe = result.get("sharpe_ratio", 0)
        max_dd = result.get("max_drawdown_pct", 0)
        trades = result.get("total_trades", 0)

        if sharpe < self.DISQUALIFICATION_THRESHOLDS["sharpe_min"]:
            return True, f"Sharpe {sharpe:.3f} below minimum {self.DISQUALIFICATION_THRESHOLDS['sharpe_min']}"
        if max_dd > self.DISQUALIFICATION_THRESHOLDS["max_dd_max"]:
            return True, f"MaxDD {max_dd:.1f}% exceeds maximum {self.DISQUALIFICATION_THRESHOLDS['max_dd_max']}%"
        if trades < self.DISQUALIFICATION_THRESHOLDS["min_trades"]:
            return True, f"Only {trades} trades, minimum {self.DISQUALIFICATION_THRESHOLDS['min_trades']} required"

        return False, ""

    def calculate_score(self, result: Dict) -> float:
        """Calculate composite score for a strategy."""
        sharpe = result.get("sharpe_ratio", 0)
        max_dd = result.get("max_drawdown_pct", 1)
        win_rate = result.get("win_rate", 0)
        profit_factor = result.get("profit_factor", 0)
        trades = result.get("total_trades", 0)

        sharpe_score = min(sharpe / 2.0, 1.0)
        dd_score = max(0, 1 - max_dd / 30.0)
        wr_score = win_rate
        pf_score = min(profit_factor / 2.5, 1.0) if profit_factor > 0 else 0

        consistency = 1.0 if trades >= 100 else trades / 100.0
        tradability = 0.8 if trades >= 50 else trades / 62.5

        score = (
            sharpe_score * self.SCORING_WEIGHTS["sharpe"] +
            dd_score * self.SCORING_WEIGHTS["max_drawdown"] +
            wr_score * self.SCORING_WEIGHTS["win_rate"] +
            pf_score * self.SCORING_WEIGHTS["profit_factor"] +
            consistency * self.SCORING_WEIGHTS["consistency"] +
            tradability * self.SCORING_WEIGHTS["live_tradability"]
        )
        return round(score, 4)

    def rank_strategies(self) -> List[Dict]:
        """Rank all strategies by composite score."""
        all_results = self.load_all_results()

        ranked = []
        for result in all_results:
            disqualified, reason = self.check_disqualification(result)
            score = self.calculate_score(result) if not disqualified else 0

            ranked.append({
                **result,
                "disqualified": disqualified,
                "disqualification_reason": reason,
                "composite_score": score
            })

        ranked.sort(key=lambda x: x["composite_score"], reverse=True)
        return ranked

    def generate_master_report(self) -> str:
        """Generate the master comparison report."""
        ranked = self.rank_strategies()

        report = "# Strategy Comparison & Ranking Report\n\n"
        report += f"**Generated:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        report += f"**Total strategies evaluated:** {len(ranked)}\n"
        report += f"**Disqualified:** {sum(1 for r in ranked if r['disqualified'])}\n\n"

        report += "## Disqualified Strategies\n\n"
        for r in ranked:
            if r["disqualified"]:
                report += f"- **{r['strategy_id']}/{r['approach_id']}**: {r['disqualification_reason']}\n"
        if not any(r["disqualified"] for r in ranked):
            report += "None — all strategies passed initial screening.\n"

        report += "\n## Ranking Table\n\n"
        report += "| Rank | Strategy | Approach | Score | Sharpe | WinRate | MaxDD | PF | Trades | P&L |\n"
        report += "|------|----------|----------|-------|--------|---------|-------|----|-------|-------|\n"

        for i, r in enumerate(ranked, 1):
            flag = "[X]" if r["disqualified"] else "[OK]"
            report += f"| {i} {flag} | {r['strategy_id']} | {r['approach_id']} | "
            report += f"{r['composite_score']:.3f} | {r.get('sharpe_ratio', 0):.3f} | "
            report += f"{r.get('win_rate', 0)*100:.1f}% | {r.get('max_drawdown_pct', 0):.1f}% | "
            report += f"{r.get('profit_factor', 0):.2f} | {r.get('total_trades', 0)} | "
            report += f"₹{r.get('total_pnl', 0):.0f} |\n"

        top_3 = [r for r in ranked if not r["disqualified"]][:3]
        report += "\n## Top 3 Recommended Strategies\n\n"
        for i, r in enumerate(top_3, 1):
            report += f"### {i}. {r['strategy_id']}/{r['approach_id']}\n"
            report += f"- **Score:** {r['composite_score']:.3f}\n"
            report += f"- **Sharpe Ratio:** {r.get('sharpe_ratio', 0):.3f}\n"
            report += f"- **Win Rate:** {r.get('win_rate', 0)*100:.1f}%\n"
            report += f"- **Max Drawdown:** {r.get('max_drawdown_pct', 0):.1f}%\n"
            report += f"- **Profit Factor:** {r.get('profit_factor', 0):.2f}\n"
            report += f"- **Total Trades:** {r.get('total_trades', 0)}\n"
            report += f"- **P&L:** ₹{r.get('total_pnl', 0):.0f}\n\n"

            recommendation = self._generate_recommendation_text(r)
            report += f"**Recommendation:** {recommendation}\n\n"

        JOURNAL_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        report_path = JOURNAL_REVIEW_DIR / "strategy_comparison.md"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)

        logger.info(f"Review report saved to {report_path}")
        self.results = ranked
        return report

    def _generate_recommendation_text(self, result: Dict) -> str:
        """Generate human-readable recommendation text."""
        sharpe = result.get('sharpe_ratio', 0)
        win_rate = result.get('win_rate', 0)
        max_dd = result.get('max_drawdown_pct', 0)

        if sharpe > 2.0 and win_rate > 0.6:
            return "Excellent risk-adjusted returns with high win rate. Suitable for live trading."
        elif sharpe > 1.5 and max_dd < 15:
            return "Good risk-adjusted returns with reasonable drawdown. Recommended for live trading."
        elif sharpe > 1.0:
            return "Moderate returns. Proceed with caution, validate with paper trading first."
        else:
            return "Below average performance. Not recommended without significant modifications."

    def run(self):
        """Execute the review and generate reports."""
        logger.info("ReviewAgent starting strategy evaluation...")
        report = self.generate_master_report()

        if self.orchestrator:
            top_3 = [r for r in self.results if not r["disqualified"]][:3]
            self.orchestrator.route_message({
                "from": "ReviewAgent",
                "to": "JournalAgent",
                "type": "REVIEW_COMPLETE",
                "payload": {
                    "ranked_strategies": self.results,
                    "top_3": top_3,
                    "report_path": str(JOURNAL_REVIEW_DIR / "strategy_comparison.md")
                }
            })

        logger.info("ReviewAgent completed.")
        return self.results


if __name__ == "__main__":
    agent = ReviewAgent()
    results = agent.run()
    print(f"Review complete. {len(results)} strategies evaluated.")