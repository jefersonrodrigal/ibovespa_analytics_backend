import pandas as pd
import pytest

from src.analytics import moving_averages


def test_moving_average_basic():
    close = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    ma = moving_averages.moving_average(close, 3)
    assert pd.isna(ma.iloc[0])
    assert pd.isna(ma.iloc[1])
    assert ma.iloc[2] == pytest.approx(2.0)
    assert ma.iloc[3] == pytest.approx(3.0)
    assert ma.iloc[4] == pytest.approx(4.0)


def test_moving_average_insufficient_history_all_nan():
    close = pd.Series([1.0, 2.0])
    ma = moving_averages.moving_average(close, 5)
    assert ma.isna().all()


def test_distance_from_ma_pct():
    close = pd.Series([110.0])
    ma = pd.Series([100.0])
    result = moving_averages.distance_from_ma_pct(close, ma)
    assert result.iloc[0] == pytest.approx(0.10)


def test_detect_crossover_golden_and_death():
    short_ma = pd.Series([9.0, 11.0, 9.0])
    long_ma = pd.Series([10.0, 10.0, 10.0])
    result = moving_averages.detect_crossover(short_ma, long_ma)
    assert result.iloc[0] is None
    assert result.iloc[1] == "golden"
    assert result.iloc[2] == "death"
