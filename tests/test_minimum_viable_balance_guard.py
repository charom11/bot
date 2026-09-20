import pytest
import main


def test_minimum_viable_balance_halts_on_sub_floor_equity(monkeypatch):
    """
    Verifies that CircuitBreakerManager enters a persistent HALTED state
    when equity falls below the minimum viable trading floor ($5.00 USDT).
    """
    cb = main.CircuitBreakerManager(daily_drawdown_limit_pct=0.06, max_consecutive_losses=3, min_viable_balance=5.0)
    cb.daily_start_balance = 20.0

    # Mock telegram broadcast to avoid external network calls during testing
    monkeypatch.setattr(main, "send_telegram_msg", lambda *a, **kw: None)

    # 1. Equity of $4.20 is below $5.00 floor -> Must persistently HALT
    assert cb.check_and_update(4.20) is False
    assert cb.circuit_tripped is True
    assert cb.circuit_tripped_until == float("inf")
    assert "below minimum viable trading floor" in cb.trip_reason

    # 2. Subsequent check while still starved remains persistently HALTED
    assert cb.check_and_update(3.90) is False
    assert cb.circuit_tripped is True
    assert cb.circuit_tripped_until == float("inf")

    # 3. Account gets refunded to $25.00 -> Automatically un-halts and restores trading
    assert cb.check_and_update(25.0) is True
    assert cb.circuit_tripped is False
    assert cb.circuit_tripped_until == 0
    assert cb.trip_reason == ""


def test_minimum_viable_balance_custom_floor(monkeypatch):
    """
    Verifies that a custom minimum viable balance floor (e.g. $10.00 USDT)
    is respected.
    """
    cb = main.CircuitBreakerManager(min_viable_balance=10.0)
    monkeypatch.setattr(main, "send_telegram_msg", lambda *a, **kw: None)

    # $8.50 is below custom $10.00 floor
    assert cb.check_and_update(8.50) is False
    assert cb.circuit_tripped is True
    assert "$10.00 USDT" in cb.trip_reason

    # $12.00 is above floor
    assert cb.check_and_update(12.00) is True
    assert cb.circuit_tripped is False


def test_minimum_viable_balance_disabled_when_zero(monkeypatch):
    """
    Verifies that setting min_viable_balance=0.0 disables the floor check.
    """
    cb = main.CircuitBreakerManager(min_viable_balance=0.0)
    monkeypatch.setattr(main, "send_telegram_msg", lambda *a, **kw: None)

    # With floor=0, $1.50 is allowed
    assert cb.check_and_update(1.50) is True
    assert cb.circuit_tripped is False


def test_circuit_breaker_disabled_bypasses_balance_check(monkeypatch):
    """
    Verifies that when circuit breaker is disabled, check_and_update returns True.
    """
    cb = main.CircuitBreakerManager(min_viable_balance=5.0)
    cb.set_enabled(False)
    monkeypatch.setattr(main, "send_telegram_msg", lambda *a, **kw: None)

    assert cb.check_and_update(1.00) is True
    assert cb.circuit_tripped is False
