"""Conversão de DataFrames/valores do pandas para JSON seguro (sem NaN/NaT/Decimal)."""
from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pandas as pd


def _clean_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):  # numpy scalars (int64, float64, bool_...)
        item = value.item()
        if isinstance(item, float) and math.isnan(item):
            return None
        return item
    return value


def df_to_records(df: pd.DataFrame) -> list[dict]:
    """Converte um DataFrame em uma lista de dicts prontos para JSON (NaN/NaT -> None)."""
    if df.empty:
        return []
    return [{k: _clean_value(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def series_to_record(series: "pd.Series | None") -> dict | None:
    if series is None:
        return None
    return {k: _clean_value(v) for k, v in series.to_dict().items()}


def clean_float_list(values: Any) -> list:
    """Converte uma Series/lista de floats para JSON seguro (NaN -> None)."""
    return [_clean_value(v) for v in values]
