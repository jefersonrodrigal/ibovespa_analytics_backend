"""Médias móveis simples e distância percentual do preço em relação a elas."""
from __future__ import annotations

import pandas as pd


def moving_average(close: pd.Series, window: int) -> pd.Series:
    """Média móvel simples de `window` pregões. NaN enquanto não houver `window` observações."""
    return close.rolling(window=window, min_periods=window).mean()


def distance_from_ma_pct(close: pd.Series, ma: pd.Series) -> pd.Series:
    """Distância percentual do preço em relação à média móvel: close/ma - 1."""
    return close / ma - 1


def detect_crossover(short_ma: pd.Series, long_ma: pd.Series) -> pd.Series:
    """Retorna 'golden' quando a média curta cruza para cima da longa, 'death' para baixo,
    e None nos demais pontos. Requer ambas as médias calculadas (sem NaN) no ponto e no anterior.
    """
    diff = short_ma - long_ma
    prev_diff = diff.shift(1)
    result = pd.Series([None] * len(diff), index=diff.index, dtype=object)
    valid = diff.notna() & prev_diff.notna()
    result[valid & (prev_diff <= 0) & (diff > 0)] = "golden"
    result[valid & (prev_diff >= 0) & (diff < 0)] = "death"
    return result
