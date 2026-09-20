"""Unit tests for the Shadow State Bridge."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from shadow_bridge import ShadowStateBridge


def test_shadow_bridge_live_disk_read():
    """Verify ShadowStateBridge reads the committed shadow telemetry in data/shadow_v9_3_1."""
    bridge = ShadowStateBridge(data_dir=Path("data") / "shadow_v9_3_1")
    summary = bridge.get_summary()

    assert isinstance(summary, dict)
    assert summary.get("candidate") == "V9.3.1"
    assert "by_symbol" in summary
    assert "by_setup" in summary

    # Test asset telemetry extraction
    btc_data = bridge.get_asset_telemetry("BTCUSDT")
    assert btc_data["trades"] == 9
    assert btc_data["win_rate"] == pytest.approx(0.2222, rel=1e-2)
    assert btc_data["net_r"] == pytest.approx(-4.034, rel=1e-2)
    assert btc_data["expectancy_r"] == pytest.approx(-4.034 / 9, rel=1e-2)


def test_shadow_bridge_payload_construction():
    """Verify build_shadow_payload produces proper dataclass with empirical values."""
    bridge = ShadowStateBridge(data_dir=Path("data") / "shadow_v9_3_1")
    payload = bridge.build_shadow_payload(
        symbol="BTCUSDT",
        setup="MSS_SHIFT",
        gating_mode="strict",
        spread_bps=3.2,
        max_spread_bps=15.0,
    )

    assert payload.symbol == "BTCUSDT"
    assert payload.setup == "MSS_SHIFT"
    assert payload.sample_size == 9
    assert payload.expectancy_r < 0  # From telemetry
    assert payload.is_shadow_available is True
    assert payload.spread_bps == 3.2
    assert payload.gating_mode == "strict"


def test_shadow_bridge_missing_dir_fallback(tmp_path):
    """Graceful degradation when shadow telemetry path does not exist."""
    fake_dir = tmp_path / "non_existent_shadow"
    bridge = ShadowStateBridge(data_dir=fake_dir)

    summary = bridge.get_summary()
    assert summary == {}

    payload = bridge.build_shadow_payload(symbol="ETHUSDT", gating_mode="strict")
    assert payload.symbol == "ETHUSDT"
    assert payload.is_shadow_available is False
    assert payload.sample_size == 0
    assert payload.expectancy_r == 0.0
