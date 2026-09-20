from pathlib import Path
import pandas as pd
import pytest
from backtests.continuous_regression import validate, EXPECTED


def test_validate_open_time_schema(tmp_path: Path):
    csv_file = tmp_path / "TEST_15m_open_time.csv"
    df = pd.DataFrame({
        'open_time': ['2026-01-01 00:00:00+00:00', '2026-01-01 00:15:00+00:00', '2026-01-01 00:30:00+00:00'],
        'close': [100.0, 101.0, 102.0]
    })
    df.to_csv(csv_file, index=False)
    assert validate(csv_file) == 3


def test_validate_timestamp_schema(tmp_path: Path):
    csv_file = tmp_path / "TEST_15m_timestamp.csv"
    df = pd.DataFrame({
        'timestamp': ['2026-01-01 00:00:00+00:00', '2026-01-01 00:15:00+00:00', '2026-01-01 00:30:00+00:00'],
        'close': [100.0, 101.0, 102.0]
    })
    df.to_csv(csv_file, index=False)
    assert validate(csv_file) == 3


def test_validate_detects_gap(tmp_path: Path):
    csv_file = tmp_path / "TEST_15m_gap.csv"
    df = pd.DataFrame({
        'open_time': ['2026-01-01 00:00:00+00:00', '2026-01-01 00:45:00+00:00'],
        'close': [100.0, 101.0]
    })
    df.to_csv(csv_file, index=False)
    with pytest.raises(ValueError, match="non-15m gap detected"):
        validate(csv_file)


def test_validate_detects_duplicate(tmp_path: Path):
    csv_file = tmp_path / "TEST_15m_dup.csv"
    df = pd.DataFrame({
        'open_time': ['2026-01-01 00:00:00+00:00', '2026-01-01 00:00:00+00:00'],
        'close': [100.0, 101.0]
    })
    df.to_csv(csv_file, index=False)
    with pytest.raises(ValueError, match="duplicate timestamps"):
        validate(csv_file)
