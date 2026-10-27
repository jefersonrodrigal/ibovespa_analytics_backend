"""Orquestra o pipeline completo: extração -> validação -> persistência -> indicadores -> log.

Idempotente: reexecutar não duplica linhas (upsert por chave única) e recalcula
os indicadores a partir do histórico completo persistido, garantindo consistência.
Uma falha em uma fonte não derruba as demais nem é convertida silenciosamente em sucesso.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from src.analytics import compare, moving_averages, returns, risk
from src.config import settings
from src.ingestion import bcb_client, brapi_client, yfinance_client
from src.ingestion.common import PriceFetchResult
from src.storage import db, repositories
from src.validation import quality

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_ibovespa_step(session, run_id: int) -> dict:
    """Extrai, valida e persiste o histórico do Ibovespa. Retorna resumo do passo.

    Estratégia híbrida: a primeira carga (sem preços persistidos) usa o yfinance
    para o backfill histórico completo. Daí em diante, as atualizações
    incrementais usam a brapi — começando em `last_date + 1 dia` para que o
    mesmo pregão nunca seja escrito por duas fontes diferentes.
    """
    asset_id = settings.IBOVESPA_ASSET_ID
    last_date = repositories.get_last_market_price_date(session, asset_id)
    today = date.today()

    if last_date is None:
        source_id = settings.YFINANCE_SOURCE_ID
        result = yfinance_client.fetch_ibovespa_history(period="max")
    elif last_date + timedelta(days=1) > today:
        # Já atualizado hoje (reexecução no mesmo dia); nada novo a buscar.
        source_id = settings.BRAPI_SOURCE_ID
        result = PriceFetchResult("^BVSP", "", "empty", None, None, [])
    else:
        source_id = settings.BRAPI_SOURCE_ID
        result = brapi_client.fetch_ibovespa_history(start=last_date + timedelta(days=1), end=today)

    repositories.insert_raw_price_snapshot(
        session, source_id, asset_id, result.url, result.status, result.error_message, result.raw_payload,
    )

    if result.status == "error":
        repositories.insert_pipeline_run_step(
            session, run_id, "extract", asset_id, "error", 0, 0, result.error_message,
        )
        return {"source": asset_id, "status": "error", "read": 0, "written": 0, "error": result.error_message}

    repositories.insert_pipeline_run_step(session, run_id, "extract", asset_id, "ok", len(result.rows), 0)

    clean_rows, issues = quality.validate_market_price_rows(result.rows)
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    for w in warnings:
        logger.warning("Qualidade (%s): %s", asset_id, w.message)

    validate_status = "error" if errors and not clean_rows else "ok"
    repositories.insert_pipeline_run_step(
        session, run_id, "validate", asset_id, validate_status, len(result.rows), len(clean_rows),
        "; ".join(i.message for i in errors) or None,
    )

    if not clean_rows:
        # result.status == "empty" é uma condição normal (ex.: fim de semana/feriado,
        # sem novo pregão desde a última atualização) — não é um erro de pipeline.
        status = "ok" if result.status == "empty" else "error"
        error = None if status == "ok" else "Nenhuma linha válida após validação."
        return {"source": asset_id, "status": status, "read": len(result.rows), "written": 0, "error": error}

    rows_to_persist = [
        {
            "asset_id": asset_id,
            "trade_date": r["trade_date"],
            "open": r["open"],
            "high": r["high"],
            "low": r["low"],
            "close": r["close"],
            "volume": r["volume"],
            "source_id": source_id,
            "ingested_at": _now(),
        }
        for r in clean_rows
    ]
    written = repositories.upsert_market_prices(session, rows_to_persist)
    repositories.insert_pipeline_run_step(session, run_id, "persist", asset_id, "ok", len(clean_rows), written)

    return {"source": asset_id, "status": "ok", "read": len(result.rows), "written": written, "error": None, "warnings": len(warnings)}


def run_macro_step(session, run_id: int, series_id: str, provider_code: str, unit: str, frequency: str) -> dict:
    last_date = repositories.get_last_macro_observation_date(session, series_id)
    start = last_date if last_date is not None else None
    result = bcb_client.fetch_series(series_id, provider_code, start=start, end=date.today())

    repositories.insert_raw_macro_snapshot(
        session, settings.BCB_SOURCE_ID, series_id, result.url, result.status, result.error_message, result.raw_payload,
    )

    if result.status == "error":
        repositories.insert_pipeline_run_step(session, run_id, "extract", series_id, "error", 0, 0, result.error_message)
        return {"source": series_id, "status": "error", "read": 0, "written": 0, "error": result.error_message}

    repositories.insert_pipeline_run_step(session, run_id, "extract", series_id, "ok", len(result.rows), 0)

    clean_rows, issues = quality.validate_macro_observation_rows(result.rows, series_id)
    errors = [i for i in issues if i.severity == "error"]
    for i in errors:
        logger.warning("Qualidade (%s): %s", series_id, i.message)

    validate_status = "error" if errors and not clean_rows else "ok"
    repositories.insert_pipeline_run_step(
        session, run_id, "validate", series_id, validate_status, len(result.rows), len(clean_rows),
        "; ".join(i.message for i in errors) or None,
    )

    if not clean_rows:
        status = "ok" if result.status == "empty" else "error"
        return {"source": series_id, "status": status, "read": 0, "written": 0, "error": None if status == "ok" else "Nenhuma linha válida."}

    rows_to_persist = [
        {
            "series_id": series_id,
            "observation_date": r["observation_date"],
            "value": r["value"],
            "unit": unit,
            "frequency": frequency,
            "publication_date": None,
            "source_id": settings.BCB_SOURCE_ID,
            "ingested_at": _now(),
        }
        for r in clean_rows
    ]
    written = repositories.upsert_macro_observations(session, rows_to_persist)
    repositories.insert_pipeline_run_step(session, run_id, "persist", series_id, "ok", len(clean_rows), written)

    return {"source": series_id, "status": "ok", "read": len(result.rows), "written": written, "error": None}


def recompute_daily_indicators(session, run_id: int) -> dict:
    """Recalcula analytics.daily_indicators a partir de todo o histórico persistido de market_prices.

    Recalcular o histórico completo (em vez de incrementalmente) evita inconsistências
    quando dados passados são corrigidos pela fonte, e é barato para o volume de dados envolvido.
    """
    asset_id = settings.IBOVESPA_ASSET_ID
    df = repositories.get_market_prices(session, asset_id)

    if df.empty:
        repositories.insert_pipeline_run_step(session, run_id, "indicators", asset_id, "skipped", 0, 0, "Sem preços persistidos.")
        return {"source": asset_id, "status": "skipped", "read": 0, "written": 0}

    df = df.sort_values("trade_date").reset_index(drop=True)
    close = df["close"].astype(float)
    dates = pd.to_datetime(df["trade_date"])

    daily_ret = returns.daily_return(close)
    ma20 = moving_averages.moving_average(close, 20)
    ma50 = moving_averages.moving_average(close, 50)
    ma200 = moving_averages.moving_average(close, 200)
    dd = risk.drawdown(close)

    indicator_rows = []
    for idx in range(len(df)):
        indicator_rows.append(
            {
                "asset_id": asset_id,
                "trade_date": df["trade_date"].iloc[idx],
                "close": float(close.iloc[idx]),
                "daily_return": _to_float_or_none(daily_ret.iloc[idx]),
                "return_21": _to_float_or_none(returns.return_n_periods(close, 21).iloc[idx]),
                "return_63": _to_float_or_none(returns.return_n_periods(close, 63).iloc[idx]),
                "return_126": _to_float_or_none(returns.return_n_periods(close, 126).iloc[idx]),
                "return_252": _to_float_or_none(returns.return_n_periods(close, 252).iloc[idx]),
                "ma_20": _to_float_or_none(ma20.iloc[idx]),
                "ma_50": _to_float_or_none(ma50.iloc[idx]),
                "ma_200": _to_float_or_none(ma200.iloc[idx]),
                "dist_ma_20_pct": _to_float_or_none(moving_averages.distance_from_ma_pct(close, ma20).iloc[idx]),
                "dist_ma_50_pct": _to_float_or_none(moving_averages.distance_from_ma_pct(close, ma50).iloc[idx]),
                "dist_ma_200_pct": _to_float_or_none(moving_averages.distance_from_ma_pct(close, ma200).iloc[idx]),
                "vol_21_annual": _to_float_or_none(risk.rolling_volatility_annualized(daily_ret, 21).iloc[idx]),
                "vol_63_annual": _to_float_or_none(risk.rolling_volatility_annualized(daily_ret, 63).iloc[idx]),
                "vol_252_annual": _to_float_or_none(risk.rolling_volatility_annualized(daily_ret, 252).iloc[idx]),
                "drawdown": _to_float_or_none(dd.iloc[idx]),
                "running_max": _to_float_or_none(risk.running_max(close).iloc[idx]),
            }
        )

    written = repositories.upsert_daily_indicators(session, indicator_rows)
    repositories.insert_pipeline_run_step(session, run_id, "indicators", asset_id, "ok", len(df), written)
    return {"source": asset_id, "status": "ok", "read": len(df), "written": written}


def _to_float_or_none(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def run_pipeline(trigger: str = "manual", for_tests: bool = False) -> dict:
    """Executa o pipeline completo. Retorna um resumo serializável da execução.

    `for_tests=True` direciona toda a execução para o banco de testes
    (ibovespa_analytics_test) — usado exclusivamente pela suíte de integração,
    nunca pela aplicação em produção.
    """
    reference_date = date.today()
    summary = {"reference_date": reference_date.isoformat(), "steps": []}

    with db.session_scope(for_tests=for_tests) as session:
        run_id = repositories.start_pipeline_run(session, trigger, reference_date)

    total_read = 0
    total_written = 0
    any_success = False
    any_error = False
    error_messages: list[str] = []

    try:
        with db.session_scope(for_tests=for_tests) as session:
            ibov_result = run_ibovespa_step(session, run_id)
        summary["steps"].append(ibov_result)
        total_read += ibov_result["read"]
        total_written += ibov_result["written"]
        if ibov_result["status"] == "ok":
            any_success = True
        else:
            any_error = True
            error_messages.append(f"^BVSP: {ibov_result['error']}")

        for series_id, meta in settings.MACRO_SERIES.items():
            with db.session_scope(for_tests=for_tests) as session:
                macro_result = run_macro_step(session, run_id, series_id, meta["provider_code"], meta["unit"], meta["frequency"])
            summary["steps"].append(macro_result)
            total_read += macro_result["read"]
            total_written += macro_result["written"]
            if macro_result["status"] == "ok":
                any_success = True
            else:
                any_error = True
                error_messages.append(f"{series_id}: {macro_result['error']}")

        with db.session_scope(for_tests=for_tests) as session:
            indicators_result = recompute_daily_indicators(session, run_id)
        summary["steps"].append(indicators_result)
        total_written += indicators_result["written"]

        with db.session_scope(for_tests=for_tests) as session:
            last_date = repositories.get_last_market_price_date(session, settings.IBOVESPA_ASSET_ID)
        staleness_issue = quality.check_staleness(last_date, reference_date)
        with db.session_scope(for_tests=for_tests) as session:
            repositories.insert_pipeline_run_step(
                session, run_id, "consistency_check", settings.IBOVESPA_ASSET_ID,
                "error" if staleness_issue and staleness_issue.severity == "error" else "ok",
                0, 0, staleness_issue.message if staleness_issue else None,
            )
        if staleness_issue:
            summary["staleness_warning"] = staleness_issue.message

        if any_success and not any_error:
            status = "success"
        elif any_success and any_error:
            status = "partial_failure"
        else:
            status = "failed"

        with db.session_scope(for_tests=for_tests) as session:
            repositories.finish_pipeline_run(
                session, run_id, status, total_read, total_written, "; ".join(error_messages) or None,
            )

        summary["status"] = status
        summary["records_read"] = total_read
        summary["records_written"] = total_written
        return summary

    except Exception as exc:
        logger.exception("Falha inesperada no pipeline (run_id=%s)", run_id)
        with db.session_scope(for_tests=for_tests) as session:
            repositories.finish_pipeline_run(session, run_id, "failed", total_read, total_written, str(exc))
        summary["status"] = "failed"
        summary["error"] = str(exc)
        summary["records_read"] = total_read
        summary["records_written"] = total_written
        return summary
