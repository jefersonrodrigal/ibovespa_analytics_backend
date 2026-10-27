"""Modelos Pydantic das respostas estruturadas (resumos, health, execução do pipeline).

Endpoints que devolvem tabelas "brutas" (preços, indicadores, observações macro,
catálogo, fontes) retornam `list[dict]` sem um schema Pydantic dedicado — a forma
já é garantida pelo SQL em `src/storage/repositories.py` e documentada no docstring
de cada rota (visível em /docs).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    database_connected: bool
    last_successful_run_at: Optional[str] = None
    last_successful_run_reference_date: Optional[str] = None


class IbovespaSummary(BaseModel):
    last_trade_date: Optional[str] = None
    last_close: Optional[float] = None
    daily_return: Optional[float] = None
    month_to_date_return: Optional[float] = None
    year_to_date_return: Optional[float] = None
    return_252: Optional[float] = None
    volatility_21_annualized: Optional[float] = None
    current_drawdown: Optional[float] = None
    staleness_days: Optional[int] = None


class MacroSummary(BaseModel):
    selic_meta: Optional[dict] = None
    selic_efetiva: Optional[dict] = None
    cdi: Optional[dict] = None
    cdi_accumulated_12m: Optional[float] = None
    usd_brl: Optional[dict] = None
    usd_brl_accumulated_12m: Optional[float] = None
    ipca_monthly: Optional[dict] = None
    ipca_accumulated_12m: Optional[float] = None
    real_interest_rate_approx: Optional[float] = None


class ComparisonSeries(BaseModel):
    label: str
    dates: list[str]
    values: list[Optional[float]]


class ComparisonResponse(BaseModel):
    series: list[ComparisonSeries]
    real_return: Optional[dict] = None


class PipelineRunSummary(BaseModel):
    status: str
    reference_date: str
    records_read: int
    records_written: int
    steps: list[dict]
    staleness_warning: Optional[str] = None
    error: Optional[str] = None
