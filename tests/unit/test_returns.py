"""Testes unitários para src/analytics/returns.py. Fixtures sintéticas, isoladas desta suíte."""
import pandas as pd
import pytest

from src.analytics import returns


def test_daily_return_basic():
    close = pd.Series([100.0, 110.0, 99.0])
    result = returns.daily_return(close)
    assert result.iloc[0] != result.iloc[0]  # NaN
    assert result.iloc[1] == pytest.approx(0.10)
    assert result.iloc[2] == pytest.approx(-0.10)


def test_return_n_periods_basic():
    close = pd.Series([100.0, 105.0, 110.0, 121.0])
    result = returns.return_n_periods(close, 2)
    assert pd.isna(result.iloc[0])
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == pytest.approx(0.10)
    assert result.iloc[3] == pytest.approx(0.1523809524, rel=1e-6)


def test_return_n_periods_requires_positive_n():
    close = pd.Series([100.0, 110.0])
    with pytest.raises(ValueError):
        returns.return_n_periods(close, 0)


def test_return_n_periods_insufficient_history_is_nan():
    close = pd.Series([100.0, 105.0])
    result = returns.return_n_periods(close, 5)
    assert result.isna().all()


def test_cumulative_return_since():
    close = pd.Series([100.0, 110.0, 121.0])
    dates = pd.Series(pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]))
    result = returns.cumulative_return_since(close, dates, pd.Timestamp("2026-01-02"))
    assert result == pytest.approx(0.10)


def test_cumulative_return_since_none_when_no_data_in_window():
    close = pd.Series([100.0, 110.0])
    dates = pd.Series(pd.to_datetime(["2026-01-01", "2026-01-02"]))
    result = returns.cumulative_return_since(close, dates, pd.Timestamp("2027-01-01"))
    assert result is None


def test_month_to_date_return():
    close = pd.Series([100.0, 105.0, 110.0])
    dates = pd.Series(pd.to_datetime(["2026-09-30", "2026-10-01", "2026-10-15"]))
    result = returns.month_to_date_return(close, dates)
    assert result == pytest.approx(110.0 / 105.0 - 1)


def test_year_to_date_return():
    close = pd.Series([100.0, 120.0, 150.0])
    dates = pd.Series(pd.to_datetime(["2025-12-31", "2026-01-02", "2026-06-01"]))
    result = returns.year_to_date_return(close, dates)
    assert result == pytest.approx(150.0 / 120.0 - 1)
