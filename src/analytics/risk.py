"""Indicadores de risco: volatilidade, drawdown e distribuição de retornos.

Fórmulas conforme especificação:
    Vol anualizada = desvio-padrão dos retornos diários da janela x sqrt(252)
    DD(t) = P(t) / max(P(0..t)) - 1
    MDD   = min(DD(t)) no intervalo analisado
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def rolling_volatility_annualized(daily_returns: pd.Series, window: int) -> pd.Series:
    """Volatilidade anualizada: desvio-padrão amostral dos retornos diários na janela x sqrt(252).
    NaN enquanto não houver `window` retornos válidos.
    """
    return daily_returns.rolling(window=window, min_periods=window).std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)


def running_max(close: pd.Series) -> pd.Series:
    return close.cummax()


def drawdown(close: pd.Series) -> pd.Series:
    """DD(t) = P(t) / max(P(0..t)) - 1. Sempre <= 0."""
    return close / running_max(close) - 1


def max_drawdown(dd: pd.Series) -> float | None:
    """MDD = valor mínimo de DD(t) no intervalo. None se a série estiver vazia."""
    if dd.empty or dd.dropna().empty:
        return None
    return float(dd.min())


def returns_distribution(daily_returns: pd.Series) -> dict:
    """Estatísticas descritivas da distribuição de retornos diários."""
    clean = daily_returns.dropna()
    if clean.empty:
        return {
            "count": 0, "mean": None, "std": None, "min": None, "max": None,
            "p5": None, "p25": None, "p50": None, "p75": None, "p95": None,
        }
    return {
        "count": int(clean.count()),
        "mean": float(clean.mean()),
        "std": float(clean.std(ddof=1)) if clean.count() > 1 else None,
        "min": float(clean.min()),
        "max": float(clean.max()),
        "p5": float(clean.quantile(0.05)),
        "p25": float(clean.quantile(0.25)),
        "p50": float(clean.quantile(0.50)),
        "p75": float(clean.quantile(0.75)),
        "p95": float(clean.quantile(0.95)),
    }


def best_worst_days(dates: pd.Series, daily_returns: pd.Series, n: int = 5) -> dict:
    """Os `n` melhores e piores pregões (por retorno diário) no intervalo informado."""
    df = pd.DataFrame({"trade_date": dates, "daily_return": daily_returns}).dropna()
    if df.empty:
        return {"best": [], "worst": []}
    best = df.nlargest(n, "daily_return").to_dict("records")
    worst = df.nsmallest(n, "daily_return").to_dict("records")
    return {"best": best, "worst": worst}
