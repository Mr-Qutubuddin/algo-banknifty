"""
Generate Professional Excel Report — BankNifty Options Algo Trading System
Multi-sheet workbook with strategy summaries and full trade-level detail.
"""
import json
import math
from pathlib import Path
from datetime import datetime
from typing import Dict, List

import openpyxl
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, numbers
)
from openpyxl.utils import get_column_letter
from openpyxl.styles.numbers import FORMAT_NUMBER_COMMA_SEPARATED1

BASE_DIR = Path(__file__).parent.parent.resolve()
JOURNAL_TRADE_LOGS = BASE_DIR / "journal" / "trade_logs"
OUTPUT_DIR = BASE_DIR / "reports"
OUTPUT_DIR.mkdir(exist_ok=True)


# ── Color Palette ──────────────────────────────────────────────────────────────
DARK_NAVY = "0D1B2A"
MEDIUM_NAVY = "1B3A4B"
LIGHT_BLUE = "3A86A8"
ACCENT_BLUE = "0066CC"
ACCENT_GREEN = "00A86B"
ACCENT_RED = "D63031"
GOLD = "D4AF37"
LIGHT_GRAY = "F5F5F5"
WHITE = "FFFFFF"
OFF_WHITE = "FAFAFA"


def _font(bold=False, size=10, color="000000", name="Calibri"):
    return Font(bold=bold, size=size, color=color, name=name)


def _fill(hex_color: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_color)


def _border_thin():
    s = Side(style="thin", color="CCCCCC")
    return Border(left=s, right=s, top=s, bottom=s)


def _border_medium():
    s = Side(style="medium", color="999999")
    return Border(left=s, right=s, top=s, bottom=s)


def _align(h="left", v="center", wrap=False):
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap)


# ── Style Helpers ──────────────────────────────────────────────────────────────
def _style_header_cell(cell, text, bg=DARK_NAVY, fg=WHITE, size=10, bold=True, align="center"):
    cell.value = text
    cell.font = _font(bold=bold, size=size, color=fg)
    cell.fill = _fill(bg)
    cell.alignment = _align(align, "center")
    cell.border = _border_thin()


def _style_subheader_cell(cell, text, bg=MEDIUM_NAVY, fg=WHITE, size=10, bold=True):
    cell.value = text
    cell.font = _font(bold=bold, size=size, color=fg)
    cell.fill = _fill(bg)
    cell.alignment = _align("left", "center", wrap=True)
    cell.border = _border_thin()


def _style_data_cell(cell, value, fmt=None, align="right", bold=False, color="000000"):
    cell.value = value
    cell.font = _font(bold=bold, color=color)
    cell.alignment = _align(align, "center")
    cell.border = _border_thin()
    if fmt:
        cell.number_format = fmt


def _style_label_cell(cell, text, bg=LIGHT_GRAY, bold=True):
    cell.value = text
    cell.font = _font(bold=bold, size=10, color="333333")
    cell.fill = _fill(bg)
    cell.alignment = _align("left", "center")
    cell.border = _border_thin()


def _row_fill(row_idx: int, base_color=WHITE) -> PatternFill:
    if row_idx % 2 == 0:
        return _fill(OFF_WHITE)
    return _fill(base_color)


def set_col_width(ws, col: int, width: float):
    ws.column_dimensions[get_column_letter(col)].width = width


def set_row_height(ws, row: int, height: float):
    ws.row_dimensions[row].height = height


# ── Data Loading ──────────────────────────────────────────────────────────────
def load_trade_log(strategy_id: str, approach_id: str) -> Dict:
    """Load trade log JSON for a strategy."""
    path = JOURNAL_TRADE_LOGS / f"strategy_{strategy_id}_approach_{approach_id}.json"
    if not path.exists():
        return {"strategy": strategy_id, "approach": approach_id, "trade_log": [], "statistics": {}}

    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ── Excel Generation ──────────────────────────────────────────────────────────

def create_excel_report(output_path: Path):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    create_summary_sheet(wb)
    create_rankings_sheet(wb)
    create_strategy_summary_sheet(wb, "004_D", "strategy_004", "approach_D")
    create_strategy_summary_sheet(wb, "006_B", "strategy_006", "approach_B")
    create_strategy_summary_sheet(wb, "003_C", "strategy_003", "approach_C")
    create_trades_sheet(wb, "004_D", "strategy_004", "approach_D")
    create_trades_sheet(wb, "006_B", "strategy_006", "approach_B")
    create_trades_sheet(wb, "003_C", "strategy_003", "approach_C")
    create_trade_level_calculator(wb)

    wb.save(str(output_path))
    print(f"Excel report saved: {output_path}")


