"""Funções de leitura e gravação por tabela. Toda escrita é idempotente (upsert)."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Iterable, Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# raw: snapshots de proveniência
# ---------------------------------------------------------------------------

def insert_raw_price_snapshot(
    session: Session,
    source_id: str,
    asset_id: str,
    request_url: Optional[str],
    status: str,
    error_message: Optional[str],
    raw_payload: Optional[Any],
) -> None:
    session.execute(
        text(
            """
            INSERT INTO raw.price_snapshots
                (source_id, asset_id, request_url, status, error_message, raw_payload)
            VALUES
                (:source_id, :asset_id, :request_url, :status, :error_message, :raw_payload)
            """
        ),
        {
            "source_id": source_id,
            "asset_id": asset_id,
            "request_url": request_url,
            "status": status,
            "error_message": error_message,
            "raw_payload": json.dumps(raw_payload, default=str) if raw_payload is not None else None,
        },
    )


def insert_raw_macro_snapshot(
    session: Session,
    source_id: str,
    series_id: str,
    request_url: Optional[str],
    status: str,
    error_message: Optional[str],
    raw_payload: Optional[Any],
) -> None:
    session.execute(
        text(
            """
            INSERT INTO raw.macro_snapshots
                (source_id, series_id, request_url, status, error_message, raw_payload)
            VALUES
                (:source_id, :series_id, :request_url, :status, :error_message, :raw_payload)
            """
        ),
        {
            "source_id": source_id,
            "series_id": series_id,
            "request_url": request_url,
            "status": status,
            "error_message": error_message,
            "raw_payload": json.dumps(raw_payload, default=str) if raw_payload is not None else None,
        },
    )


# ---------------------------------------------------------------------------
# processed: upserts idempotentes
# ---------------------------------------------------------------------------

def upsert_market_prices(session: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    from sqlalchemy import MetaData, Table

    metadata = MetaData()
    table = Table("market_prices", metadata, schema="processed", autoload_with=session.get_bind())
    stmt = pg_insert(table).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_market_prices",
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
            "source_id": stmt.excluded.source_id,
            "ingested_at": stmt.excluded.ingested_at,
        },
    )
    session.execute(stmt)
    return len(rows)


def upsert_macro_observations(session: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    from sqlalchemy import MetaData, Table

    metadata = MetaData()
    table = Table("macro_observations", metadata, schema="processed", autoload_with=session.get_bind())
    stmt = pg_insert(table).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_macro_observations",
        set_={
            "value": stmt.excluded.value,
            "publication_date": stmt.excluded.publication_date,
            "ingested_at": stmt.excluded.ingested_at,
        },
    )
    session.execute(stmt)
    return len(rows)


def upsert_daily_indicators(session: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    from sqlalchemy import MetaData, Table

    metadata = MetaData()
    table = Table("daily_indicators", metadata, schema="analytics", autoload_with=session.get_bind())
    stmt = pg_insert(table).values(rows)
    update_cols = {c.name: stmt.excluded[c.name] for c in table.columns if c.name not in ("id", "asset_id", "trade_date")}
    stmt = stmt.on_conflict_do_update(constraint="uq_daily_indicators", set_=update_cols)
    session.execute(stmt)
    return len(rows)


# ---------------------------------------------------------------------------
# processed: leituras
# ---------------------------------------------------------------------------

def get_market_prices(
    session: Session, asset_id: str, start: Optional[date] = None, end: Optional[date] = None
) -> pd.DataFrame:
    query = """
        SELECT trade_date, open, high, low, close, volume, source_id, ingested_at
        FROM processed.market_prices
        WHERE asset_id = :asset_id
          AND (:start IS NULL OR trade_date >= :start)
          AND (:end IS NULL OR trade_date <= :end)
        ORDER BY trade_date
    """
    return pd.read_sql(text(query), session.get_bind(), params={"asset_id": asset_id, "start": start, "end": end})


def get_macro_observations(
    session: Session, series_id: str, start: Optional[date] = None, end: Optional[date] = None
) -> pd.DataFrame:
    query = """
        SELECT observation_date, value, unit, frequency, publication_date, source_id, ingested_at
        FROM processed.macro_observations
        WHERE series_id = :series_id
          AND (:start IS NULL OR observation_date >= :start)
          AND (:end IS NULL OR observation_date <= :end)
        ORDER BY observation_date
    """
    return pd.read_sql(text(query), session.get_bind(), params={"series_id": series_id, "start": start, "end": end})


def get_daily_indicators(
    session: Session, asset_id: str, start: Optional[date] = None, end: Optional[date] = None
) -> pd.DataFrame:
    query = """
        SELECT *
        FROM analytics.daily_indicators
        WHERE asset_id = :asset_id
          AND (:start IS NULL OR trade_date >= :start)
          AND (:end IS NULL OR trade_date <= :end)
        ORDER BY trade_date
    """
    return pd.read_sql(text(query), session.get_bind(), params={"asset_id": asset_id, "start": start, "end": end})


def get_last_market_price_date(session: Session, asset_id: str) -> Optional[date]:
    result = session.execute(
        text("SELECT MAX(trade_date) FROM processed.market_prices WHERE asset_id = :asset_id"),
        {"asset_id": asset_id},
    ).scalar()
    return result


def get_last_macro_observation_date(session: Session, series_id: str) -> Optional[date]:
    result = session.execute(
        text("SELECT MAX(observation_date) FROM processed.macro_observations WHERE series_id = :series_id"),
        {"series_id": series_id},
    ).scalar()
    return result


def get_series_catalog(session: Session) -> pd.DataFrame:
    return pd.read_sql(
        text("SELECT series_id, name, provider_code, source_id, unit, frequency, description FROM processed.series_catalog ORDER BY series_id"),
        session.get_bind(),
    )


def get_sources(session: Session) -> pd.DataFrame:
    return pd.read_sql(
        text("SELECT source_id, name, base_url, description, terms_notes FROM processed.sources ORDER BY source_id"),
        session.get_bind(),
    )


# ---------------------------------------------------------------------------
# ops: execuções do pipeline
# ---------------------------------------------------------------------------

def start_pipeline_run(session: Session, trigger: str, reference_date: Optional[date]) -> int:
    result = session.execute(
        text(
            """
            INSERT INTO ops.pipeline_runs (trigger, status, reference_date)
            VALUES (:trigger, 'running', :reference_date)
            RETURNING run_id
            """
        ),
        {"trigger": trigger, "reference_date": reference_date},
    )
    return result.scalar_one()


def finish_pipeline_run(
    session: Session,
    run_id: int,
    status: str,
    records_read: int,
    records_written: int,
    error_message: Optional[str] = None,
) -> None:
    session.execute(
        text(
            """
            UPDATE ops.pipeline_runs
            SET finished_at = now(), status = :status, records_read = :records_read,
                records_written = :records_written, error_message = :error_message
            WHERE run_id = :run_id
            """
        ),
        {
            "run_id": run_id,
            "status": status,
            "records_read": records_read,
            "records_written": records_written,
            "error_message": error_message,
        },
    )


def insert_pipeline_run_step(
    session: Session,
    run_id: int,
    step_name: str,
    target: str,
    status: str,
    records_read: int = 0,
    records_written: int = 0,
    error_message: Optional[str] = None,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO ops.pipeline_run_steps
                (run_id, step_name, target, status, records_read, records_written, error_message, finished_at)
            VALUES
                (:run_id, :step_name, :target, :status, :records_read, :records_written, :error_message, now())
            """
        ),
        {
            "run_id": run_id,
            "step_name": step_name,
            "target": target,
            "status": status,
            "records_read": records_read,
            "records_written": records_written,
            "error_message": error_message,
        },
    )


