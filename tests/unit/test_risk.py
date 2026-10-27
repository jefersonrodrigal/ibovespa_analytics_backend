import numpy as np
import pandas as pd
import pytest

from src.analytics import returns, risk


def test_drawdown_zero_at_new_high():
    close = pd.Series([100.0, 110.0, 120.0])
    dd = risk.drawdown(close)
    assert dd.iloc[-1] == pytest.approx(0.0)


def test_drawdown_negative_after_fall():
    close = pd.Series([100.0, 120.0, 90.0])
    dd = risk.drawdown(close)
    assert dd.iloc[-1] == pytest.approx(90.0 / 120.0 - 1)


def test_max_drawdown():
    close = pd.Series([100.0, 120.0, 90.0, 95.0, 130.0])
    dd = risk.drawdown(close)
    mdd = risk.max_drawdown(dd)
    assert mdd == pytest.approx(90.0 / 120.0 - 1)


def test_max_drawdown_empty_series_is_none():
    assert risk.max_drawdown(pd.Series([], dtype=float)) is None


def test_rolling_volatility_annualized_known_value():
    # retornos constantes de 1% ao dia -> desvio-padrão = 0
    close = pd.Series([100 * (1.01 ** i) for i in range(10)])
    daily_ret = returns.daily_return(close)
    vol = risk.rolling_volatility_annualized(daily_ret, 5)
    assert vol.dropna().iloc[-1] == pytest.approx(0.0, abs=1e-9)


def test_rolling_volatility_insufficient_history_is_nan():
    daily_ret = pd.Series([0.01, -0.01])
    vol = risk.rolling_volatility_annualized(daily_ret, 21)
    assert vol.isna().all()


def test_returns_distribution_empty():
    stats = risk.returns_distribution(pd.Series([np.nan, np.nan]))
    assert stats["count"] == 0
    assert stats["mean"] is None


def test_returns_distribution_basic():
    stats = risk.returns_distribution(pd.Series([0.01, -0.02, 0.03, 0.0]))
    assert stats["count"] == 4
    assert stats["min"] == pytest.approx(-0.02)
    assert stats["max"] == pytest.approx(0.03)


def test_best_worst_days():
    dates = pd.Series(pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]))
    rets = pd.Series([0.05, -0.03, 0.01])
    result = risk.best_worst_days(dates, rets, n=1)
    assert result["best"][0]["daily_return"] == pytest.approx(0.05)
    assert result["worst"][0]["daily_return"] == pytest.approx(-0.03)
