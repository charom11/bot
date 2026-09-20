#!/usr/bin/env python3
"""Atlas Realized P&L Ledger & Reconciliation Tool.

Reads data/state/realized_trade_ledger.jsonl and computes performance attribution,
streak analysis, channel breakdown, and reconciliation against account equity.
"""

from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from typing import Dict, List, Any


def reconcile_ledger(
    ledger_path: Path,
    start_balance: float = None,
    current_balance: float = None
) -> Dict[str, Any]:
    if not ledger_path.exists():
        return {
            "status": "EMPTY",
            "trades_count": 0,
            "total_realized_pnl": 0.0,
            "message": f"Ledger file not found: {ledger_path}"
        }

    records: List[Dict[str, Any]] = []
    with ledger_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue

    if not records:
        return {
            "status": "EMPTY",
            "trades_count": 0,
            "total_realized_pnl": 0.0,
            "message": "No valid trade records found in ledger."
        }

    total_pnl = 0.0
    wins = 0
    losses = 0
    gross_wins = 0.0
    gross_losses = 0.0
    streak = 0
    max_streak = 0
    channel_stats: Dict[str, Dict[str, Any]] = {}
    symbol_stats: Dict[str, Dict[str, Any]] = {}

    for r in records:
        pnl = float(r.get("income", 0.0))
        sym = r.get("symbol", "UNKNOWN")
        ch = r.get("channel", "UNKNOWN")

        total_pnl += pnl

        if pnl > 0:
            wins += 1
            gross_wins += pnl
            streak = 0
        elif pnl < 0:
            losses += 1
            gross_losses += abs(pnl)
            streak += 1
            max_streak = max(max_streak, streak)

        # Channel attribution
        if ch not in channel_stats:
            channel_stats[ch] = {"trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0}
        channel_stats[ch]["trades"] += 1
        channel_stats[ch]["net_pnl"] += pnl
        if pnl > 0:
            channel_stats[ch]["wins"] += 1
        elif pnl < 0:
            channel_stats[ch]["losses"] += 1

        # Symbol attribution
        if sym not in symbol_stats:
            symbol_stats[sym] = {"trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0}
        symbol_stats[sym]["trades"] += 1
        symbol_stats[sym]["net_pnl"] += pnl
        if pnl > 0:
            symbol_stats[sym]["wins"] += 1
        elif pnl < 0:
            symbol_stats[sym]["losses"] += 1

    total_trades = len(records)
    win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
    profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else (999.0 if gross_wins > 0 else 0.0)

    result = {
        "status": "OK",
        "trades_count": total_trades,
        "total_realized_pnl": round(total_pnl, 4),
        "win_rate_pct": round(win_rate, 2),
        "wins": wins,
        "losses": losses,
        "profit_factor": round(profit_factor, 2),
        "max_loss_streak": max_streak,
        "channels": channel_stats,
        "symbols": symbol_stats,
    }

    if start_balance is not None and current_balance is not None:
        expected_balance = start_balance + total_pnl
        discrepancy = current_balance - expected_balance
        result["reconciliation"] = {
            "start_balance": start_balance,
            "current_balance": current_balance,
            "expected_balance": round(expected_balance, 4),
            "discrepancy": round(discrepancy, 4),
            "reconciled": abs(discrepancy) < 0.01
        }

    return result


def main():
    parser = argparse.ArgumentParser(description="Reconcile Atlas trade ledger")
    parser.add_argument("--ledger", default="data/state/realized_trade_ledger.jsonl", help="Path to trade ledger JSONL")
    parser.add_argument("--start-balance", type=float, default=None, help="Initial wallet balance")
    parser.add_argument("--current-balance", type=float, default=None, help="Current wallet balance")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    args = parser.parse_args()

    res = reconcile_ledger(Path(args.ledger), args.start_balance, args.current_balance)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print("\n=======================================================")
        print("          ATLAS REALIZED P&L RECONCILIATION            ")
        print("=======================================================")
        print(f"Status:             {res.get('status')}")
        print(f"Total Trades:       {res.get('trades_count')}")
        print(f"Total Realized PnL: ${res.get('total_realized_pnl', 0.0):+,.4f} USDT")
        print(f"Win Rate:           {res.get('win_rate_pct', 0.0):.1f}% ({res.get('wins', 0)}W / {res.get('losses', 0)}L)")
        print(f"Profit Factor:      {res.get('profit_factor', 0.0):.2f}")
        print(f"Max Loss Streak:    {res.get('max_loss_streak', 0)}")
        print("-------------------------------------------------------")
        print("Channel Attribution:")
        for ch, data in res.get("channels", {}).items():
            print(f"  • {ch:<18}: {data['trades']} trades | Net: ${data['net_pnl']:+,.4f}")
        if "reconciliation" in res:
            rec = res["reconciliation"]
            print("-------------------------------------------------------")
            print(f"Reconciliation:     {'MATCHED 🟢' if rec['reconciled'] else 'DISCREPANCY ⚠️'}")
            print(f"  Start Balance:    ${rec['start_balance']:,.2f}")
            print(f"  Current Balance:  ${rec['current_balance']:,.2f}")
            print(f"  Expected Balance: ${rec['expected_balance']:,.2f}")
            print(f"  Discrepancy:      ${rec['discrepancy']:+,.4f}")
        print("=======================================================\n")


if __name__ == "__main__":
    main()
