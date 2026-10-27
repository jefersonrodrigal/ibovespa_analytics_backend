from datetime import date, timedelta

from src.validation import quality


def test_validate_market_price_rows_rejects_duplicate_dates():
    rows = [
        {"trade_date": date(2026, 1, 2), "close": 100.0, "open": 100, "high": 101, "low": 99, "volume": 10},
        {"trade_date": date(2026, 1, 2), "close": 101.0, "open": 100, "high": 101, "low": 99, "volume": 10},
    ]
    clean, issues = quality.validate_market_price_rows(rows)
    assert len(clean) == 1
    assert any(i.severity == "error" and "duplicada" in i.message for i in issues)


def test_validate_market_price_rows_rejects_non_positive_close():
    rows = [
        {"trade_date": date(2026, 1, 2), "close": 0.0, "open": 100, "high": 101, "low": 99, "volume": 10},
        {"trade_date": date(2026, 1, 3), "close": -5.0, "open": 100, "high": 101, "low": 99, "volume": 10},
    ]
    clean, issues = quality.validate_market_price_rows(rows)
    assert len(clean) == 0
    assert all(i.severity == "error" for i in issues)


def test_validate_market_price_rows_flags_extreme_move_as_warning_not_rejection():
    rows = [
        {"trade_date": date(2026, 1, 1), "close": 100.0, "open": 100, "high": 101, "low": 99, "volume": 10},
        {"trade_date": date(2026, 1, 2), "close": 130.0, "open": 100, "high": 130, "low": 99, "volume": 10},
    ]
    clean, issues = quality.validate_market_price_rows(rows)
    assert len(clean) == 2  # dado real preservado, não descartado
    assert any(i.severity == "warning" and "extrema" in i.message for i in issues)


def test_validate_macro_observation_rows_rejects_null_value():
    rows = [
        {"observation_date": date(2026, 1, 1), "value": None},
        {"observation_date": date(2026, 1, 2), "value": 13.75},
    ]
    clean, issues = quality.validate_macro_observation_rows(rows, "BCB_SGS_432")
    assert len(clean) == 1
    assert clean[0]["value"] == 13.75
    assert any(i.severity == "error" for i in issues)


def test_validate_macro_observation_rows_rejects_duplicate_dates():
    rows = [
        {"observation_date": date(2026, 1, 1), "value": 10.0},
        {"observation_date": date(2026, 1, 1), "value": 11.0},
    ]
    clean, issues = quality.validate_macro_observation_rows(rows, "BCB_SGS_12")
    assert len(clean) == 1


def test_check_staleness_none_when_up_to_date():
    today = date(2026, 10, 27)  # terça-feira
    last = date(2026, 10, 26)  # segunda-feira
    assert quality.check_staleness(last, today) is None


def test_check_staleness_warns_when_old():
    today = date(2026, 10, 27)
    last = today - timedelta(days=20)
    issue = quality.check_staleness(last, today)
    assert issue is not None
    assert issue.severity == "warning"


def test_check_staleness_error_when_no_data():
    issue = quality.check_staleness(None, date(2026, 10, 27))
    assert issue is not None
    assert issue.severity == "error"


def test_check_staleness_ignores_weekend_as_business_days():
    # sexta -> segunda não deveria contar como grande defasagem (2 dias úteis: sáb/dom não contam)
    friday = date(2026, 10, 23)
    monday = date(2026, 10, 26)
    assert quality.check_staleness(friday, monday) is None
