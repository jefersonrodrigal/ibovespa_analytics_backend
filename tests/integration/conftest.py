"""Fixtures de integração: usam o banco de testes real (ibovespa_analytics_test).

Nunca usa o banco de produção (ibovespa_analytics). As tabelas de fato são limpas
antes de cada teste para isolamento; as tabelas de dimensão (sources/assets/series_catalog)
são preservadas, pois são carga de referência do schema.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from src.storage import db


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
def db_session():
    with db.session_scope(for_tests=True) as session:
        yield session
