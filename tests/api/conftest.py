"""Fixtures dos testes de API: TestClient apontado para o banco de testes real
(ibovespa_analytics_test), nunca para produção.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.deps import get_db
from app.main import app
from src.storage import db


def _get_db_for_tests():
    with db.session_scope(for_tests=True) as session:
        yield session


app.dependency_overrides[get_db] = _get_db_for_tests


@pytest.fixture(autouse=True)
def clean_fact_tables():
    with db.session_scope(for_tests=True) as session:
        session.execute(text("TRUNCATE TABLE ops.pipeline_run_steps RESTART IDENTITY CASCADE"))
        session.execute(text("TRUNCATE TABLE ops.pipeline_runs RESTART IDENTITY CASCADE"))
        session.execute(text("TRUNCATE TABLE analytics.daily_indicators RESTART IDENTITY CASCADE"))
        session.execute(text("TRUNCATE TABLE processed.market_prices RESTART IDENTITY CASCADE"))
        session.execute(text("TRUNCATE TABLE processed.macro_observations RESTART IDENTITY CASCADE"))
        session.execute(text("TRUNCATE TABLE raw.price_snapshots RESTART IDENTITY CASCADE"))
        session.execute(text("TRUNCATE TABLE raw.macro_snapshots RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
