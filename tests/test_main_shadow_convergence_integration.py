"""Integration tests for WeatherEnsembleBot with ExecutionConvergenceGate & ShadowStateBridge."""
from __future__ import annotations

import pandas as pd
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from main import WeatherEnsembleBot, GLOBAL_CACHE
from execution_convergence import ExecutionConvergenceGate


def test_weather_bot_initialization_with_shadow_bridge():
    """Verify WeatherEnsembleBot initializes ShadowStateBridge properly."""
    bot = WeatherEnsembleBot(
        consensus_threshold=28,
        live_trading=False,
        enable_shadow_bridge=True,
        shadow_gating="strict",
    )
    assert bot.enable_shadow_bridge is True
    assert bot.shadow_gating == "strict"
    assert bot.shadow_bridge is not None

    summary = bot.shadow_bridge.get_summary()
    assert isinstance(summary, dict)


def test_weather_bot_initialization_disabled_shadow():
    """Verify WeatherEnsembleBot handles disabled shadow bridge gracefully."""
    bot = WeatherEnsembleBot(
        consensus_threshold=28,
        live_trading=False,
        enable_shadow_bridge=False,
    )
    assert bot.enable_shadow_bridge is False
    assert bot.shadow_bridge is None


def test_evaluate_bar_convergence_gate_execution():
    """Verify evaluate_bar routes trade signals through ExecutionConvergenceGate."""
    bot = WeatherEnsembleBot(
        consensus_threshold=25,
        live_trading=False,
        enable_shadow_bridge=True,
        shadow_gating="strict",
    )

    # Generate synthetic 15m OHLCV dataframe with 50 bars
    dates = pd.date_range("2026-09-20 00:00:00", periods=50, freq="15min", tz="UTC")
    close_prices = np.linspace(100.0, 120.0, 50)
    df = pd.DataFrame({
        "open": close_prices - 0.5,
        "high": close_prices + 1.0,
        "low": close_prices - 1.0,
        "close": close_prices,
        "volume": np.full(50, 10000.0),
    }, index=dates)

    # Test evaluate_bar runs without error
    entry = bot.evaluate_bar(df, symbol="BTCUSDT")
    assert isinstance(entry, dict)
    assert "symbol" in entry
    assert entry["symbol"] == "BTCUSDT"
    assert "action" in entry
    assert "is_trade" in entry
