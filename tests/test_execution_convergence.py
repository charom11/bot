"""Unit tests for the Execution Convergence Gate."""
from __future__ import annotations

import pytest
from execution_convergence import (
    ConfluencePayload,
    ConsensusPayload,
    RiskCitadelPayload,
    ShadowTelemetryPayload,
    ExecutionConvergenceGate,
)


def test_confluence_missing():
    """No trade allowed when confluence signal is absent."""
    confluence = ConfluencePayload(channel="NO_CONFLUENCE", side="NO TRADE", is_confluent=False)
    consensus = ConsensusPayload(max_consensus=28)
    risk = RiskCitadelPayload()
    shadow = ShadowTelemetryPayload(is_shadow_available=False)

    verdict = ExecutionConvergenceGate.evaluate("BTCUSDT", confluence, consensus, risk, shadow)
    assert not verdict.allow_trade
    assert verdict.action == "NO TRADE"
    assert any("No valid confluence" in r for r in verdict.rejection_reasons)


def test_risk_citadel_veto():
    """Trade must be vetoed if any Risk Citadel guard trips."""
    confluence = ConfluencePayload(channel="FIB_POCKET", side="BUY", is_confluent=True, custom_tp=105.0, custom_sl=95.0)
    consensus = ConsensusPayload(max_consensus=28)
    shadow = ShadowTelemetryPayload(is_shadow_available=False)

    # Trip Circuit Breaker
    risk = RiskCitadelPayload(circuit_breaker_ok=False, circuit_breaker_desc="5 consecutive losses")
    verdict = ExecutionConvergenceGate.evaluate("BTCUSDT", confluence, consensus, risk, shadow)
    assert not verdict.allow_trade
    assert any("Circuit Breaker" in r for r in verdict.rejection_reasons)

    # Trip 4H Macro SMC
    risk2 = RiskCitadelPayload(smc_4h_ok=False, smc_bias_desc="4H Bearish Order Block opposes Long")
    verdict2 = ExecutionConvergenceGate.evaluate("SOLUSDT", confluence, consensus, risk2, shadow)
    assert not verdict2.allow_trade
    assert any("4H Macro" in r for r in verdict2.rejection_reasons)

    # Trip ADX Anti-Chop
    risk3 = RiskCitadelPayload(adx_ok=False, adx_desc="ADX 18.2 < 22.0 Range Chop")
    verdict3 = ExecutionConvergenceGate.evaluate("ETHUSDT", confluence, consensus, risk3, shadow)
    assert not verdict3.allow_trade
    assert any("ADX Anti-Chop" in r for r in verdict3.rejection_reasons)


def test_shadow_expectancy_strict_veto():
    """Strict gating mode must veto trade if shadow expectancy is negative over >= 5 trades."""
    confluence = ConfluencePayload(channel="FIB_POCKET", side="BUY", is_confluent=True, custom_tp=105.0, custom_sl=95.0)
    consensus = ConsensusPayload(max_consensus=29)
    risk = RiskCitadelPayload()
    shadow = ShadowTelemetryPayload(
        symbol="BTCUSDT",
        expectancy_r=-0.45,
        sample_size=9,
        is_shadow_available=True,
        gating_mode="strict",
    )

    verdict = ExecutionConvergenceGate.evaluate("BTCUSDT", confluence, consensus, risk, shadow)
    assert not verdict.allow_trade
    assert any("Shadow Expectancy Negative" in r for r in verdict.rejection_reasons)


def test_shadow_expectancy_throttle_mode():
    """Throttle gating mode allows the trade but halves shadow sizing multiplier."""
    confluence = ConfluencePayload(channel="FIB_POCKET", side="BUY", is_confluent=True, custom_tp=105.0, custom_sl=95.0)
    consensus = ConsensusPayload(max_consensus=28, effective_threshold=26)
    risk = RiskCitadelPayload()
    shadow = ShadowTelemetryPayload(
        symbol="BTCUSDT",
        expectancy_r=-0.35,
        sample_size=9,
        is_shadow_available=True,
        gating_mode="throttle",
    )

    verdict = ExecutionConvergenceGate.evaluate(
        "BTCUSDT", confluence, consensus, risk, shadow, base_margin_pct=0.04, darwinian_mult=1.0
    )
    assert verdict.allow_trade
    assert verdict.action == "BUY"
    assert verdict.shadow_scale == 0.50
    # Effective margin must reflect the 0.50x throttling
    assert verdict.effective_margin_pct < 0.04


def test_all_streams_converged_healthy():
    """When all 4 streams clear with positive telemetry, trade is allowed with dynamic scaling."""
    confluence = ConfluencePayload(
        channel="POTATO_SR",
        side="BUY",
        is_confluent=True,
        custom_tp=110.0,
        custom_sl=90.0,
        rr_ratio=2.0,
        min_rr_required=1.5,
    )
    consensus = ConsensusPayload(
        total_models=31,
        max_consensus=31,  # Unanimous
        effective_threshold=26,
        agreement_pct=100.0,
    )
    risk = RiskCitadelPayload()
    shadow = ShadowTelemetryPayload(
        symbol="SOLUSDT",
        expectancy_r=0.25,
        sample_size=12,
        spread_bps=2.5,
        max_spread_bps=12.0,
        is_shadow_available=True,
        gating_mode="strict",
    )

    verdict = ExecutionConvergenceGate.evaluate(
        "SOLUSDT", confluence, consensus, risk, shadow, base_margin_pct=0.03, darwinian_mult=1.2
    )
    assert verdict.allow_trade
    assert verdict.action == "BUY"
    assert verdict.consensus_scale == 1.35  # Max scale for 31/31
    assert verdict.shadow_scale > 1.0       # Alpha boost for positive expectancy
    assert verdict.order_type == "MARKET"
    assert len(verdict.rejection_reasons) == 0


def test_spread_friction_maker_routing():
    """Elevated spread routes order to MAKER_POST_ONLY rather than aggressive taker."""
    confluence = ConfluencePayload(channel="DIVERGENCE", side="SELL", is_confluent=True, custom_tp=90.0, custom_sl=110.0)
    consensus = ConsensusPayload(max_consensus=27)
    risk = RiskCitadelPayload()
    shadow = ShadowTelemetryPayload(
        symbol="APTUSDT",
        spread_bps=9.5,      # > 65% of max_spread (12.0)
        max_spread_bps=12.0,
        is_shadow_available=True,
        gating_mode="throttle",
    )

    verdict = ExecutionConvergenceGate.evaluate("APTUSDT", confluence, consensus, risk, shadow)
    assert verdict.allow_trade
    assert verdict.order_type == "MAKER_POST_ONLY"