def create_summary_sheet(wb):
    ws = wb.create_sheet("Summary")
    ws.sheet_view.showGridLines = False

    # Title block
    ws.merge_cells("A1:L1")
    cell = ws["A1"]
    cell.value = "BANKING & FINANCE QUANTITATIVE STRATEGY REPORT"
    cell.font = Font(name="Calibri", bold=True, size=18, color=WHITE)
    cell.fill = _fill(DARK_NAVY)
    cell.alignment = _align("center", "center")
    set_row_height(ws, 1, 40)

    ws.merge_cells("A2:L2")
    cell = ws["A2"]
    cell.value = "Algorithmic Options Trading — Backtest Validation Report | May 2023 – May 2026"
    cell.font = Font(name="Calibri", bold=False, size=11, color=LIGHT_BLUE)
    cell.fill = _fill(DARK_NAVY)
    cell.alignment = _align("center", "center")
    set_row_height(ws, 2, 22)

    ws.merge_cells("A3:L3")
    ws["A3"].value = ""

    # Meta info row
    meta_row = 4
    ws.merge_cells("A4:C4")
    ws["A4"].value = f"Report Generated: {datetime.now().strftime('%B %d, %Y')}"
    ws["A4"].font = _font(bold=True, size=10, color="555555")
    ws["A4"].fill = _fill(LIGHT_GRAY)
    ws["A4"].alignment = _align("left", "center")

    ws.merge_cells("D4:F4")
    ws["D4"].value = "Initial Capital: ₹1,00,000"
    ws["D4"].font = _font(size=10, color="555555")
    ws["D4"].fill = _fill(LIGHT_GRAY)
    ws["D4"].alignment = _align("center", "center")

    ws.merge_cells("G4:I4")
    ws["G4"].value = "Brokerage: ₹5/buy + ₹5/sell + 6.5% GST + 0.05% STT + 0.01% SEBI"
    ws["G4"].font = _font(size=10, color="555555")
    ws["G4"].fill = _fill(LIGHT_GRAY)
    ws["G4"].alignment = _align("center", "center")

    ws.merge_cells("J4:L4")
    ws["J4"].value = "Lot Size: 15 contracts"
    ws["J4"].font = _font(size=10, color="555555")
    ws["J4"].fill = _fill(LIGHT_GRAY)
    ws["J4"].alignment = _align("center", "center")
    set_row_height(ws, 4, 20)

    ws.merge_cells("A5:L5")
    ws["A5"].value = ""

    # Column headers
    headers = ["#", "Strategy", "Approach", "Sharpe", "CAGR", "Win Rate",
               "Max DD", "Profit Factor", "Trades", "Total P&L", "Min Capital", "Type"]
    col_widths = [4, 14, 12, 8, 8, 9, 8, 12, 8, 12, 10, 10]
    for i, (h, w) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=6, column=i)
        _style_header_cell(cell, h, bg=MEDIUM_NAVY, fg=WHITE, size=10)
        set_col_width(ws, i, w)
    set_row_height(ws, 6, 18)

    # Data rows
    strategy_data = [
        (1, "strategy_006", "approach_A", 3.606, 0.307, 0.436, 0.090, 2.91, 110, 123350, 12810, "BUY only"),
        (2, "strategy_004", "approach_D", 3.870, 1.176, 0.476, 0.091, 2.05, 1231, 930241, 13935, "BUY only"),
        (3, "strategy_002", "approach_A", 3.995, 0.193, 0.500, 0.072, 2.08, 78, 69764, 13815, "BUY only"),
        (4, "strategy_006", "approach_B", 3.876, 1.184, 0.474, 0.117, 2.08, 1235, 942314, 13815, "BUY only"),
        (5, "strategy_003", "approach_C", 3.670, 1.666, 0.474, 0.121, 2.01, 2443, 1793928, 15255, "BUY only"),
        (6, "strategy_002", "approach_C", 3.081, 1.152, 0.442, 0.142, 2.09, 1467, 896172, 13320, "BUY only"),
        (7, "strategy_006", "approach_D", 3.488, 0.881, 0.447, 0.179, 2.45, 600, 566014, 13650, "BUY only"),
        (8, "strategy_003", "approach_D", 2.492, 1.259, 0.433, 0.162, 1.94, 2274, 1053150, 15255, "BUY only"),
        (9, "strategy_004", "approach_C", 2.258, 0.448, 0.434, 0.207, 1.91, 447, 203398, 13560, "BUY only"),
        (10, "strategy_001", "approach_A", 3.468, 0.967, 0.763, 0.180, 0.51, 566, 660704, 18180, "SELL only"),
    ]

    for row_idx, row_data in enumerate(strategy_data, 7):
        bg = OFF_WHITE if row_idx % 2 == 0 else WHITE
        (rank, strat, appr, sharpe, cagr, wr, mdd, pf, trades, pnl, min_cap, typ) = row_data

        vals = [rank, strat, appr, sharpe, f"{cagr*100:.1f}%", f"{wr*100:.1f}%",
                f"{mdd*100:.1f}%", pf, trades,
                f"₹{pnl:,.0f}", f"₹{min_cap:,}", typ]

        fmts = [None, None, None, "0.000", "0.0%", "0.0%", "0.0%", "0.00", None, None, None, None]
        aligns = ["center", "left", "left", "center", "center", "center", "center",
                  "center", "center", "center", "center", "center"]

        for col_idx, (val, fmt, aln) in enumerate(zip(vals, fmts, aligns), 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            if isinstance(val, (int, float)):
                cell.value = val
                cell.font = _font(bold=(col_idx == 1), size=10, color=ACCENT_BLUE if col_idx == 1 else "000000")
                cell.number_format = fmt or "General"
            else:
                cell.value = val
                cell.font = _font(bold=False, size=10)
            cell.fill = _fill(bg)
            cell.alignment = _align(aln, "center")
            cell.border = _border_thin()

        set_row_height(ws, row_idx, 16)

    # Legend row
    legend_row = 17
    ws.merge_cells(f"A{legend_row}:L{legend_row}")
    ws[f"A{legend_row}"].value = "All strategies use 3-year hourly backtest data (May 2023 – May 2026). Sharpe ≥ 0.8 threshold applied. Disqualified: Sharpe < 0.8, MaxDD > 40%, trades < 50."
    ws[f"A{legend_row}"].font = _font(size=9, color="888888", bold=False)
    ws[f"A{legend_row}"].fill = _fill(LIGHT_GRAY)
    ws[f"A{legend_row}"].alignment = _align("left", "center")
    set_row_height(ws, legend_row, 14)

    ws.freeze_panes = "A7"


def create_rankings_sheet(wb):
    ws = wb.create_sheet("Rankings")
    ws.sheet_view.showGridLines = False

    ws.merge_cells("A1:J1")
    cell = ws["A1"]
    cell.value = "STRATEGY RANKINGS — APPROVED STRATEGIES"
    cell.font = Font(bold=True, size=14, color=WHITE, name="Calibri")
    cell.fill = _fill(DARK_NAVY)
    cell.alignment = _align("center", "center")
    set_row_height(ws, 1, 35)

    ws.merge_cells("A2:J2")
    ws["A2"].value = "Ranked by Sharpe Ratio | Data Period: May 2023 – May 2026 | Capital: ₹1,00,000 | Brokerage: ₹5/side + 6.5% GST"
    ws["A2"].font = Font(size=9, color=LIGHT_BLUE, name="Calibri")
    ws["A2"].fill = _fill(DARK_NAVY)
    ws["A2"].alignment = _align("center", "center")
    set_row_height(ws, 2, 18)

    headers = ["Rank", "Strategy", "Approach", "Sharpe", "CAGR", "Win Rate",
               "Max Drawdown", "Profit Factor", "Total Trades", "Net P&L"]
    widths = [6, 16, 12, 8, 8, 9, 12, 12, 10, 14]
    for i, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=4, column=i)
        _style_header_cell(c, h, bg=DARK_NAVY, fg=WHITE, size=10)
        set_col_width(ws, i, w)
    set_row_height(ws, 4, 18)

    data = [
        (1, "strategy_004", "approach_D", 3.870, 117.6, 47.6, 9.1, 2.05, 1231, 930241),
        (2, "strategy_006", "approach_B", 3.876, 118.4, 47.4, 11.7, 2.08, 1235, 942314),
        (3, "strategy_003", "approach_C", 3.670, 166.6, 47.4, 12.1, 2.01, 2443, 1793928),
    ]

    for row_idx, row in enumerate(data, 5):
        bg = OFF_WHITE if row_idx % 2 == 0 else WHITE
        rank, strat, appr, sharpe, cagr, wr, mdd, pf, trades, pnl = row

        vals = [rank, strat, appr, sharpe, f"{cagr:.1f}%", f"{wr:.1f}%",
                f"{mdd:.1f}%", pf, trades, f"₹{pnl:,.0f}"]
        aligns = ["center", "left", "left"] + ["center"] * 7
        for col, (v, a) in enumerate(zip(vals, aligns), 1):
            c = ws.cell(row=row_idx, column=col)
            c.value = v
            c.font = _font(bold=(col == 1), size=10,
                           color=ACCENT_BLUE if col == 1 else "000000")
            c.fill = _fill(bg)
            c.alignment = _align(a, "center")
            c.border = _border_thin()
        set_row_height(ws, row_idx, 18)

    ws.freeze_panes = "A5"


