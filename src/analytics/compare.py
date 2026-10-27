"""Comparações entre o Ibovespa e benchmarks (CDI, USD/BRL, IPCA).

Convenções documentadas na página de Metodologia:
- Séries normalizadas para base 100 na primeira data em comum entre as duas séries.
- Índice do CDI construído por capitalização composta diária: idx(t) = idx(t-1) * (1 + taxa_dia/100).
- Retorno real (deflacionado pelo IPCA) via equação de Fisher: (1+nominal)/(1+inflação) - 1.
- Comparações usam apenas datas em que AMBAS as séries têm observação (interseção),
  nunca preenchimento artificial de lacunas.
"""
from __future__ import annotations

import pandas as pd


def normalize_to_base(series: pd.Series, base: float = 100.0) -> pd.Series:
    """Reescala a série para começar em `base` no primeiro valor não nulo."""
    clean = series.dropna()
    if clean.empty:
        return series * float("nan")
    first = clean.iloc[0]
    if first == 0:
        return series * float("nan")
    return series / first * base


def build_compounded_index(daily_rate_pct: pd.Series, base: float = 100.0) -> pd.Series:
    """Constrói um índice por capitalização composta a partir de uma taxa diária em %.

    idx(0) = base; idx(t) = idx(t-1) * (1 + taxa(t)/100).
    """
    factors = 1 + daily_rate_pct.fillna(0) / 100
    index = factors.cumprod() * base
    index.iloc[0] = base
    return index


def align_on_common_dates(df_a: pd.DataFrame, df_b: pd.DataFrame, date_col: str = "date") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retorna as duas séries restritas às datas presentes em ambas (interseção)."""
    common = set(df_a[date_col]).intersection(set(df_b[date_col]))
    a = df_a[df_a[date_col].isin(common)].sort_values(date_col).reset_index(drop=True)
    b = df_b[df_b[date_col].isin(common)].sort_values(date_col).reset_index(drop=True)
    return a, b


def real_return_fisher(nominal_return: float | None, inflation_return: float | None) -> float | None:
    """Retorno real via equação de Fisher: (1+nominal)/(1+inflação) - 1."""
    if nominal_return is None or inflation_return is None:
        return None
    if (1 + inflation_return) == 0:
        return None
    return (1 + nominal_return) / (1 + inflation_return) - 1


def accumulated_rate(rate_pct: pd.Series) -> float | None:
    """Capitalização composta de uma série de taxas periódicas em %: ∏(1 + taxa/100) - 1.

    Usado tanto para CDI/Selic acumulados (observações diárias) quanto para o
    IPCA acumulado (observações mensais) — a mecânica de composição é a mesma,
    só a frequência das observações difere.
    """
    clean = rate_pct.dropna()
    if clean.empty:
        return None
    return float((1 + clean / 100).prod() - 1)


def trailing_window(df: pd.DataFrame, date_col: str, months: int, as_of: "pd.Timestamp | None" = None) -> pd.DataFrame:
    """Observações dos últimos `months` meses corridos até `as_of` (ou a última data da série)."""
    if df.empty:
        return df
    reference = as_of or pd.Timestamp(df[date_col].max())
    start = reference - pd.DateOffset(months=months)
    mask = (pd.to_datetime(df[date_col]) > start) & (pd.to_datetime(df[date_col]) <= reference)
    return df[mask]
