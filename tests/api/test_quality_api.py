from datetime import date

from src.storage import db, repositories


def test_pipeline_runs_empty_when_never_executed(client):
    response = client.get("/api/quality/pipeline-runs")
    assert response.status_code == 200
    assert response.json() == []


def test_pipeline_run_steps_404_for_unknown_run(client):
    response = client.get("/api/quality/pipeline-runs/99999/steps")
    assert response.status_code == 404


def test_pipeline_runs_reflects_real_execution(client):
    with db.session_scope(for_tests=True) as session:
        run_id = repositories.start_pipeline_run(session, "manual", date(2026, 1, 1))
        repositories.insert_pipeline_run_step(session, run_id, "extract", "^BVSP", "ok", 5, 5)
        repositories.finish_pipeline_run(session, run_id, "success", 5, 5)

    response = client.get("/api/quality/pipeline-runs")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "success"

    steps_response = client.get(f"/api/quality/pipeline-runs/{run_id}/steps")
    assert steps_response.status_code == 200
    assert steps_response.json()[0]["step_name"] == "extract"


def test_sources_returns_registered_catalog(client):
    response = client.get("/api/quality/sources")
    assert response.status_code == 200
    source_ids = {row["source_id"] for row in response.json()}
    assert {"BCB_SGS", "YFINANCE", "BRAPI"}.issubset(source_ids)


def test_record_counts_empty_database(client):
    response = client.get("/api/quality/record-counts")
    assert response.status_code == 200
    assert response.json() == []
