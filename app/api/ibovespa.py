"""Endpoints do Ibovespa: preços brutos, indicadores calculados e resumo de KPIs."""
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas import IbovespaSummary
from app.serialization import df_to_records
from src.analytics import returns as returns_mod
from src.config import settings
from src.storage import repositories

router = APIRouter(prefix="/api/ibovespa", tags=["ibovespa"])


@router.get("/prices")
def get_prices(start: Optional[date] = None, end: Optional[date] = None, db: Session = Depends(get_db)) -> list[dict]:
    """Histórico de preços (trade_date, open, high, low, close, volume, source_id, ingested_at)."""
    df = repositories.get_market_prices(db, settings.IBOVESPA_ASSET_ID, start, end)
    return df_to_records(df)


@router.get("/indicators")
def get_indicators(start: Optional[date] = None, end: Optional[date] = None, db: Session = Depends(get_db)) -> list[dict]:
    """Indicadores diários pré-calculados: retornos (21/63/126/252p), médias móveis,
    volatilidade anualizada (21/63/252p) e drawdown."""
    df = repositories.get_daily_indicators(db, settings.IBOVESPA_ASSET_ID, start, end)
    return df_to_records(df)


@router.get("/summary", response_model=IbovespaSummary)
def get_summary(db: Session = Depends(get_db)) -> IbovespaSummary:
    """KPIs consolidados para a página Visão Geral. Campos ausentes (None) significam
    histórico insuficiente para aquele cálculo — nunca um valor aproximado."""
    prices = repositories.get_market_prices(db, settings.IBOVESPA_ASSET_ID)
    if prices.empty:
        return IbovespaSummary()

    prices = prices.sort_values("trade_date").reset_index(drop=True)
    indicators = repositories.get_daily_indicators(db, settings.IBOVESPA_ASSET_ID).sort_values("trade_date")
    last_indicator = indicators.iloc[-1] if not indicators.empty else None

    close = prices["close"].astype(float)
    dates = pd.to_datetime(prices["trade_date"])
    last_trade_date = prices["trade_date"].iloc[-1]

    def _field(name: str) -> Optional[float]:
        if last_indicator is None:
            return None
        value = last_indicator.get(name)
        return None if value is None or pd.isna(value) else float(value)

    return IbovespaSummary(
        last_trade_date=last_trade_date.isoformat(),
        last_close=float(close.iloc[-1]),
        daily_return=_field("daily_return"),
        month_to_date_return=returns_mod.month_to_date_return(close, dates),
        year_to_date_return=returns_mod.year_to_date_return(close, dates),
        return_252=_field("return_252"),
        volatility_21_annualized=_field("vol_21_annual"),
        current_drawdown=_field("drawdown"),
        staleness_days=(date.today() - last_trade_date).days,
    )
