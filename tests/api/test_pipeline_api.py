"""O endpoint de disparo do pipeline nunca é testado chamando as fontes externas de
verdade (lento, e `run_pipeline()` sem `for_tests=True` escreveria no banco de
produção) — a função é substituída por um resumo controlado, e o teste verifica
apenas que a API empacota esse resumo corretamente.
"""
from __future__ import annotations

from datetime import date

import app.api.pipeline as pipeline_api


def test_trigger_pipeline_run_wraps_summary(client, monkeypatch):
    fake_summary = {
        "reference_date": date(2026, 1, 1).isoformat(),
        "steps": [{"source": "^BVSP", "status": "ok", "read": 1, "written": 1, "error": None}],
        "status": "success",
        "records_read": 1,
        "records_written": 1,
    }
    monkeypatch.setattr(pipeline_api, "run_pipeline", lambda trigger: fake_summary)

    response = client.post("/api/pipeline/run")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["records_written"] == 1
    assert body["steps"][0]["source"] == "^BVSP"


def test_trigger_pipeline_run_reports_failure_honestly(client, monkeypatch):
    fake_summary = {
        "reference_date": date(2026, 1, 1).isoformat(),
        "steps": [],
        "status": "failed",
        "records_read": 0,
        "records_written": 0,
        "error": "falha simulada",
    }
    monkeypatch.setattr(pipeline_api, "run_pipeline", lambda trigger: fake_summary)

    response = client.post("/api/pipeline/run")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"] == "falha simulada"
