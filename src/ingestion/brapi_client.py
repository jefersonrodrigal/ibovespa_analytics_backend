"""Cliente para a API brapi.dev — usado para as atualizações diárias incrementais
do Ibovespa na arquitetura híbrida (o backfill histórico usa yfinance).

Documentação: https://brapi.dev/docs/acoes (endpoint de cotações/histórico).
Requer autenticação (`BRAPI_API_KEY`), enviada via header `Authorization: Bearer`
— nunca como parâmetro de URL, para que o token não seja persistido em claro no
campo `request_url` do snapshot de proveniência (`raw.price_snapshots`).

Limitação verificada nesta sessão: o plano gratuito da brapi permite no máximo
`range=3mo` de histórico por requisição (confirmado pela própria API, que retorna
HTTP 400 com o código do plano exigido quando se pede um período maior). Por isso
este cliente nunca é usado para o histórico completo — apenas para janelas curtas
e incrementais, dentro do que qualquer plano (inclusive o gratuito) já suporta.
"""
from __future__ import annotations

import logging
import time
from datetime import date
from typing import Optional

import requests

from src.config import settings
from src.ingestion.common import PriceFetchResult

logger = logging.getLogger(__name__)

TICKER = "^BVSP"


def fetch_ibovespa_history(
    start: Optional[date] = None,
    end: Optional[date] = None,
    timeout: int = settings.PIPELINE_TIMEOUT_SECONDS,
    max_retries: int = settings.PIPELINE_MAX_RETRIES,
) -> PriceFetchResult:
    """Busca o histórico recente do Ibovespa via brapi. Nunca lança exceção.

    Pensado para janelas curtas (atualização incremental diária). `start`/`end`
    são usados apenas para montar `startDate`/`endDate`; não há acesso a
    histórico profundo nesta fonte (ver limitação no docstring do módulo).
    """
    url = f"{settings.BRAPI_BASE_URL}/quote/{TICKER}"

    if not settings.BRAPI_API_KEY:
        return PriceFetchResult(
            "^BVSP", url, "error",
            "BRAPI_API_KEY não configurado em .env — atualização incremental via brapi indisponível.",
            None, [],
        )

    params = {"interval": "1d"}
    if start is not None:
        params["startDate"] = start.isoformat()
    if end is not None:
        params["endDate"] = end.isoformat()
    if start is None and end is None:
        params["range"] = "5d"

    headers = {"Authorization": f"Bearer {settings.BRAPI_API_KEY}"}
    last_error: Optional[str] = None

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
            response.raise_for_status()
            payload = response.json()

            if payload.get("error"):
                return PriceFetchResult("^BVSP", url, "error", payload.get("message", "Erro desconhecido da brapi"), payload, [])

            results = payload.get("results") or []
            if not results:
                return PriceFetchResult("^BVSP", url, "empty", None, payload, [])

            history = results[0].get("historicalDataPrice") or []
            if not history:
                return PriceFetchResult("^BVSP", url, "empty", None, payload, [])

            rows = []
            for item in history:
                try:
                    trade_date = date.fromtimestamp(int(item["date"]))
                    close = float(item["close"])
                except (KeyError, ValueError, TypeError) as exc:
                    logger.warning("Registro inválido ignorado (brapi): %s (%s)", item, exc)
                    continue
                if close <= 0:
                    continue
                rows.append(
                    {
                        "trade_date": trade_date,
                        "open": float(item["open"]) if item.get("open") is not None else None,
                        "high": float(item["high"]) if item.get("high") is not None else None,
                        "low": float(item["low"]) if item.get("low") is not None else None,
                        "close": close,
                        "volume": int(item["volume"]) if item.get("volume") else None,
                    }
                )
            return PriceFetchResult("^BVSP", url, "ok", None, payload, rows)
        except requests.exceptions.RequestException as exc:
            last_error = str(exc)
            logger.warning("Tentativa %s/%s falhou para ^BVSP via brapi: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 10))

    return PriceFetchResult("^BVSP", url, "error", last_error, None, [])
