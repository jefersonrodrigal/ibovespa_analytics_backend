from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from src.storage import db, repositories


def test_upsert_market_prices_is_idempotent(db_session):
    rows = [
        {
            "asset_id": "^BVSP", "trade_date": date(2026, 1, 2), "open": 100.0, "high": 105.0,
            "low": 99.0, "close": 104.0, "volume": 1000, "source_id": "YFINANCE",
            "ingested_at": datetime.now(timezone.utc),
        }
    ]
    written_first = repositories.upsert_market_prices(db_session, rows)
    written_second = repositories.upsert_market_prices(db_session, rows)
    db_session.commit()

    assert written_first == 1
    assert written_second == 1

    df = repositories.get_market_prices(db_session, "^BVSP")
    assert len(df) == 1  # sem duplicação
    assert float(df.iloc[0]["close"]) == 104.0


def test_upsert_market_prices_updates_existing_row(db_session):
    base_row = {
        "asset_id": "^BVSP", "trade_date": date(2026, 1, 2), "open": 100.0, "high": 105.0,
        "low": 99.0, "close": 104.0, "volume": 1000, "source_id": "YFINANCE",
        "ingested_at": datetime.now(timezone.utc),
    }
    repositories.upsert_market_prices(db_session, [base_row])

    updated_row = dict(base_row)
    updated_row["close"] = 110.0
    repositories.upsert_market_prices(db_session, [updated_row])
    db_session.commit()

    df = repositories.get_market_prices(db_session, "^BVSP")
    assert len(df) == 1
    assert float(df.iloc[0]["close"]) == 110.0


def test_market_prices_rejects_non_positive_close(db_session):
    rows = [
        {
            "asset_id": "^BVSP", "trade_date": date(2026, 1, 2), "open": 100.0, "high": 105.0,
            "low": 99.0, "close": 0.0, "volume": 1000, "source_id": "YFINANCE",
            "ingested_at": datetime.now(timezone.utc),
        }
    ]
    with pytest.raises(IntegrityError):
        repositories.upsert_market_prices(db_session, rows)
    db_session.rollback()


def test_upsert_macro_observations_is_idempotent(db_session):
    rows = [
        {
            "series_id": "BCB_SGS_12", "observation_date": date(2026, 1, 2), "value": 0.05,
            "unit": "% a.d.", "frequency": "daily", "publication_date": None,
            "source_id": "BCB_SGS", "ingested_at": datetime.now(timezone.utc),
        }
    ]
    repositories.upsert_macro_observations(db_session, rows)
    repositories.upsert_macro_observations(db_session, rows)
    db_session.commit()

    df = repositories.get_macro_observations(db_session, "BCB_SGS_12")
    assert len(df) == 1


def test_pipeline_run_lifecycle(db_session):
    run_id = repositories.start_pipeline_run(db_session, "manual", date(2026, 1, 2))
    repositories.insert_pipeline_run_step(db_session, run_id, "extract", "^BVSP", "ok", 10, 0)
    repositories.finish_pipeline_run(db_session, run_id, "success", 10, 10)
    db_session.commit()

    runs = repositories.get_pipeline_runs(db_session, limit=5)
    assert len(runs) == 1
    assert runs.iloc[0]["status"] == "success"

    steps = repositories.get_pipeline_run_steps(db_session, run_id)
    assert len(steps) == 1
    assert steps.iloc[0]["step_name"] == "extract"


def test_rollback_discards_uncommitted_changes():
    with db.session_scope(for_tests=True) as outer_session:
        pass  # sessão limpa antes do teste (via fixture autouse)

    try:
        with db.session_scope(for_tests=True) as session:
            repositories.upsert_market_prices(session, [{
                "asset_id": "^BVSP", "trade_date": date(2026, 1, 2), "open": 100.0, "high": 105.0,
                "low": 99.0, "close": 104.0, "volume": 1000, "source_id": "YFINANCE",
                "ingested_at": datetime.now(timezone.utc),
            }])
            raise RuntimeError("falha simulada após gravação, antes do commit")
    except RuntimeError:
        pass

    with db.session_scope(for_tests=True) as session:
        df = repositories.get_market_prices(session, "^BVSP")
        assert df.empty  # rollback automático de session_scope impediu a gravação
