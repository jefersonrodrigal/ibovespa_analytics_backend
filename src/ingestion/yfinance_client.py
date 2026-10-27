"""Cliente para a série histórica do Ibovespa via biblioteca yfinance (ticker ^BVSP).

Papel na arquitetura híbrida: usado apenas para o BACKFILL histórico (primeira
carga, quando ainda não há preços persistidos). As atualizações diárias
incrementais usam a brapi (ver `brapi_client.py`).

Limitação documentada: yfinance é uma biblioteca não oficial que consulta endpoints
não documentados publicamente do Yahoo Finance. Não há SLA garantido e o formato
pode mudar sem aviso. Os dados aqui NÃO são equivalentes aos dados oficiais da B3.
"""
from __future__ import annotations

import logging
import time
from datetime import date
from typing import Optional

import pandas as pd
import yfinance as yf

from src.config import settings
from src.ingestion.common import PriceFetchResult

logger = logging.getLogger(__name__)

TICKER = "^BVSP"


def fetch_ibovespa_history(
    start: Optional[date] = None,
    end: Optional[date] = None,
    period: Optional[str] = None,
    max_retries: int = settings.PIPELINE_MAX_RETRIES,
) -> PriceFetchResult:
    """Busca o histórico do Ibovespa. Nunca lança exceção: falhas voltam no resultado.

    Use `period="max"` para todo o histórico disponível, ou `start`/`end` para um
    intervalo específico (usado nas atualizações incrementais diárias).
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}"
    last_error: Optional[str] = None

    for attempt in range(1, max_retries + 1):
        try:
            ticker = yf.Ticker(TICKER)
            if period is not None:
                df = ticker.history(period=period, interval="1d", auto_adjust=False)
            else:
                df = ticker.history(start=start, end=end, interval="1d", auto_adjust=False)

            if df is None or df.empty:
                return PriceFetchResult("^BVSP", url, "empty", None, None, [])

            df = df.reset_index()
            df["Date"] = pd.to_datetime(df["Date"]).dt.date

            rows = []
            raw_records = []
            for _, record in df.iterrows():
                if pd.isna(record["Close"]) or record["Close"] <= 0:
                    logger.warning("Registro com fechamento inválido ignorado: %s", record.to_dict())
                    continue
                row = {
                    "trade_date": record["Date"],
                    "open": float(record["Open"]) if pd.notna(record["Open"]) else None,
                    "high": float(record["High"]) if pd.notna(record["High"]) else None,
                    "low": float(record["Low"]) if pd.notna(record["Low"]) else None,
                    "close": float(record["Close"]),
                    "volume": int(record["Volume"]) if pd.notna(record["Volume"]) and record["Volume"] > 0 else None,
                }
                rows.append(row)
                raw_records.append({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()})

            return PriceFetchResult("^BVSP", url, "ok", None, raw_records, rows)
        except Exception as exc:  # yfinance pode lançar várias exceções internas/HTTP
            last_error = str(exc)
            logger.warning("Tentativa %s/%s falhou para ^BVSP via yfinance: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 10))

    return PriceFetchResult("^BVSP", url, "error", last_error, None, [])
