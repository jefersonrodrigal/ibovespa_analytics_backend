"""Testes de integração do pipeline completo contra o banco de testes real.

As respostas das fontes externas (yfinance/BCB) são substituídas por fixtures
sintéticas via monkeypatch, para isolar o teste de instabilidade de rede — nunca
usadas fora desta suíte. A persistência, idempotência e os indicadores calculados
usam o PostgreSQL de teste real, sem mocks de banco de dados.
"""
from __future__ import annotations

from datetime import date

import pytest

from src import pipeline
from src.config import settings
from src.ingestion.bcb_client import SeriesFetchResult
from src.ingestion.common import PriceFetchResult
from src.storage import db, repositories


def _fake_ibov_result(rows):
    return PriceFetchResult("^BVSP", "http://fake", "ok", None, rows, rows)


def _fake_series_result(series_id, provider_code, rows):
    return SeriesFetchResult(series_id, provider_code, "http://fake", "ok", None, rows, rows)


@pytest.fixture
def synthetic_ibov_rows():
    return [
        {"trade_date": date(2026, 1, d), "open": 100.0 + d, "high": 101.0 + d, "low": 99.0 + d,
         "close": 100.0 + d, "volume": 1000 + d}
        for d in range(1, 11)
    ]


def test_run_ibovespa_step_persists_data(db_session, synthetic_ibov_rows, monkeypatch):
    monkeypatch.setattr(
        pipeline.yfinance_client, "fetch_ibovespa_history",
        lambda **kwargs: _fake_ibov_result(synthetic_ibov_rows),
    )
    run_id = repositories.start_pipeline_run(db_session, "manual", date(2026, 1, 10))
    db_session.commit()

    with db.session_scope(for_tests=True) as session:
        result = pipeline.run_ibovespa_step(session, run_id)

    assert result["status"] == "ok"
    assert result["written"] == 10

    with db.session_scope(for_tests=True) as session:
        df = repositories.get_market_prices(session, settings.IBOVESPA_ASSET_ID)
    assert len(df) == 10


def test_run_ibovespa_step_uses_brapi_for_incremental_update_after_backfill(db_session, synthetic_ibov_rows, monkeypatch):
    # 1ª carga: sem preços persistidos -> deve usar yfinance.
    monkeypatch.setattr(
        pipeline.yfinance_client, "fetch_ibovespa_history",
        lambda **kwargs: _fake_ibov_result(synthetic_ibov_rows),
    )
    run_id = repositories.start_pipeline_run(db_session, "manual", date(2026, 1, 10))
    db_session.commit()
    with db.session_scope(for_tests=True) as session:
        first = pipeline.run_ibovespa_step(session, run_id)
    assert first["status"] == "ok"

    # 2ª carga: já há histórico -> deve usar a brapi, a partir de last_date + 1 dia.
    captured = {}

    def fake_brapi(**kwargs):
        captured.update(kwargs)
        return _fake_ibov_result([
            {"trade_date": date(2026, 1, 11), "open": 111.0, "high": 112.0, "low": 110.0, "close": 111.5, "volume": 5000},
        ])

    monkeypatch.setattr(pipeline.brapi_client, "fetch_ibovespa_history", fake_brapi)
    with db.session_scope(for_tests=True) as session:
        second = pipeline.run_ibovespa_step(session, run_id)

    assert second["status"] == "ok"
    assert second["written"] == 1
    assert captured["start"] == date(2026, 1, 11)  # last_date (10) + 1 dia

    with db.session_scope(for_tests=True) as session:
        df = repositories.get_market_prices(session, settings.IBOVESPA_ASSET_ID)
    assert len(df) == 11
    new_row = df[df["trade_date"] == date(2026, 1, 11)].iloc[0]
    assert new_row["source_id"] == settings.BRAPI_SOURCE_ID


def test_run_ibovespa_step_handles_source_error_without_fake_success(db_session, monkeypatch):
    monkeypatch.setattr(
        pipeline.yfinance_client, "fetch_ibovespa_history",
        lambda **kwargs: PriceFetchResult("^BVSP", "http://fake", "error", "falha simulada de rede", None, []),
    )
    run_id = repositories.start_pipeline_run(db_session, "manual", date(2026, 1, 10))
    db_session.commit()

    with db.session_scope(for_tests=True) as session:
        result = pipeline.run_ibovespa_step(session, run_id)

    assert result["status"] == "error"
    assert result["written"] == 0
    assert "falha simulada" in result["error"]

    with db.session_scope(for_tests=True) as session:
        df = repositories.get_market_prices(session, settings.IBOVESPA_ASSET_ID)
    assert df.empty  # falha não é convertida silenciosamente em sucesso


def test_recompute_daily_indicators_from_persisted_prices(db_session, synthetic_ibov_rows, monkeypatch):
    monkeypatch.setattr(
        pipeline.yfinance_client, "fetch_ibovespa_history",
        lambda **kwargs: _fake_ibov_result(synthetic_ibov_rows),
    )
    run_id = repositories.start_pipeline_run(db_session, "manual", date(2026, 1, 10))
    db_session.commit()

    with db.session_scope(for_tests=True) as session:
        pipeline.run_ibovespa_step(session, run_id)
    with db.session_scope(for_tests=True) as session:
        result = pipeline.recompute_daily_indicators(session, run_id)

    assert result["status"] == "ok"
    with db.session_scope(for_tests=True) as session:
        df = repositories.get_daily_indicators(session, settings.IBOVESPA_ASSET_ID)
    assert len(df) == 10
    assert df.iloc[0]["daily_return"] is None or df.iloc[0]["daily_return"] != df.iloc[0]["daily_return"]
    # com apenas 10 pregões, médias móveis de 20+ não devem estar disponíveis
    assert df.iloc[-1]["ma_20"] is None


def test_full_pipeline_run_is_idempotent_on_rerun(synthetic_ibov_rows, monkeypatch):
    monkeypatch.setattr(
        pipeline.yfinance_client, "fetch_ibovespa_history",
        lambda **kwargs: _fake_ibov_result(synthetic_ibov_rows),
    )
    # A 2ª execução já tem last_date persistido, então o pipeline usa a brapi
    # (atualização incremental) em vez do yfinance — simula "sem pregão novo".
    monkeypatch.setattr(
        pipeline.brapi_client, "fetch_ibovespa_history",
        lambda **kwargs: PriceFetchResult("^BVSP", "http://fake", "empty", None, None, []),
    )
    monkeypatch.setattr(
        pipeline.bcb_client, "fetch_series",
        lambda series_id, provider_code, **kwargs: _fake_series_result(
            series_id, provider_code,
            [{"observation_date": date(2026, 1, d), "value": 0.05} for d in range(1, 11)],
        ),
    )
    summary_1 = pipeline.run_pipeline(trigger="manual", for_tests=True)
    summary_2 = pipeline.run_pipeline(trigger="manual", for_tests=True)

    assert summary_1["status"] == "success"
    assert summary_2["status"] == "success"

    with db.session_scope(for_tests=True) as session:
        prices = repositories.get_market_prices(session, settings.IBOVESPA_ASSET_ID)
        macro = repositories.get_macro_observations(session, "BCB_SGS_12")

    assert len(prices) == 10  # sem duplicação na reexecução
    assert len(macro) == 10
