"""Tipos compartilhados entre os clientes de ingestão de preços (yfinance, brapi)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class PriceFetchResult:
    asset_id: str
    url: str
    status: str  # 'ok' | 'empty' | 'error'
    error_message: Optional[str]
    raw_payload: Optional[list]
    rows: list[dict]  # [{"trade_date", "open", "high", "low", "close", "volume"}]
