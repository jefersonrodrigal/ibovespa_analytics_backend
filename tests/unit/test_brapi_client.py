"""Testes unitários do cliente brapi — HTTP mockado, nunca a API real."""
from datetime import date

import pytest

from src.config import settings
from src.ingestion import brapi_client


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise __import__("requests").exceptions.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_fetch_ibovespa_history_without_api_key_returns_error(monkeypatch):
    monkeypatch.setattr(settings, "BRAPI_API_KEY", None)
    result = brapi_client.fetch_ibovespa_history(start=date(2026, 1, 1), end=date(2026, 1, 5))
    assert result.status == "error"
    assert "BRAPI_API_KEY" in result.error_message


def test_fetch_ibovespa_history_parses_valid_payload(monkeypatch):
    monkeypatch.setattr(settings, "BRAPI_API_KEY", "fake-token")
    payload = {
        "results": [
            {
                "symbol": "^BVSP",
                "historicalDataPrice": [
                    {"date": 1735689600, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
                    {"date": 1735776000, "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 2000},
                ],
            }
        ]
    }
    monkeypatch.setattr(brapi_client.requests, "get", lambda *a, **k: _FakeResponse(payload))

    result = brapi_client.fetch_ibovespa_history(start=date(2026, 1, 1), end=date(2026, 1, 5))
    assert result.status == "ok"
    assert len(result.rows) == 2
    assert result.rows[0]["close"] == 100.5


def test_fetch_ibovespa_history_rejects_non_positive_close(monkeypatch):
    monkeypatch.setattr(settings, "BRAPI_API_KEY", "fake-token")
    payload = {"results": [{"symbol": "^BVSP", "historicalDataPrice": [
        {"date": 1735689600, "open": 100.0, "high": 101.0, "low": 99.0, "close": 0.0, "volume": 1000},
    ]}]}
    monkeypatch.setattr(brapi_client.requests, "get", lambda *a, **k: _FakeResponse(payload))

    result = brapi_client.fetch_ibovespa_history(start=date(2026, 1, 1), end=date(2026, 1, 5))
    assert len(result.rows) == 0  # linha descartada na validação, nunca um preço inválido persistido


def test_fetch_ibovespa_history_empty_results_is_empty_status(monkeypatch):
    monkeypatch.setattr(settings, "BRAPI_API_KEY", "fake-token")
    monkeypatch.setattr(brapi_client.requests, "get", lambda *a, **k: _FakeResponse({"results": []}))

    result = brapi_client.fetch_ibovespa_history(start=date(2026, 1, 1), end=date(2026, 1, 5))
    assert result.status == "empty"


def test_fetch_ibovespa_history_plan_limit_error_is_reported(monkeypatch):
    monkeypatch.setattr(settings, "BRAPI_API_KEY", "fake-token")
    payload = {"error": True, "message": "Período histórico de cotações não disponível no plano atual"}
    monkeypatch.setattr(brapi_client.requests, "get", lambda *a, **k: _FakeResponse(payload))

    result = brapi_client.fetch_ibovespa_history(start=date(2020, 1, 1), end=date(2026, 1, 5))
    assert result.status == "error"
    assert "plano" in result.error_message.lower()


def test_fetch_ibovespa_history_never_puts_token_in_url(monkeypatch):
    monkeypatch.setattr(settings, "BRAPI_API_KEY", "super-secret-token")
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return _FakeResponse({"results": []})

    monkeypatch.setattr(brapi_client.requests, "get", fake_get)
    brapi_client.fetch_ibovespa_history(start=date(2026, 1, 1), end=date(2026, 1, 5))

    assert "super-secret-token" not in captured["url"]
    assert "super-secret-token" not in str(captured["params"])
    assert captured["headers"]["Authorization"] == "Bearer super-secret-token"
