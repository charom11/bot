import json
import os
from pathlib import Path
import pytest
import main
from backtests.reconcile_pnl_ledger import reconcile_ledger


def test_load_position_targets_prunes_closed_positions(tmp_path, monkeypatch):
    """
    Verifies that on engine restart, _load_position_targets authoritatively
    compares local target state against live Binance positions and prunes
    stale targets whose positions are already closed on exchange.
    """
    temp_targets_file = tmp_path / "active_position_targets.json"
    initial_targets = {
        "BTCUSDT": {
            "side": "BUY",
            "entry_price": 60000.0,
            "tp1": 61000.0,
            "current_sl": 59500.0,
            "channel": "FIBONACCI"
        },
        "ETHUSDT": {
            "side": "SELL",
            "entry_price": 3000.0,
            "tp1": 2900.0,
            "current_sl": 3050.0,
            "channel": "POTATO_SR"
        }
    }
    temp_targets_file.write_text(json.dumps(initial_targets, indent=2), encoding="utf-8")
    monkeypatch.setattr(main, "_POSITION_TARGETS_FILE", str(temp_targets_file))

    # Mock Binance returning ONLY BTCUSDT active (ETHUSDT is already closed)
    mock_positions = [
        {"symbol": "BTCUSDT", "positionAmt": "0.05", "entryPrice": "60000.0"}
    ]
    monkeypatch.setattr(main, "get_binance_futures_positions", lambda: mock_positions)

    main.ACTIVE_POSITION_TARGETS.clear()
    main._load_position_targets()

    # BTCUSDT must be preserved
    assert "BTCUSDT" in main.ACTIVE_POSITION_TARGETS
    assert main.ACTIVE_POSITION_TARGETS["BTCUSDT"]["entry_price"] == 60000.0

    # ETHUSDT must be pruned
    assert "ETHUSDT" not in main.ACTIVE_POSITION_TARGETS

    # File on disk must also be updated with pruned state
    disk_data = json.loads(temp_targets_file.read_text(encoding="utf-8"))
    assert "BTCUSDT" in disk_data
    assert "ETHUSDT" not in disk_data

    # Cleanup memory
    main.ACTIVE_POSITION_TARGETS.clear()


def test_load_position_targets_preserves_on_api_outage(tmp_path, monkeypatch):
    """
    Verifies that if Binance API is unreachable during boot (TradingStateUnavailable),
    local target state is safely retained rather than wiped out.
    """
    temp_targets_file = tmp_path / "active_position_targets.json"
    initial_targets = {
        "SOLUSDT": {
            "side": "BUY",
            "entry_price": 150.0,
            "current_sl": 145.0,
            "channel": "POTATO_SR"
        }
    }
    temp_targets_file.write_text(json.dumps(initial_targets, indent=2), encoding="utf-8")
    monkeypatch.setattr(main, "_POSITION_TARGETS_FILE", str(temp_targets_file))

    # Mock API outage returning None
    monkeypatch.setattr(main, "get_binance_futures_positions", lambda: None)

    main.ACTIVE_POSITION_TARGETS.clear()
    main._load_position_targets()

    # Targets must be safely preserved
    assert "SOLUSDT" in main.ACTIVE_POSITION_TARGETS
    assert main.ACTIVE_POSITION_TARGETS["SOLUSDT"]["entry_price"] == 150.0

    main.ACTIVE_POSITION_TARGETS.clear()


def test_reconcile_pnl_ledger_metrics(tmp_path):
    """
    Verifies that reconcile_ledger computes accurate trade counts, win rate,
    profit factor, channel attribution, and account reconciliation.
    """
    ledger_file = tmp_path / "test_ledger.jsonl"
    events = [
        {"time_ms": 1000, "symbol": "BTCUSDT", "income": 5.00, "channel": "FIBONACCI"},
        {"time_ms": 2000, "symbol": "ETHUSDT", "income": -2.00, "channel": "POTATO_SR"},
        {"time_ms": 3000, "symbol": "SOLUSDT", "income": 8.00, "channel": "FIBONACCI"},
        {"time_ms": 4000, "symbol": "LINKUSDT", "income": -1.00, "channel": "DIVERGENCE"}
    ]
    with ledger_file.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")

    res = reconcile_ledger(ledger_file, start_balance=100.0, current_balance=110.0)

    assert res["status"] == "OK"
    assert res["trades_count"] == 4
    assert res["wins"] == 2
    assert res["losses"] == 2
    assert res["total_realized_pnl"] == 10.00
    assert res["win_rate_pct"] == 50.0
    assert res["profit_factor"] == round(13.0 / 3.0, 2)
    assert res["channels"]["FIBONACCI"]["net_pnl"] == 13.0
    assert res["channels"]["POTATO_SR"]["net_pnl"] == -2.0
    assert res["reconciliation"]["reconciled"] is True
    assert res["reconciliation"]["discrepancy"] == 0.0