def get_pipeline_runs(session: Session, limit: int = 20) -> pd.DataFrame:
    return pd.read_sql(
        text(
            """
            SELECT run_id, trigger, started_at, finished_at, status, reference_date,
                   records_read, records_written, error_message
            FROM ops.pipeline_runs
            ORDER BY started_at DESC
            LIMIT :limit
            """
        ),
        session.get_bind(),
        params={"limit": limit},
    )


def get_pipeline_run_steps(session: Session, run_id: int) -> pd.DataFrame:
    return pd.read_sql(
        text(
            """
            SELECT step_name, target, status, records_read, records_written,
                   error_message, started_at, finished_at
            FROM ops.pipeline_run_steps
            WHERE run_id = :run_id
            ORDER BY started_at
            """
        ),
        session.get_bind(),
        params={"run_id": run_id},
    )


def get_last_successful_run(session: Session) -> Optional[pd.Series]:
    df = pd.read_sql(
        text(
            """
            SELECT run_id, started_at, finished_at, reference_date, records_written
            FROM ops.pipeline_runs
            WHERE status IN ('success', 'partial_failure')
            ORDER BY finished_at DESC
            LIMIT 1
            """
        ),
        session.get_bind(),
    )
    if df.empty:
        return None
    return df.iloc[0]


def get_record_counts(session: Session) -> pd.DataFrame:
    return pd.read_sql(
        text(
            """
            SELECT 'processed.market_prices' AS table_name, source_id, COUNT(*) AS records,
                   MIN(trade_date) AS min_date, MAX(trade_date) AS max_date
            FROM processed.market_prices
            GROUP BY source_id
            UNION ALL
            SELECT 'processed.macro_observations' AS table_name, series_id AS source_id, COUNT(*) AS records,
                   MIN(observation_date) AS min_date, MAX(observation_date) AS max_date
            FROM processed.macro_observations
            GROUP BY series_id
            ORDER BY table_name, source_id
            """
        ),
        session.get_bind(),
    )
