"""Execution Convergence Gate: Multi-Stream Decision & Sizing Engine.

Implements the convergent execution architecture for Atlas Live Trading Engine:
Ingests 4 synchronized data streams:
1. Signal Confluence (Fibonacci, Divergence, Potato S&R, Consensus)
2. 31-Model Consensus (Directional agreement, pillar weights, conviction)
3. 6-Tier Risk Citadel (4H SMC macro, BTC dump filter, L2 depth, ADX anti-chop, circuit breaker)
4. Candidate Shadow Telemetry (Forward expectancy, empirical friction, transition gate status)

Computes a deterministic execution verdict, composite dynamic margin sizing, and optimal order type.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class ConfluencePayload:
    """Channel signal conviction, structural targets, and order-flow context."""
    channel: str = "NO_CONFLUENCE"
    side: str = "NO TRADE"
    is_confluent: bool = False
    custom_tp: Optional[float] = None
    custom_sl: Optional[float] = None
    rr_ratio: float = 0.0
    min_rr_required: float = 1.0
    of_desc: str = "Delta Confirmed"


@dataclass
class ConsensusPayload:
    """31-model quantitative consensus vector and pillar strength."""
    total_models: int = 31
    bull_count: int = 0
    bear_count: int = 0
    neutral_count: int = 0
    max_consensus: int = 0
    agreement_pct: float = 0.0
    weighted_score: float = 0.0
    effective_threshold: int = 26


@dataclass
class RiskCitadelPayload:
    """Institutional pre-trade risk clearance and capacity states."""
    smc_4h_ok: bool = True
    smc_bias_desc: str = "4H SMC Bullish"
    btc_macro_ok: bool = True
    btc_macro_desc: str = "BTC Macro Normal"
    adx_val: float = 25.0
    adx_ok: bool = True
    adx_desc: str = "ADX Trending >= 22.0"
    core_gates_ok: bool = True
    core_gates_desc: str = "Core Gates OK"
    ob_ratio: float = 1.20
    portfolio_ok: bool = True
    portfolio_desc: str = "Portfolio Capacity Clear"
    directional_cap_ok: bool = True
    directional_cap_desc: str = "Directional Cap Clear"
    circuit_breaker_ok: bool = True
    circuit_breaker_desc: str = "Circuit Normal"
    cro_ok: bool = True
    cro_desc: str = "CRO Defense Passed"


@dataclass
class ShadowTelemetryPayload:
    """Forward candidate strategy expectancy and empirical market quality."""
    symbol: str = ""
    setup: str = ""
    expectancy_r: float = 0.0
    win_rate: float = 0.0
    net_realized_r: float = 0.0
    sample_size: int = 0
    spread_bps: float = 0.0
    max_spread_bps: float = 15.0
    is_shadow_available: bool = False
    gating_mode: str = "strict"  # "strict", "throttle", "advisory", "disabled"


@dataclass
class ExecutionVerdict:
    """Final unified execution decision produced by the convergence gate."""
    allow_trade: bool = False
    action: str = "NO TRADE"
    symbol: str = ""
    channel: str = "NO_CONFLUENCE"
    base_margin_pct: float = 0.03
    darwinian_mult: float = 1.0
    consensus_scale: float = 1.0
    shadow_scale: float = 1.0
    effective_margin_pct: float = 0.03
    custom_tp: Optional[float] = None
    custom_sl: Optional[float] = None
    order_type: str = "MARKET"  # 'MARKET' or 'MAKER_POST_ONLY'
    rejection_reasons: List[str] = field(default_factory=list)
    telemetry_notes: List[str] = field(default_factory=list)

    @property
    def composite_sizing_mult(self) -> float:
        return self.darwinian_mult * self.consensus_scale * self.shadow_scale


class ExecutionConvergenceGate:
    """Centralized convergence evaluator for multi-stream execution decisions."""

    @staticmethod
    def calc_consensus_scale(max_consensus: int, threshold: int = 26, total_models: int = 31) -> float:
        """Scales position margin dynamically based on consensus conviction (0.8x to 1.35x)."""
        if max_consensus < threshold:
            return 0.80
        excess = max_consensus - threshold
        denom = max(1, total_models - threshold)
        # Linear scale from 1.0x up to 1.35x for unanimous consensus
        return round(1.0 + (0.35 * (excess / denom)), 3)

    @classmethod
    def evaluate(
        cls,
        symbol: str,
        confluence: ConfluencePayload,
        consensus: ConsensusPayload,
        risk: RiskCitadelPayload,
        shadow: ShadowTelemetryPayload,
        base_margin_pct: float = 0.03,
        darwinian_mult: float = 1.0,
    ) -> ExecutionVerdict:
        """Evaluates all 4 streams synchronously and returns a hardened ExecutionVerdict."""
        verdict = ExecutionVerdict(
            allow_trade=False,
            action="NO TRADE",
            symbol=symbol,
            channel=confluence.channel,
            base_margin_pct=base_margin_pct,
            darwinian_mult=darwinian_mult,
            custom_tp=confluence.custom_tp,
            custom_sl=confluence.custom_sl,
        )

        # ---------------------------------------------------------------------
        # 1. Confluence Stream Validation
        # ---------------------------------------------------------------------
        if not confluence.is_confluent or confluence.side not in ["BUY", "SELL"]:
            verdict.rejection_reasons.append(f"No valid confluence signal ({confluence.channel})")
            return verdict

        target_side = confluence.side
        verdict.action = target_side

        # Structural R:R Check
        if confluence.rr_ratio > 0 and confluence.min_rr_required > 0:
            if confluence.rr_ratio < confluence.min_rr_required:
                verdict.rejection_reasons.append(
                    f"Structural R:R {confluence.rr_ratio:.2f} < {confluence.min_rr_required:.2f} minimum requirement"
                )

        # ---------------------------------------------------------------------
        # 2. Risk Citadel Stream Clearance
        # ---------------------------------------------------------------------
        if not risk.circuit_breaker_ok:
            verdict.rejection_reasons.append(f"Circuit Breaker / Min Balance: {risk.circuit_breaker_desc}")
        if not risk.smc_4h_ok:
            verdict.rejection_reasons.append(f"4H Macro / MSS: {risk.smc_bias_desc}")
        if not risk.btc_macro_ok and symbol != "BTCUSDT":
            verdict.rejection_reasons.append(f"BTC Master Beta Filter: {risk.btc_macro_desc}")
        if not risk.adx_ok:
            verdict.rejection_reasons.append(f"ADX Anti-Chop: {risk.adx_desc}")
        if not risk.core_gates_ok:
            verdict.rejection_reasons.append(f"Core Gates: {risk.core_gates_desc}")
        if not risk.directional_cap_ok:
            verdict.rejection_reasons.append(f"Directional Cap: {risk.directional_cap_desc}")
        if not risk.portfolio_ok:
            verdict.rejection_reasons.append(f"Portfolio Margin Capacity: {risk.portfolio_desc}")
        if not risk.cro_ok:
            verdict.rejection_reasons.append(f"CRO Adversarial: {risk.cro_desc}")

        # ---------------------------------------------------------------------
        # 3. Consensus Stream Scaling
        # ---------------------------------------------------------------------
        consensus_scale = cls.calc_consensus_scale(
            consensus.max_consensus,
            threshold=consensus.effective_threshold,
            total_models=consensus.total_models,
        )
        verdict.consensus_scale = consensus_scale
        verdict.telemetry_notes.append(
            f"Consensus: {consensus.max_consensus}/{consensus.total_models} models ({consensus.agreement_pct}%) -> {consensus_scale}x scale"
        )

        # ---------------------------------------------------------------------
        # 4. Shadow Telemetry Stream Feedback & Friction Guard
        # ---------------------------------------------------------------------
        shadow_scale = 1.0
        gating = shadow.gating_mode.lower() if shadow.gating_mode else "strict"

        if shadow.is_shadow_available and gating != "disabled":
            # Spread friction check
            if shadow.spread_bps > 0 and shadow.max_spread_bps > 0:
                if shadow.spread_bps > shadow.max_spread_bps:
                    if gating == "strict":
                        verdict.rejection_reasons.append(
                            f"Shadow Spread Friction ({shadow.spread_bps:.1f} bps > {shadow.max_spread_bps:.1f} bps cap)"
                        )
                    else:
                        verdict.order_type = "MAKER_POST_ONLY"
                        verdict.telemetry_notes.append(
                            f"High spread {shadow.spread_bps:.1f} bps -> routed as MAKER_POST_ONLY"
                        )
                elif shadow.spread_bps > (shadow.max_spread_bps * 0.65):
                    verdict.order_type = "MAKER_POST_ONLY"
                    verdict.telemetry_notes.append(
                        f"Moderate spread {shadow.spread_bps:.1f} bps -> routed as MAKER_POST_ONLY"
                    )

            # Forward expectancy gating (minimum 5 trades required to activate statistical gating)
            if shadow.sample_size >= 5:
                if shadow.expectancy_r < 0:
                    if gating == "strict":
                        verdict.rejection_reasons.append(
                            f"Shadow Expectancy Negative for {symbol} ({shadow.expectancy_r:+.3f} R over {shadow.sample_size} trades)"
                        )
                    elif gating == "throttle":
                        shadow_scale = 0.50
                        verdict.telemetry_notes.append(
                            f"Shadow Expectancy Negative ({shadow.expectancy_r:+.3f} R) -> Throttle sizing to 0.50x"
                        )
                elif shadow.expectancy_r > 0.10:
                    # High alpha bonus scale up to 1.15x
                    shadow_scale = min(1.15, 1.0 + (shadow.expectancy_r * 0.15))
                    verdict.telemetry_notes.append(
                        f"Shadow Expectancy High ({shadow.expectancy_r:+.3f} R) -> Boost sizing to {shadow_scale:.2f}x"
                    )

        verdict.shadow_scale = shadow_scale

        # ---------------------------------------------------------------------
        # 5. Composite Sizing & Final Verdict Formulation
        # ---------------------------------------------------------------------
        effective_margin = base_margin_pct * darwinian_mult * consensus_scale * shadow_scale
        # Institutional safety bound: margin must remain between 0.5% and 10%
        effective_margin = max(0.005, min(0.10, effective_margin))
        verdict.effective_margin_pct = round(effective_margin, 5)

        if not verdict.rejection_reasons:
            verdict.allow_trade = True
            verdict.telemetry_notes.append(
                f"✅ ALL 4 STREAMS CONVERGED: Margin={verdict.effective_margin_pct*100:.2f}% (Base={base_margin_pct*100:.1f}%, Darwin={darwinian_mult}x, Consensus={consensus_scale}x, Shadow={shadow_scale}x)"
            )
        else:
            verdict.action = "NO TRADE"

        return verdict