def create_strategy_summary_sheet(wb, tab_name: str, strategy_id: str, approach_id: str):
    ws = wb.create_sheet(f"Strategy {tab_name}")
    ws.sheet_view.showGridLines = False

    trade_data = load_trade_log(strategy_id, approach_id)
    stats = trade_data.get("statistics", {})

    strategy_names = {
        "004_D": "Intraday Momentum Breakout",
        "006_B": "LSTM Momentum",
        "003_C": "BB Squeeze Breakout"
    }
    strat_name = strategy_names.get(tab_name, tab_name)

    # Title
    ws.merge_cells("A1:L1")
    c = ws["A1"]
    c.value = f"STRATEGY {tab_name} — {strat_name.upper()}"
    c.font = Font(bold=True, size=16, color=WHITE, name="Calibri")
    c.fill = _fill(DARK_NAVY)
    c.alignment = _align("center", "center")
    set_row_height(ws, 1, 38)

    # Subtitle
    ws.merge_cells("A2:L2")
    c = ws["A2"]
    c.value = f"Entry: BUY CE/PE on SMA20 + RSI14 crossover | Exit: +50% profit | -30% stop | 60-tick time exit | Confidence: ≥ 0.60"
    c.font = Font(size=9, color=LIGHT_BLUE, name="Calibri")
    c.fill = _fill(MEDIUM_NAVY)
    c.alignment = _align("center", "center")
    set_row_height(ws, 2, 16)

    # Key metrics in 2-column layout
    # Row 4-5: metric labels
    row_start = 4

    metrics_left = [
        ("Sharpe Ratio", stats.get("sharpe_ratio", 0)),
        ("CAGR", stats.get("total_pnl", 0)),
        ("Win Rate", stats.get("win_rate", 0)),
        ("Profit Factor", stats.get("profit_factor", 0)),
    ]
    metrics_right = [
        ("Max Drawdown", stats.get("max_drawdown_pct", 0)),
        ("Total Trades", stats.get("total_trades", 0)),
        ("Avg Trade P&L", stats.get("avg_trade", 0)),
        ("Min Capital Required", stats.get("margin_used", 0)),
    ]

    # Left panel
    ws.merge_cells(f"A{row_start}:F{row_start}")
    c = ws[f"A{row_start}"]
    c.value = "PERFORMANCE METRICS"
    c.font = Font(bold=True, size=11, color=WHITE, name="Calibri")
    c.fill = _fill(MEDIUM_NAVY)
    c.alignment = _align("center", "center")
    set_row_height(ws, row_start, 20)

    row = row_start + 1
    for label, value in metrics_left:
        ws.merge_cells(f"A{row}:C{row}")
        ws[f"A{row}"].value = label
        ws[f"A{row}"].font = _font(bold=True, size=10, color="333333")
        ws[f"A{row}"].fill = _fill(LIGHT_GRAY)
        ws[f"A{row}"].alignment = _align("left", "center")
        ws[f"A{row}"].border = _border_thin()

        ws.merge_cells(f"D{row}:F{row}")
        val_cell = ws[f"D{row}"]
        if label == "Sharpe Ratio":
            val_cell.value = round(float(value), 3)
            val_cell.number_format = "0.000"
        elif label == "Win Rate":
            val_cell.value = f"{float(value)*100:.1f}%"
        elif label == "Profit Factor":
            val_cell.value = round(float(value), 2)
            val_cell.number_format = "0.00"
        elif label == "CAGR":
            val_cell.value = f"₹{value:,.0f}"
        else:
            val_cell.value = value
        val_cell.font = _font(bold=True, size=12, color=ACCENT_BLUE)
        val_cell.fill = _fill(WHITE)
        val_cell.alignment = _align("center", "center")
        val_cell.border = _border_thin()
        set_row_height(ws, row, 20)
        row += 1

    # Right panel
    row = row_start + 1
    ws.merge_cells(f"G{row_start}:L{row_start}")
    ws[f"G{row_start}"].value = "TRADE STATISTICS"
    ws[f"G{row_start}"].font = Font(bold=True, size=11, color=WHITE, name="Calibri")
    ws[f"G{row_start}"].fill = _fill(MEDIUM_NAVY)
    ws[f"G{row_start}"].alignment = _align("center", "center")

    for label, value in metrics_right:
        ws.merge_cells(f"G{row}:I{row}")
        ws[f"G{row}"].value = label
        ws[f"G{row}"].font = _font(bold=True, size=10, color="333333")
        ws[f"G{row}"].fill = _fill(LIGHT_GRAY)
        ws[f"G{row}"].alignment = _align("left", "center")
        ws[f"G{row}"].border = _border_thin()

        ws.merge_cells(f"J{row}:L{row}")
        val_cell = ws[f"J{row}"]
        if label == "Max Drawdown":
            val_cell.value = f"{value:.1f}%"
        elif label == "Total Trades":
            val_cell.value = int(value)
        elif label == "Avg Trade P&L":
            val_cell.value = f"₹{value:,.0f}"
        elif label == "Min Capital Required":
            val_cell.value = f"₹{value:,.0f}"
        else:
            val_cell.value = value
        val_cell.font = _font(bold=True, size=12, color=ACCENT_GREEN)
        val_cell.fill = _fill(WHITE)
        val_cell.alignment = _align("center", "center")
        val_cell.border = _border_thin()
        set_row_height(ws, row, 20)
        row += 1

    # Entry/Exit rules section
    rules_row = row + 1
    ws.merge_cells(f"A{rules_row}:L{rules_row}")
    ws[f"A{rules_row}"].value = "ENTRY & EXIT RULES"
    ws[f"A{rules_row}"].font = Font(bold=True, size=11, color=WHITE, name="Calibri")
    ws[f"A{rules_row}"].fill = _fill(LIGHT_BLUE)
    ws[f"A{rules_row}"].alignment = _align("center", "center")
    set_row_height(ws, rules_row, 18)

    entry_rules = {
        "004_D": [
            ("BUY CE", "price > SMA20 AND RSI(14) > 62"),
            ("BUY PE", "price < SMA20 AND RSI(14) < 38"),
            ("Min premium", "₹30 entry price"),
            ("Strike selection", "Nearest 100-point strike to spot"),
        ],
        "006_B": [
            ("BUY CE", "RSI(9) > 60 AND RSI(14) > 55 AND SMA20 > SMA50"),
            ("BUY PE", "RSI(9) < 40 AND RSI(14) < 45 AND SMA20 < SMA50"),
            ("Min premium", "₹30 entry price"),
            ("Strike selection", "Nearest 100-point strike to spot"),
        ],
        "003_C": [
            ("BUY Straddle", "BB_width < 0.03 AND regime != 'high_vol'"),
            ("Regime filter", "Skipped in high_vol regime"),
            ("Min premium", "₹20 combined straddle"),
            ("Strike selection", "Nearest 200-point ATM strike"),
        ],
    }

    rules = entry_rules.get(tab_name, [])
    rule_row = rules_row + 1
    for rule_label, rule_desc in rules:
        ws.merge_cells(f"A{rule_row}:C{rule_row}")
        ws[f"A{rule_row}"].value = rule_label
        ws[f"A{rule_row}"].font = _font(bold=True, size=10, color=DARK_NAVY)
        ws[f"A{rule_row}"].fill = _fill(LIGHT_GRAY)
        ws[f"A{rule_row}"].alignment = _align("left", "center")
        ws[f"A{rule_row}"].border = _border_thin()

        ws.merge_cells(f"D{rule_row}:L{rule_row}")
        ws[f"D{rule_row}"].value = rule_desc
        ws[f"D{rule_row}"].font = _font(bold=False, size=10, color="333333")
        ws[f"D{rule_row}"].fill = _fill(WHITE)
        ws[f"D{rule_row}"].alignment = _align("left", "center")
        ws[f"D{rule_row}"].border = _border_thin()
        set_row_height(ws, rule_row, 16)
        rule_row += 1

    # Exit rules
    exit_row = rule_row + 1
    exit_rules = [
        ("50% Profit Target", "Exit when P&L >= +50% of entry premium"),
        ("30% Stop Loss", "Exit when P&L <= -30% of entry premium"),
        ("Time Exit", "Exit after 60 ticks with P&L < +10%"),
        ("Brokerage", "₹5/buy + ₹5/sell + 6.5% GST + 0.01% SEBI + 0.05% STT (sell)"),
    ]
    ws.merge_cells(f"A{exit_row}:L{exit_row}")
    ws[f"A{exit_row}"].value = "EXIT RULES"
    ws[f"A{exit_row}"].font = Font(bold=True, size=11, color=WHITE, name="Calibri")
    ws[f"A{exit_row}"].fill = _fill(MEDIUM_NAVY)
    ws[f"A{exit_row}"].alignment = _align("center", "center")
    set_row_height(ws, exit_row, 18)

    for label, desc in exit_rules:
        exit_row += 1
        ws.merge_cells(f"A{exit_row}:C{exit_row}")
        ws[f"A{exit_row}"].value = label
        ws[f"A{exit_row}"].font = _font(bold=True, size=10, color=DARK_NAVY)
        ws[f"A{exit_row}"].fill = _fill(LIGHT_GRAY)
        ws[f"A{exit_row}"].alignment = _align("left", "center")
        ws[f"A{exit_row}"].border = _border_thin()

        ws.merge_cells(f"D{exit_row}:L{exit_row}")
        ws[f"D{exit_row}"].value = desc
        ws[f"D{exit_row}"].font = _font(bold=False, size=10, color="333333")
        ws[f"D{exit_row}"].fill = _fill(WHITE)
        ws[f"D{exit_row}"].alignment = _align("left", "center")
        ws[f"D{exit_row}"].border = _border_thin()
        set_row_height(ws, exit_row, 16)


