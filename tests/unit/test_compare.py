import pandas as pd
import pytest

from src.analytics import compare


def test_normalize_to_base():
    series = pd.Series([50.0, 55.0, 60.0])
    result = compare.normalize_to_base(series, base=100.0)
    assert result.iloc[0] == pytest.approx(100.0)
    assert result.iloc[1] == pytest.approx(110.0)


def test_normalize_to_base_empty():
    result = compare.normalize_to_base(pd.Series([], dtype=float))
    assert result.empty


def test_build_compounded_index():
    daily_rate_pct = pd.Series([0.0, 1.0, 1.0])  # 0%, 1%, 1% ao dia
    index = compare.build_compounded_index(daily_rate_pct, base=100.0)
    assert index.iloc[0] == pytest.approx(100.0)
    assert index.iloc[1] == pytest.approx(101.0)
    assert index.iloc[2] == pytest.approx(101.0 * 1.01)


def test_align_on_common_dates():
    df_a = pd.DataFrame({"date": [1, 2, 3], "value": [10, 20, 30]})
    df_b = pd.DataFrame({"date": [2, 3, 4], "value": [200, 300, 400]})
    a, b = compare.align_on_common_dates(df_a, df_b, date_col="date")
    assert list(a["date"]) == [2, 3]
    assert list(b["date"]) == [2, 3]


def test_real_return_fisher():
    result = compare.real_return_fisher(0.10, 0.05)
    assert result == pytest.approx(1.10 / 1.05 - 1)


def test_real_return_fisher_none_when_missing_input():
    assert compare.real_return_fisher(None, 0.05) is None
    assert compare.real_return_fisher(0.1, None) is None


def test_accumulated_rate_compounds_periodic_rates():
    rates = pd.Series([1.0, 1.0, 1.0])  # 1% em 3 períodos sucessivos
    result = compare.accumulated_rate(rates)
    assert result == pytest.approx(1.01 ** 3 - 1)


def test_accumulated_rate_empty_is_none():
    assert compare.accumulated_rate(pd.Series([], dtype=float)) is None
    assert compare.accumulated_rate(pd.Series([None, None])) is None


def test_trailing_window_keeps_only_last_n_months():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-15", "2025-06-15", "2025-11-15", "2026-01-15"]),
        "value": [1, 2, 3, 4],
    })
    result = compare.trailing_window(df, "date", months=12, as_of=pd.Timestamp("2026-01-15"))
    assert list(result["value"]) == [2, 3, 4]  # exclui 2025-01-15 (exatamente 12 meses antes, fora da janela aberta)


def test_trailing_window_empty_dataframe():
    df = pd.DataFrame({"date": [], "value": []})
    result = compare.trailing_window(df, "date", months=12)
    assert result.empty
