"""Cálculos de retorno. Fórmulas conforme especificação do projeto:

    R(t)  = P(t) / P(t-1) - 1
    R(N)  = P(t) / P(t-N) - 1

Convenção: quando não há histórico suficiente para a janela solicitada, o
resultado é NaN — nunca uma aproximação. Pressupõe uma série de preços (`close`)
indexada por data de pregão, ordenada ascendentemente, sem lacunas de linhas
(dias sem pregão simplesmente não existem como linha).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def daily_return(close: pd.Series) -> pd.Series:
    """R(t) = P(t)/P(t-1) - 1. Primeira posição é NaN (sem P(t-1))."""
    return close / close.shift(1) - 1


def return_n_periods(close: pd.Series, n: int) -> pd.Series:
    """R(N) = P(t)/P(t-N) - 1. NaN para as primeiras N posições (histórico insuficiente)."""
    if n <= 0:
        raise ValueError("n deve ser positivo")
    return close / close.shift(n) - 1


def cumulative_return_since(close: pd.Series, dates: pd.Series, since: "pd.Timestamp | None") -> float | None:
    """Retorno acumulado desde a primeira data >= `since` até o último valor da série.

    Retorna None se não houver dado na janela ou se `since` for None.
    """
    if since is None or close.empty:
        return None
    mask = dates >= since
    if not mask.any():
        return None
    window = close[mask]
    if len(window) < 1:
        return None
    base = window.iloc[0]
    last = window.iloc[-1]
    if base is None or base == 0 or pd.isna(base):
        return None
    return float(last / base - 1)


def month_to_date_return(close: pd.Series, dates: pd.Series) -> float | None:
    if dates.empty:
        return None
    last_date = pd.Timestamp(dates.iloc[-1])
    month_start = last_date.replace(day=1)
    return cumulative_return_since(close, dates, month_start)


def year_to_date_return(close: pd.Series, dates: pd.Series) -> float | None:
    if dates.empty:
        return None
    last_date = pd.Timestamp(dates.iloc[-1])
    year_start = last_date.replace(month=1, day=1)
    return cumulative_return_since(close, dates, year_start)