def create_trades_sheet(wb, tab_name: str, strategy_id: str, approach_id: str):
    ws = wb.create_sheet(f"Trades {tab_name}")
    ws.sheet_view.showGridLines = False

    trade_data = load_trade_log(strategy_id, approach_id)
    trades = trade_data.get("trade_log", [])
    stats = trade_data.get("statistics", {})

    strategy_names = {
        "004_D": "Intraday Momentum Breakout",
        "006_B": "LSTM Momentum",
        "003_C": "BB Squeeze Breakout"
    }
    strat_name = strategy_names.get(tab_name, tab_name)

    # Title
    ws.merge_cells("A1:O1")
    c = ws["A1"]
    c.value = f"TRADE LOG — {tab_name} | {strat_name} | {len(trades)} Trades"
    c.font = Font(bold=True, size=14, color=WHITE, name="Calibri")
    c.fill = _fill(DARK_NAVY)
    c.alignment = _align("center", "center")
    set_row_height(ws, 1, 35)

    ws.merge_cells("A2:O2")
    ws["A2"].value = f"Sharpe: {stats.get('sharpe_ratio',0):.3f} | Win Rate: {stats.get('win_rate',0)*100:.1f}% | Profit Factor: {stats.get('profit_factor',0):.2f} | Total P&L: ₹{stats.get('total_pnl',0):,.0f} | Max DD: {stats.get('max_drawdown_pct',0)*100:.1f}%"
    ws["A2"].font = Font(size=10, color=LIGHT_BLUE, name="Calibri")
    ws["A2"].fill = _fill(MEDIUM_NAVY)
    ws["A2"].alignment = _align("center", "center")
    set_row_height(ws, 2, 18)

    # Column headers
    headers = ["#", "Order ID", "Instrument", "Strike", "Type", "Side", "Qty",
               "Entry Price", "Exit Price", "P&L (₹)", "Charges (₹)", "Entry Time",
               "Exit Time", "Duration (min)", "P&L Net"]
    widths = [4, 12, 20, 8, 6, 6, 6, 11, 11, 11, 10, 20, 20, 12, 11]

    for i, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=4, column=i)
        _style_header_cell(c, h, bg=DARK_NAVY, fg=WHITE, size=10)
        set_col_width(ws, i, w)
    set_row_height(ws, 4, 18)

    for row_idx, trade in enumerate(trades, 5):
        bg = OFF_WHITE if row_idx % 2 == 0 else WHITE

        pnl = trade.get("pnl", 0)
        charges = trade.get("charges", {})
        total_charges = charges.get("total_charges", 0)
        net_pnl = pnl  # pnl is already net of charges

        duration = trade.get("duration_minutes", 0)

        row_vals = [
            row_idx - 4,
            trade.get("order_id", ""),
            trade.get("instrument", ""),
            trade.get("strike", ""),
            trade.get("option_type", ""),
            trade.get("side", ""),
            trade.get("quantity", 1),
            round(trade.get("entry_price", 0), 2),
            round(trade.get("exit_price", 0), 2),
            round(pnl, 2),
            round(total_charges, 2),
            trade.get("entry_time", ""),
            trade.get("exit_time", ""),
            int(duration) if duration else 0,
            round(pnl, 2),
        ]

        fmts = [None, None, None, None, None, None, None,
                "0.00", "0.00", "#,##0.00", "#,##0.00", None, None, None, "#,##0.00"]

        pnl_color = ACCENT_GREEN if pnl >= 0 else ACCENT_RED

        for col_idx, (val, fmt) in enumerate(zip(row_vals, fmts), 1):
            c = ws.cell(row=row_idx, column=col_idx)
            c.value = val
            c.border = _border_thin()
            c.alignment = _align("center", "center")
            c.fill = _fill(bg)

            if col_idx == 10:  # P&L column
                c.font = _font(bold=True, size=10, color=pnl_color)
                c.number_format = "#,##0.00"
            elif col_idx == 15:  # Net P&L
                c.font = _font(bold=True, size=10, color=pnl_color)
                c.number_format = "#,##0.00"
            elif fmt:
                c.font = _font(bold=False, size=10)
                c.number_format = fmt
            else:
                c.font = _font(bold=False, size=10)

        set_row_height(ws, row_idx, 15)

    # Summary row at bottom
    summary_row = 5 + len(trades)
    ws.merge_cells(f"A{summary_row}:H{summary_row}")
    ws[f"A{summary_row}"].value = "TOTAL"
    ws[f"A{summary_row}"].font = Font(bold=True, size=11, color=WHITE, name="Calibri")
    ws[f"A{summary_row}"].fill = _fill(DARK_NAVY)
    ws[f"A{summary_row}"].alignment = _align("center", "center")
    ws[f"A{summary_row}"].border = _border_thin()

    total_pnl = stats.get("total_pnl", 0)
    total_charges = sum(t.get("charges", {}).get("total_charges", 0) for t in trades)

    ws.cell(row=summary_row, column=9).value = round(total_pnl, 2)
    ws.cell(row=summary_row, column=9).number_format = "#,##0.00"
    ws.cell(row=summary_row, column=9).font = _font(bold=True, size=11, color=ACCENT_GREEN)
    ws.cell(row=summary_row, column=9).fill = _fill(DARK_NAVY)
    ws.cell(row=summary_row, column=9).border = _border_thin()
    ws.cell(row=summary_row, column=9).alignment = _align("center", "center")

    ws.cell(row=summary_row, column=11).value = round(total_charges, 2)
    ws.cell(row=summary_row, column=11).number_format = "#,##0.00"
    ws.cell(row=summary_row, column=11).font = _font(bold=True, size=11, color=WHITE)
    ws.cell(row=summary_row, column=11).fill = _fill(DARK_NAVY)
    ws.cell(row=summary_row, column=11).border = _border_thin()
    ws.cell(row=summary_row, column=11).alignment = _align("center", "center")

    ws.freeze_panes = "A5"


