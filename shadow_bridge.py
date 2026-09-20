"""Shadow State Bridge: Live Telemetry Ingestion & Forward Robustness Interface.

Enables thread-safe, cached ingestion of Candidate V9.3.1 shadow telemetry from disk:
- Reads telemetry_summary.json and open_positions.json with mtime-debounced caching.
- Extracts asset-level and setup-level empirical forward expectancy and win rates.
- Constructs ShadowTelemetryPayload for direct ingestion into the ExecutionConvergenceGate.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import Lock
from typing import Optional, Dict, Any, Tuple

from execution_convergence import ShadowTelemetryPayload

DEFAULT_SHADOW_DIR = Path("data") / "shadow_v9_3_1"


class ShadowStateBridge:
    """Thread-safe interface reading candidate shadow telemetry to inform live execution."""

    def __init__(self, data_dir: Path = DEFAULT_SHADOW_DIR, cache_ttl_sec: float = 5.0):
        self.data_dir = Path(data_dir)
        self.summary_file = self.data_dir / "telemetry_summary.json"
        self.positions_file = self.data_dir / "open_positions.json"
        self.cache_ttl = cache_ttl_sec
        self._lock = Lock()

        self._last_summary_read = 0.0
        self._summary_mtime = 0.0
        self._cached_summary: Dict[str, Any] = {}

        self._last_positions_read = 0.0
        self._positions_mtime = 0.0
        self._cached_positions: Dict[str, Any] = {}

    def get_summary(self) -> Dict[str, Any]:
        """Loads and returns telemetry_summary.json with mtime and TTL caching."""
        with self._lock:
            now = time.time()
            if not self.summary_file.exists():
                return {}

            try:
                mtime = self.summary_file.stat().st_mtime
                if (now - self._last_summary_read < self.cache_ttl) and (mtime == self._summary_mtime):
                    return self._cached_summary

                with open(self.summary_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._cached_summary = data
                    self._summary_mtime = mtime
                    self._last_summary_read = now
                    return data
            except Exception as e:
                # On transient concurrent write, return last cached snapshot
                return self._cached_summary

    def get_open_positions(self) -> Dict[str, Any]:
        """Loads open_positions.json with mtime and TTL caching."""
        with self._lock:
            now = time.time()
            if not self.positions_file.exists():
                return {}

            try:
                mtime = self.positions_file.stat().st_mtime
                if (now - self._last_positions_read < self.cache_ttl) and (mtime == self._positions_mtime):
                    return self._cached_positions

                with open(self.positions_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._cached_positions = data.get("open_positions", {})
                    self._positions_mtime = mtime
                    self._last_positions_read = now
                    return self._cached_positions
            except Exception:
                return self._cached_positions

    def get_asset_telemetry(self, symbol: str) -> Dict[str, Any]:
        """Returns empirical telemetry for a specific symbol."""
        summary = self.get_summary()
        by_symbol = summary.get("by_symbol", {})
        sym_data = by_symbol.get(symbol, {})
        trades = sym_data.get("trades", 0)
        net_r = float(sym_data.get("net_r", 0.0))
        win_rate = float(sym_data.get("win_rate", 0.0))
        expectancy_r = (net_r / trades) if trades > 0 else 0.0
        return {
            "trades": trades,
            "net_r": net_r,
            "win_rate": win_rate,
            "expectancy_r": expectancy_r,
        }

    def get_setup_telemetry(self, setup_name: str) -> Dict[str, Any]:
        """Returns empirical telemetry for a specific candidate setup."""
        summary = self.get_summary()
        by_setup = summary.get("by_setup", {})
        setup_data = by_setup.get(setup_name, {})
        trades = setup_data.get("trades", 0)
        net_r = float(setup_data.get("net_r", 0.0))
        win_rate = float(setup_data.get("win_rate", 0.0))
        expectancy_r = (net_r / trades) if trades > 0 else 0.0
        return {
            "trades": trades,
            "net_r": net_r,
            "win_rate": win_rate,
            "expectancy_r": expectancy_r,
        }

    def build_shadow_payload(
        self,
        symbol: str,
        setup: str = "",
        gating_mode: str = "strict",
        spread_bps: float = 0.0,
        max_spread_bps: float = 15.0,
    ) -> ShadowTelemetryPayload:
        """Constructs a ShadowTelemetryPayload for execution convergence."""
        summary = self.get_summary()
        if not summary:
            return ShadowTelemetryPayload(
                symbol=symbol,
                setup=setup,
                is_shadow_available=False,
                gating_mode=gating_mode,
            )

        asset_stat = self.get_asset_telemetry(symbol)
        trades = asset_stat["trades"]
        net_r = asset_stat["net_r"]
        win_rate = asset_stat["win_rate"]
        expectancy_r = asset_stat["expectancy_r"]

        # If asset has no trades, check setup-level statistics if available
        if trades == 0 and setup:
            setup_stat = self.get_setup_telemetry(setup)
            if setup_stat["trades"] > 0:
                trades = setup_stat["trades"]
                net_r = setup_stat["net_r"]
                win_rate = setup_stat["win_rate"]
                expectancy_r = setup_stat["expectancy_r"]

        return ShadowTelemetryPayload(
            symbol=symbol,
            setup=setup,
            expectancy_r=expectancy_r,
            win_rate=win_rate,
            net_realized_r=net_r,
            sample_size=trades,
            spread_bps=spread_bps,
            max_spread_bps=max_spread_bps,
            is_shadow_available=True,
            gating_mode=gating_mode,
        )
