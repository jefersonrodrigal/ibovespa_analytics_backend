from datetime import date, datetime, timezone

from src.config import settings
from src.pipeline import recompute_daily_indicators
from src.storage import db, repositories


def _seed_prices(n_days: int = 30) -> None:
    rows = [
        {
            "asset_id": settings.IBOVESPA_ASSET_ID, "trade_date": date(2026, 1, d) if d <= 28 else date(2026, 2, d - 28),
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0 + d, "volume": 1000,
            "source_id": "YFINANCE", "ingested_at": datetime.now(timezone.utc),
        }
        for d in range(1, n_days + 1)
    ]
    # Duas sessões separadas: o upsert precisa ser commitado antes que
    # recompute_daily_indicators o leia (ele lê via pd.read_sql no engine,
    # fora da transação da sessão em uso, então não veria dados não commitados
    # se estivesse na mesma sessão/transação ainda aberta).
    with db.session_scope(for_tests=True) as session:
        repositories.upsert_market_prices(session, rows)
    with db.session_scope(for_tests=True) as session:
        run_id = repositories.start_pipeline_run(session, "manual", date(2026, 2, 1))
        recompute_daily_indicators(session, run_id)


def test_prices_empty_database_returns_empty_list_not_error(client):
    response = client.get("/api/ibovespa/prices")
    assert response.status_code == 200
    assert response.json() == []


def test_summary_empty_database_returns_all_none_fields(client):
    response = client.get("/api/ibovespa/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["last_close"] is None
    assert body["daily_return"] is None


def test_prices_reflects_real_seeded_data(client):
    _seed_prices(30)
    response = client.get("/api/ibovespa/prices")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 30
    last_row = body[-1]
    assert last_row["close"] == 130.0  # 100 + 30, valor controlado pelo teste


def test_summary_reflects_real_seeded_data(client):
    _seed_prices(30)
    response = client.get("/api/ibovespa/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["last_close"] == 130.0
    assert body["return_252"] is None  # histórico insuficiente (< 252 pregões), nunca aproximado


def test_indicators_respects_date_filter(client):
    _seed_prices(30)
    response = client.get("/api/ibovespa/indicators", params={"start": "2026-02-01"})
    assert response.status_code == 200
    body = response.json()
    assert all(row["trade_date"] >= "2026-02-01" for row in body)
    assert len(body) == 2  # dias 29 e 30 cairam em fevereiro