def create_trade_level_calculator(wb):
    """Sheet with raw trade data formatted for independent recalculation."""
    ws = wb.create_sheet("Recalculation Data")
    ws.sheet_view.showGridLines = False

    ws.merge_cells("A1:N1")
    c = ws["A1"]
    c.value = "TRADE-LEVEL RECALCULATION DATA — All Strategies Combined"
    c.font = Font(bold=True, size=14, color=WHITE, name="Calibri")
    c.fill = _fill(DARK_NAVY)
    c.alignment = _align("center", "center")
    set_row_height(ws, 1, 35)

    ws.merge_cells("A2:N2")
    ws["A2"].value = "Use this data to independently recalculate P&L: P&L = (exit_price - entry_price) × quantity × lot_size - total_charges"
    ws["A2"].font = Font(size=9, color=LIGHT_BLUE, name="Calibri")
    ws["A2"].fill = _fill(MEDIUM_NAVY)
    ws["A2"].alignment = _align("center", "center")

    headers = ["Strategy", "Approach", "#", "Order ID", "Instrument", "Strike",
               "Type", "Side", "Qty", "Lot Size", "Entry Price", "Exit Price",
               "Charges", "P&L (Gross)", "P&L (Net)", "Entry Time", "Exit Time", "Duration"]
    widths = [12, 10, 5, 12, 22, 8, 6, 6, 6, 8, 11, 11, 10, 12, 12, 20, 20, 10]

    for i, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=4, column=i)
        _style_header_cell(c, h, bg=DARK_NAVY, fg=WHITE, size=10)
        set_col_width(ws, i, w)
    set_row_height(ws, 4, 18)

    strategies = [
        ("strategy_004", "approach_D", "004_D"),
        ("strategy_006", "approach_B", "006_B"),
        ("strategy_003", "approach_C", "003_C"),
    ]

    row_num = 5
    for strat_id, appr_id, tab_name in strategies:
        trade_data = load_trade_log(strat_id, appr_id)
        trades = trade_data.get("trade_log", [])

        strat_name = {
            "004_D": "Momentum Breakout",
            "006_B": "LSTM Momentum",
            "003_C": "BB Squeeze"
        }.get(tab_name, tab_name)

        for trade_idx, trade in enumerate(trades, 1):
            bg = OFF_WHITE if row_num % 2 == 0 else WHITE

            pnl = trade.get("pnl", 0)
            charges = trade.get("charges", {})
            total_charges = charges.get("total_charges", 0)
            qty = trade.get("quantity", 1)
            lot_size = 15

            gross_pnl = (trade.get("exit_price", 0) - trade.get("entry_price", 0)) * qty * lot_size

            row_vals = [
                tab_name,
                appr_id.replace("approach_", ""),
                trade_idx,
                trade.get("order_id", ""),
                trade.get("instrument", ""),
                trade.get("strike", ""),
                trade.get("option_type", ""),
                trade.get("side", ""),
                qty,
                lot_size,
                round(trade.get("entry_price", 0), 2),
                round(trade.get("exit_price", 0), 2),
                round(total_charges, 2),
                round(gross_pnl, 2),
                round(pnl, 2),
                trade.get("entry_time", ""),
                trade.get("exit_time", ""),
                int(trade.get("duration_minutes", 0) or 0),
            ]

            fmts = [None, None, None, None, None, None, None, None, None, None,
                    "0.00", "0.00", "#,##0.00", "#,##0.00", "#,##0.00", None, None, None]

            pnl_color = ACCENT_GREEN if pnl >= 0 else ACCENT_RED

            for col_idx, (val, fmt) in enumerate(zip(row_vals, fmts), 1):
                c = ws.cell(row=row_num, column=col_idx)
                c.value = val
                c.fill = _fill(bg)
                c.border = _border_thin()
                c.alignment = _align("center", "center")

                if col_idx == 15:  # Net P&L
                    c.font = _font(bold=True, size=9, color=pnl_color)
                    c.number_format = "#,##0.00"
                elif fmt:
                    c.number_format = fmt

            set_row_height(ws, row_num, 14)
            row_num += 1

    ws.freeze_panes = "A5"


# ── Word Document Generation ──────────────────────────────────────────────────

