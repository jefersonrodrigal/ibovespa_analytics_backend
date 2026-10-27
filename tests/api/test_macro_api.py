from datetime import date, datetime, timezone

from src.storage import db, repositories


def _seed_series(series_id: str, unit: str, frequency: str, values: list[tuple[date, float]]) -> None:
    rows = [
        {
            "series_id": series_id, "observation_date": d, "value": v, "unit": unit, "frequency": frequency,
            "publication_date": None, "source_id": "BCB_SGS", "ingested_at": datetime.now(timezone.utc),
        }
        for d, v in values
    ]
    with db.session_scope(for_tests=True) as session:
        repositories.upsert_macro_observations(session, rows)


def test_catalog_returns_real_series_definitions(client):
    response = client.get("/api/macro/catalog")
    assert response.status_code == 200
    body = response.json()
    series_ids = {row["series_id"] for row in body}
    assert "BCB_SGS_12" in series_ids  # CDI — cadastrado pelo schema.sql, não inventado pelo teste


def test_summary_empty_database_returns_none_everywhere(client):
    response = client.get("/api/macro/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["cdi"] is None
    assert body["cdi_accumulated_12m"] is None
    assert body["real_interest_rate_approx"] is None


def test_summary_reflects_seeded_cdi_data(client):
    _seed_series("BCB_SGS_12", "% a.d.", "daily", [(date(2026, 1, d), 0.05) for d in range(1, 29)])
    response = client.get("/api/macro/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["cdi"]["value"] == 0.05
    assert body["cdi"]["observation_date"] == "2026-01-28"


def test_observations_endpoint_for_unknown_series_is_empty_not_error(client):
    response = client.get("/api/macro/BCB_SGS_999/observations")
    assert response.status_code == 200
    assert response.json() == []
