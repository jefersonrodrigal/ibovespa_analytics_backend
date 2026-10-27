"""Endpoints de macroeconomia: catálogo de séries, observações, resumo e comparação com o Ibovespa.

Toda métrica derivada (acumulados de 12 meses, juro real) é calculada aqui no
backend reusando `src/analytics/compare.py` — o frontend nunca recalcula regra
de negócio, só formata e exibe.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas import ComparisonResponse, ComparisonSeries, MacroSummary
from app.serialization import clean_float_list, df_to_records, series_to_record
from src.analytics import compare
from src.config import settings
from src.storage import repositories

router = APIRouter(prefix="/api/macro", tags=["macro"])

SELIC_META = "BCB_SGS_432"
SELIC_EFETIVA = "BCB_SGS_11"
CDI = "BCB_SGS_12"
USD_BRL = "BCB_SGS_1"
IPCA = "BCB_SGS_433"


def _with_normalized_dates(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["observation_date"] = pd.to_datetime(df["observation_date"]).dt.date
    return df


@router.get("/catalog")
def get_catalog(db: Session = Depends(get_db)) -> list[dict]:
    """Catálogo de séries macroeconômicas: series_id, nome, código no provedor, fonte, unidade, frequência."""
    return df_to_records(repositories.get_series_catalog(db))


@router.get("/summary", response_model=MacroSummary)
def get_summary(db: Session = Depends(get_db)) -> MacroSummary:
    """KPIs consolidados: últimos valores de Selic meta/efetiva/CDI/USD-BRL/IPCA, acumulados
    de 12 meses (CDI, USD/BRL, IPCA) e juro real aproximado (Fisher: Selic meta vs. IPCA 12m)."""
    selic_meta = _with_normalized_dates(repositories.get_macro_observations(db, SELIC_META))
    selic_efetiva = _with_normalized_dates(repositories.get_macro_observations(db, SELIC_EFETIVA))
    cdi = _with_normalized_dates(repositories.get_macro_observations(db, CDI))
    usd = _with_normalized_dates(repositories.get_macro_observations(db, USD_BRL))
    ipca = _with_normalized_dates(repositories.get_macro_observations(db, IPCA))

    def _last(df: pd.DataFrame) -> Optional[dict]:
        return None if df.empty else series_to_record(df.sort_values("observation_date").iloc[-1])

    cdi_12m = None
    if not cdi.empty:
        window = compare.trailing_window(cdi, "observation_date", months=12)
        cdi_12m = compare.accumulated_rate(window["value"].astype(float)) if not window.empty else None

    usd_12m = None
    if not usd.empty:
        window = compare.trailing_window(usd, "observation_date", months=12).sort_values("observation_date")
        if len(window) >= 2:
            usd_12m = float(window["value"].iloc[-1] / window["value"].iloc[0] - 1)

    ipca_12m = None
    if not ipca.empty:
        window = compare.trailing_window(ipca, "observation_date", months=12)
        ipca_12m = compare.accumulated_rate(window["value"].astype(float)) if not window.empty else None

    real_rate = None
    if not selic_meta.empty and ipca_12m is not None:
        selic_meta_atual = float(selic_meta.sort_values("observation_date").iloc[-1]["value"]) / 100
        real_rate = compare.real_return_fisher(selic_meta_atual, ipca_12m)

    return MacroSummary(
        selic_meta=_last(selic_meta),
        selic_efetiva=_last(selic_efetiva),
        cdi=_last(cdi),
        cdi_accumulated_12m=cdi_12m,
        usd_brl=_last(usd),
        usd_brl_accumulated_12m=usd_12m,
        ipca_monthly=_last(ipca),
        ipca_accumulated_12m=ipca_12m,
        real_interest_rate_approx=real_rate,
    )


@router.get("/comparison", response_model=ComparisonResponse)
def get_comparison(start: Optional[date] = None, end: Optional[date] = None, db: Session = Depends(get_db)) -> ComparisonResponse:
    """Ibovespa, CDI (capitalizado), USD/BRL e IPCA (capitalizado) normalizados em base 100
    na primeira observação de cada um dentro do período — prontos para o gráfico de
    comparação. Inclui também o retorno real do Ibovespa (Fisher) no mesmo período."""
    prices = repositories.get_market_prices(db, settings.IBOVESPA_ASSET_ID, start, end).sort_values("trade_date")
    if prices.empty:
        return ComparisonResponse(series=[])

    window_start, window_end = prices["trade_date"].iloc[0], prices["trade_date"].iloc[-1]
    series: list[ComparisonSeries] = [
        ComparisonSeries(
            label="Ibovespa",
            dates=[d.isoformat() for d in prices["trade_date"]],
            values=clean_float_list(compare.normalize_to_base(prices["close"].astype(float))),
        )
    ]

    cdi = _with_normalized_dates(repositories.get_macro_observations(db, CDI, window_start, window_end)).sort_values("observation_date")
    if not cdi.empty:
        series.append(ComparisonSeries(
            label="CDI (capitalizado)",
            dates=[d.isoformat() for d in cdi["observation_date"]],
            values=clean_float_list(compare.build_compounded_index(cdi["value"].astype(float))),
        ))

    usd = _with_normalized_dates(repositories.get_macro_observations(db, USD_BRL, window_start, window_end)).sort_values("observation_date")
    if not usd.empty:
        series.append(ComparisonSeries(
            label="USD/BRL",
            dates=[d.isoformat() for d in usd["observation_date"]],
            values=clean_float_list(compare.normalize_to_base(usd["value"].astype(float))),
        ))

    ipca = _with_normalized_dates(repositories.get_macro_observations(db, IPCA, window_start, window_end)).sort_values("observation_date")
    if len(ipca) >= 2:
        series.append(ComparisonSeries(
            label="IPCA (capitalizado)",
            dates=[d.isoformat() for d in ipca["observation_date"]],
            values=clean_float_list(compare.build_compounded_index(ipca["value"].astype(float))),
        ))

    real_return = None
    if not ipca.empty:
        inflation_cum = compare.accumulated_rate(ipca["value"].astype(float))
        nominal = float(prices["close"].iloc[-1] / prices["close"].iloc[0] - 1)
        real_return = {
            "nominal_return": nominal,
            "inflation_accumulated": inflation_cum,
            "real_return": compare.real_return_fisher(nominal, inflation_cum),
        }

    return ComparisonResponse(series=series, real_return=real_return)


@router.get("/{series_id}/observations")
def get_observations(series_id: str, start: Optional[date] = None, end: Optional[date] = None, db: Session = Depends(get_db)) -> list[dict]:
    """Observações de uma série macroeconômica: observation_date, value, unit, frequency, source_id."""
    return df_to_records(repositories.get_macro_observations(db, series_id, start, end))