def create_word_report(output_path: Path):
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document()

    # Page setup
    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)

    def set_heading_style(para, level=1):
        para.style = f'Heading {level}'

    def add_table_row(table, cells_data, style="Light Shading Accent 1"):
        row = table.add_row()
        for i, cell_data in enumerate(cells_data):
            cell = row.cells[i]
            cell.text = str(cell_data)
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    def shade_cell(cell, hex_color):
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'), hex_color)
        tcPr.append(shd)

    def set_cell_border(cell, **kwargs):
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        tcBorders = OxmlElement('w:tcBorders')
        for edge in ('left', 'top', 'right', 'bottom'):
            border = OxmlElement(f'w:{edge}')
            border.set(qn('w:val'), 'single')
            border.set(qn('w:sz'), '4')
            border.set(qn('w:space'), '0')
            border.set(qn('w:color'), 'CCCCCC')
            tcBorders.append(border)
        tcPr.append(tcBorders)

    # ── COVER PAGE ─────────────────────────────────────────────────────────────
    doc.add_paragraph()
    doc.add_paragraph()
    doc.add_paragraph()

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("BANKING & FINANCE")
    run.font.name = "Calibri"
    run.font.size = Pt(14)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x0D, 0x1B, 0x2A)
    title.paragraph_format.space_after = Pt(0)

    title2 = doc.add_paragraph()
    title2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run2 = title2.add_run("QUANTITATIVE STRATEGY RESEARCH REPORT")
    run2.font.name = "Calibri"
    run2.font.size = Pt(22)
    run2.font.bold = True
    run2.font.color.rgb = RGBColor(0x0D, 0x1B, 0x2A)
    title2.paragraph_format.space_before = Pt(4)
    title2.paragraph_format.space_after = Pt(0)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run3 = subtitle.add_run("Algorithmic Options Trading System")
    run3.font.name = "Calibri"
    run3.font.size = Pt(14)
    run3.font.color.rgb = RGBColor(0x3A, 0x86, 0xA8)
    subtitle.paragraph_format.space_before = Pt(6)

    doc.add_paragraph()

    # Divider line
    div_para = doc.add_paragraph()
    div_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_div = div_para.add_run("━" * 70)
    run_div.font.color.rgb = RGBColor(0xD4, 0xAF, 0x37)
    run_div.font.size = Pt(10)

    doc.add_paragraph()

    meta_table = doc.add_table(rows=8, cols=2)
    meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_table.style = 'Table Grid'

    meta_data = [
        ("Report Title", "Algorithmic BankNifty Options Trading — Strategy Validation Report"),
        ("Classification", "Confidential — For Internal Review"),
        ("Period", "May 2023 – May 2026 (3 Years)"),
        ("Data Source", "Historical OHLCV Data — Hourly Candles (5,071 ticks)"),
        ("Initial Capital", "₹1,00,000"),
        ("Brokerage Model", "₹5 flat/buy | ₹5 flat/sell | 6.5% GST | 0.05% STT (sell) | 0.01% SEBI"),
        ("Lot Size", "15 contracts (BANKNIFTY options)"),
        ("Report Date", datetime.now().strftime("%B %d, %Y")),
    ]

    for i, (label, value) in enumerate(meta_data):
        row = meta_table.rows[i]
        row.cells[0].text = label
        row.cells[0].paragraphs[0].runs[0].font.bold = True
        row.cells[0].paragraphs[0].runs[0].font.color.rgb = RGBColor(0x0D, 0x1B, 0x2A)
        row.cells[0].paragraphs[0].runs[0].font.size = Pt(10)
        shade_cell(row.cells[0], "F5F5F5")
        row.cells[1].text = value
        row.cells[1].paragraphs[0].runs[0].font.size = Pt(10)
        shade_cell(row.cells[1], "FFFFFF")
        set_cell_border(row.cells[0])
        set_cell_border(row.cells[1])
        for cell in row.cells:
            cell.width = Cm(7)

    doc.add_page_break()

    # ── EXECUTIVE SUMMARY ──────────────────────────────────────────────────────
    h1 = doc.add_heading("1. Executive Summary", level=1)
    h1.runs[0].font.color.rgb = RGBColor(0x0D, 0x1B, 0x2A)
    h1.runs[0].font.size = Pt(16)

    exec_para = doc.add_paragraph()
    exec_para.add_run(
        "This report presents a comprehensive backtesting analysis of algorithmic options trading "
        "strategies applied to BankNifty futures and options. The system was evaluated over a three-year "
        "period (May 2023 – May 2026) using hourly OHLCV data, encompassing diverse market conditions "
        "including bull runs, bear corrections, and range-bound phases."
    )
    exec_para.paragraph_format.space_after = Pt(10)

    exec_para2 = doc.add_paragraph()
    exec_para2.add_run(
        "Out of 21 strategy approaches tested, 10 met the minimum qualification criteria "
        "(Sharpe Ratio ≥ 0.8, maximum drawdown ≤ 40%, minimum 50 trades). Three strategies received "
        "approval for paper trading deployment: Strategy 004/approach_D (Intraday Momentum Breakout), "
        "Strategy 006/approach_B (LSTM Momentum), and Strategy 003/approach_C (BB Squeeze Breakout)."
    )
    exec_para2.paragraph_format.space_after = Pt(10)

    # Key stats box
    stats_table = doc.add_table(rows=4, cols=4)
    stats_table.style = 'Table Grid'
    stats_table.alignment = WD_TABLE_ALIGNMENT.CENTER

    kpis = [
        ("Best Sharpe", "3.87", "004_D"),
        ("Highest CAGR", "166.6%", "003_C"),
        ("Lowest Max DD", "9.1%", "004_D"),
        ("Highest P&L", "₹17,93,928", "003_C"),
    ]

    for col_idx, (label, val, strat) in enumerate(kpis):
        cell = stats_table.rows[0].cells[col_idx]
        shade_cell(cell, "0D1B2A")
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = cell.paragraphs[0].add_run(label)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        run.font.size = Pt(9)
        cell.paragraphs[0].paragraph_format.space_before = Pt(4)

        cell2 = stats_table.rows[1].cells[col_idx]
        shade_cell(cell2, "F5F5F5")
        cell2.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        run2 = cell2.paragraphs[0].add_run(val)
        run2.font.bold = True
        run2.font.size = Pt(20)
        run2.font.color.rgb = RGBColor(0x00, 0xA8, 0x6B)
        cell2.paragraphs[0].paragraph_format.space_before = Pt(2)

        cell3 = stats_table.rows[2].cells[col_idx]
        shade_cell(cell3, "FFFFFF")
        cell3.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        run3 = cell3.paragraphs[0].add_run(strat)
        run3.font.size = Pt(10)
        run3.font.color.rgb = RGBColor(0x3A, 0x86, 0xA8)
        cell3.paragraphs[0].paragraph_format.space_after = Pt(4)

    doc.add_paragraph()

    # ── SECTION 2: METHODOLOGY ─────────────────────────────────────────────────
    h2 = doc.add_heading("2. Methodology", level=1)
    h2.runs[0].font.color.rgb = RGBColor(0x0D, 0x1B, 0x2A)
    h2.runs[0].font.size = Pt(16)

    meth_para = doc.add_paragraph()
    meth_para.add_run("2.1 Data Sources and Period").bold = True
    meth_para.paragraph_format.space_before = Pt(6)

    meth_table = doc.add_table(rows=5, cols=2)
    meth_table.style = 'Table Grid'
    meth_data = [
        ("Data Source", "simulation_feed_hourly.json (primary)"),
        ("Time Period", "May 26, 2023 – May 7, 2026 (3 years)"),
        ("Candle Interval", "Hourly (5,071 ticks)"),
        ("Underlying", "BankNifty (BANKNIFTY indices options)"),
        ("Lot Size", "15 contracts per lot"),
    ]
    for i, (k, v) in enumerate(meth_data):
        meth_table.rows[i].cells[0].text = k
        meth_table.rows[i].cells[0].paragraphs[0].runs[0].font.bold = True
        meth_table.rows[i].cells[1].text = v
        shade_cell(meth_table.rows[i].cells[0], "F5F5F5")
        shade_cell(meth_table.rows[i].cells[1], "FFFFFF")

    doc.add_paragraph()

    meth_para2 = doc.add_paragraph()
    meth_para2.add_run("2.2 Brokerage and Cost Model").bold = True
    meth_para2.paragraph_format.space_before = Pt(6)

    cost_table = doc.add_table(rows=6, cols=3)
    cost_table.style = 'Table Grid'
    cost_headers = ["Charge Type", "Rate", "Applies To"]
    for i, h in enumerate(cost_headers):
        cell = cost_table.rows[0].cells[i]
        shade_cell(cell, "1B3A4B")
        cell.paragraphs[0].clear()
        run = cell.paragraphs[0].add_run(h)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        run.font.bold = True
        run.font.size = Pt(10)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    cost_data = [
        ("Brokerage (Flat)", "₹5.00 per side", "BUY and SELL orders"),
        ("GST", "6.5% of brokerage", "All orders"),
        ("STT (Securities Transaction Tax)", "0.05% of turnover", "SELL orders only"),
        ("SEBI Charges", "0.01% of turnover", "All orders"),
        ("Slippage", "0.05% of price", "Market orders"),
    ]
    for row_idx, (ctype, rate, applies) in enumerate(cost_data, 1):
        bg = "F5F5F5" if row_idx % 2 == 0 else "FFFFFF"
        for col_idx, val in enumerate([ctype, rate, applies]):
            cell = cost_table.rows[row_idx].cells[col_idx]
            cell.text = val
            cell.paragraphs[0].runs[0].font.size = Pt(10)
            shade_cell(cell, bg)
            set_cell_border(cell)

    doc.add_page_break()

    # ── SECTION 3: STRATEGY DESCRIPTIONS ───────────────────────────────────────
    h3 = doc.add_heading("3. Approved Strategy Descriptions", level=1)
    h3.runs[0].font.color.rgb = RGBColor(0x0D, 0x1B, 0x2A)
    h3.runs[0].font.size = Pt(16)

    strategies_doc = [
        {
            "id": "004_D",
            "name": "Intraday Momentum Breakout",
            "sharpe": "3.87",
            "cagr": "117.6%",
            "winrate": "47.6%",
            "maxdd": "9.1%",
            "pf": "2.05",
            "trades": "1,231",
            "pnl": "₹9,30,241",
            "min_cap": "₹13,935",
            "entry": "BUY CE when price > SMA20 AND RSI(14) > 62\nBUY PE when price < SMA20 AND RSI(14) < 38",
            "indicators": "SMA20 — 20-period Simple Moving Average\nRSI(14) — 14-period Relative Strength Index",
            "exit": "50% profit target\n30% stop loss\n60-tick time exit",
            "holds": "~24 hours (positional)",
        },
        {
            "id": "006_B",
            "name": "LSTM Momentum",
            "sharpe": "3.88",
            "cagr": "118.4%",
            "winrate": "47.4%",
            "maxdd": "11.7%",
            "pf": "2.08",
            "trades": "1,235",
            "pnl": "₹9,42,314",
            "min_cap": "₹13,815",
            "entry": "BUY CE when RSI(9) > 60 AND RSI(14) > 55 AND SMA20 > SMA50\nBUY PE when RSI(9) < 40 AND RSI(14) < 45 AND SMA20 < SMA50",
            "indicators": "RSI(9) — Fast 9-period Relative Strength Index\nRSI(14) — Slow 14-period RSI\nSMA20/SMA50 — 20 and 50 period SMA",
            "exit": "50% profit target\n30% stop loss\n60-tick time exit",
            "holds": "~25 hours (positional)",
        },
        {
            "id": "003_C",
            "name": "BB Squeeze Breakout",
            "sharpe": "3.67",
            "cagr": "166.6%",
            "winrate": "47.4%",
            "maxdd": "12.1%",
            "pf": "2.01",
            "trades": "2,443",
            "pnl": "₹17,93,928",
            "min_cap": "₹15,255",
            "entry": "BUY ATM STRADDLE when BB_width < 0.03 AND regime ≠ 'high_vol'\n(Regime = trending_up/down/range_bound/high_vol based on ATR%)",
            "indicators": "BB_width — Bollinger Band width < 0.03 (squeeze condition)\nATR% — ATR/price × 100 (regime detection)\nRegime classification based on ATR%, price vs SMA20, RSI",
            "exit": "50% profit target\n30% stop loss\n60-tick time exit",
            "holds": "~26 hours (positional)",
        },
    ]

    for strat in strategies_doc:
        # Strategy header
        h_strat = doc.add_heading(f"3.{list(strategies_doc).index(strat)+1} Strategy {strat['id']} — {strat['name']}", level=2)
        h_strat.runs[0].font.color.rgb = RGBColor(0x1B, 0x3A, 0x4B)
        h_strat.runs[0].font.size = Pt(13)

        # Stats table
        stats_t = doc.add_table(rows=2, cols=8)
        stats_t.style = 'Table Grid'
        stats_t.alignment = WD_TABLE_ALIGNMENT.CENTER

        stat_headers = ["Sharpe", "CAGR", "Win Rate", "Max DD", "Profit Factor", "Trades", "Total P&L", "Min Capital"]
        stat_vals = [strat['sharpe'], strat['cagr'], strat['winrate'], strat['maxdd'],
                     strat['pf'], strat['trades'], strat['pnl'], strat['min_cap']]

        for i, h in enumerate(stat_headers):
            c = stats_t.rows[0].cells[i]
            shade_cell(c, "0D1B2A")
            c.paragraphs[0].clear()
            run = c.paragraphs[0].add_run(h)
            run.font.bold = True
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            run.font.size = Pt(8)
            c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

        for i, v in enumerate(stat_vals):
            c = stats_t.rows[1].cells[i]
            shade_cell(c, "F5F5F5" if i % 2 == 0 else "FFFFFF")
            c.paragraphs[0].clear()
            run = c.paragraphs[0].add_run(v)
            run.font.bold = True
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0x00, 0xA8, 0x6B) if i != 3 else RGBColor(0xD6, 0x30, 0x31)
            c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

        doc.add_paragraph()

        # Entry logic
        p_entry = doc.add_paragraph()
        p_entry.add_run("Entry Logic: ").bold = True
        p_entry.add_run(strat['entry']).font.size = Pt(10)

        p_ind = doc.add_paragraph()
        p_ind.add_run("Indicators Used: ").bold = True
        p_ind.add_run(strat['indicators']).font.size = Pt(10)

        p_exit = doc.add_paragraph()
        p_exit.add_run("Exit Rules: ").bold = True
        p_exit.add_run(strat['exit']).font.size = Pt(10)

        p_hold = doc.add_paragraph()
        p_hold.add_run("Average Hold Time: ").bold = True
        p_hold.add_run(strat['holds']).font.size = Pt(10)

        doc.add_paragraph()

    doc.add_page_break()

    # ── SECTION 4: FULL RESULTS TABLE ──────────────────────────────────────────
    h4 = doc.add_heading("4. Full Strategy Rankings", level=1)
    h4.runs[0].font.color.rgb = RGBColor(0x0D, 0x1B, 0x2A)
    h4.runs[0].font.size = Pt(16)

    doc.add_paragraph(
        "Table below shows all 10 qualifying strategies ranked by Sharpe Ratio. "
        "Disqualified strategies had Sharpe < 0.8, maximum drawdown > 40%, or fewer than 50 trades."
    ).paragraph_format.space_after = Pt(10)

    ranking_table = doc.add_table(rows=11, cols=9)
    ranking_table.style = 'Table Grid'

    r_headers = ["Rank", "Strategy", "Approach", "Sharpe", "CAGR", "Win Rate", "Max DD", "Profit Factor", "Trades"]
    for i, h in enumerate(r_headers):
        c = ranking_table.rows[0].cells[i]
        shade_cell(c, "0D1B2A")
        c.paragraphs[0].clear()
        run = c.paragraphs[0].add_run(h)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        run.font.size = Pt(9)
        c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    ranking_data = [
        (1, "strategy_006", "approach_A", "3.606", "30.7%", "43.6%", "9.0%", "2.91", "110"),
        (2, "strategy_004", "approach_D", "3.870", "117.6%", "47.6%", "9.1%", "2.05", "1,231"),
        (3, "strategy_002", "approach_A", "3.995", "19.3%", "50.0%", "7.2%", "2.08", "78"),
        (4, "strategy_006", "approach_B", "3.876", "118.4%", "47.4%", "11.7%", "2.08", "1,235"),
        (5, "strategy_003", "approach_C", "3.670", "166.6%", "47.4%", "12.1%", "2.01", "2,443"),
        (6, "strategy_002", "approach_C", "3.081", "115.2%", "44.2%", "14.2%", "2.09", "1,467"),
        (7, "strategy_006", "approach_D", "3.488", "88.1%", "44.7%", "17.9%", "2.45", "600"),
        (8, "strategy_003", "approach_D", "2.492", "125.9%", "43.3%", "16.2%", "1.94", "2,274"),
        (9, "strategy_004", "approach_C", "2.258", "44.8%", "43.4%", "20.7%", "1.91", "447"),
        (10, "strategy_001", "approach_A", "3.468", "96.7%", "76.3%", "18.0%", "0.51", "566"),
    ]

    for row_idx, row_data in enumerate(ranking_data, 1):
        bg = "F5F5F5" if row_idx % 2 == 0 else "FFFFFF"
        for col_idx, val in enumerate(row_data):
            c = ranking_table.rows[row_idx].cells[col_idx]
            c.text = str(val)
            shade_cell(c, bg)
            c.paragraphs[0].runs[0].font.size = Pt(9)
            c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_page_break()

    # ── SECTION 5: RISK PARAMETERS ─────────────────────────────────────────────
    h5 = doc.add_heading("5. Risk Management Parameters", level=1)
    h5.runs[0].font.color.rgb = RGBColor(0x0D, 0x1B, 0x2A)
    h5.runs[0].font.size = Pt(16)

    risk_data = [
        ("Max Open Positions", "3 simultaneous positions"),
        ("Per-Trade Stop Loss", "-30% of entry premium"),
        ("Per-Trade Profit Target", "+50% of entry premium"),
        ("Time-Based Exit", "60 ticks with P&L < +10%"),
        ("Max Daily Loss (Kill Switch)", "₹5,000 — triggers auto square-off"),
        ("Max Per-Trade Loss", "₹3,000 — hard stop"),
        ("Margin Utilization", "Maximum 80% of available capital"),
        ("Auto Square-Off Time", "15:20 IST (5 minutes before market close)"),
        ("Confidence Threshold", "≥ 0.60 (floating-point safe comparison)"),
    ]

    risk_t = doc.add_table(rows=len(risk_data), cols=2)
    risk_t.style = 'Table Grid'

    for i, (param, value) in enumerate(risk_data):
        c0 = risk_t.rows[i].cells[0]
        c0.text = param
        c0.paragraphs[0].runs[0].font.bold = True
        c0.paragraphs[0].runs[0].font.size = Pt(10)
        shade_cell(c0, "F5F5F5")

        c1 = risk_t.rows[i].cells[1]
        c1.text = value
        c1.paragraphs[0].runs[0].font.size = Pt(10)
        shade_cell(c1, "FFFFFF")

    doc.add_paragraph()

    # ── SECTION 6: VALIDATION NOTES ────────────────────────────────────────────
    h6 = doc.add_heading("6. Validation Notes", level=1)
    h6.runs[0].font.color.rgb = RGBColor(0x0D, 0x1B, 0x2A)
    h6.runs[0].font.size = Pt(16)

    val_notes = [
        "All strategies use BUY-only logic — no short option selling. Direction (CE vs PE) is determined by market regime indicators at entry time.",
        "All P&L figures are net of brokerage, GST, SEBI, and STT charges. Brokerage model: ₹5 flat per side + 6.5% GST on brokerage + 0.01% SEBI on turnover + 0.05% STT on sell turnover.",
        "Floating-point comparison bug was identified and resolved: confidence threshold of 0.60 uses >= comparison (not >) to correctly capture signals at the boundary.",
        "All strategies were tested on 3 years of hourly data (May 2023 – May 2026) — 5,071 hourly candles — representing diverse market conditions including bull trends, bear corrections, and range-bound periods.",
        "The Excel workbook accompanying this report contains full trade-level data with entry/exit prices, charges breakdown, and timestamps for independent recalculation and audit verification.",
        "Backtest results represent simulated performance and do not guarantee future results. Actual trading may differ due to slippage, execution quality, and market liquidity variations.",
    ]

    for note in val_notes:
        p = doc.add_paragraph()
        run = p.add_run("• ")
        run.font.color.rgb = RGBColor(0x00, 0xA8, 0x6B)
        run.bold = True
        p.add_run(note).font.size = Pt(10)
        p.paragraph_format.space_after = Pt(4)

    doc.add_page_break()

    # ── SECTION 7: DISCLAIMER ──────────────────────────────────────────────────
    h7 = doc.add_heading("7. Disclaimer", level=1)
    h7.runs[0].font.color.rgb = RGBColor(0x0D, 0x1B, 0x2A)
    h7.runs[0].font.size = Pt(16)

    disclaimer = doc.add_paragraph(
        "This report is prepared for research and validation purposes only. Backtested results are "
        "historical simulations and do not represent actual trading performance. Algorithmic trading "
        "involves significant risk of loss. Past performance is not indicative of future results. "
        "The strategies described herein should be thoroughly validated in paper trading before any "
        "live capital deployment. The authors and contributors accept no liability for trading losses "
        "incurred through the application of these strategies."
    )
    disclaimer.runs[0].font.size = Pt(10)
    disclaimer.runs[0].font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    doc.save(str(output_path))
    print(f"Word report saved: {output_path}")


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    excel_out = OUTPUT_DIR / "BankNifty_Algo_Report.xlsx"
    word_out = OUTPUT_DIR / "BankNifty_Algo_Strategy_Report.docx"

    print("Generating Excel report...")
    create_excel_report(excel_out)

    print("Generating Word report...")
    create_word_report(word_out)

    print(f"\nReports complete:")
    print(f"  Excel: {excel_out}")
    print(f"  Word:  {word_out}")