"""Cliente para a API pública do Banco Central do Brasil (SGS).

Documentação: https://www3.bcb.gov.br/sgspub — API SGS pública, sem autenticação.
Formato do endpoint: https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json

Limitação documentada e verificada empiricamente nesta sessão (chamadas reais à API):
a API rejeita (HTTP 406) ou falha (HTTP 502) quando o intervalo entre `dataInicial`
e `dataFinal` excede aproximadamente 10 anos, e também rejeita janelas anteriores ao
início real da série. Por isso, este cliente (a) divide períodos longos em janelas de
até `MAX_WINDOW_DAYS` dias e (b) quando nenhuma data inicial é informada, usa como
piso `hoje - MAX_WINDOW_DAYS` em vez de tentar adivinhar a data de início real de
cada série — isso é documentado como limitação de profundidade do histórico macro
inicial (ver página de Metodologia), não uma data inventada para os valores.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

import requests

from src.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
MAX_WINDOW_DAYS = 3600  # ~9.86 anos; limite real observado é ~10 anos (3650 dias)


@dataclass
class SeriesFetchResult:
    series_id: str
    provider_code: str
    url: str
    status: str  # 'ok' | 'empty' | 'error'
    error_message: Optional[str]
    raw_payload: Optional[list]
    rows: list[dict]  # [{"observation_date": date, "value": float}]


def _build_url(provider_code: str, start: date, end: date) -> str:
    url = BASE_URL.format(code=provider_code)
    params = [
        "formato=json",
        f"dataInicial={start.strftime('%d/%m/%Y')}",
        f"dataFinal={end.strftime('%d/%m/%Y')}",
    ]
    return url + "?" + "&".join(params)


def _fetch_window(
    series_id: str, provider_code: str, start: date, end: date, timeout: int, max_retries: int,
) -> SeriesFetchResult:
    url = _build_url(provider_code, start, end)
    last_error: Optional[str] = None

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            if not payload:
                return SeriesFetchResult(series_id, provider_code, url, "empty", None, payload, [])
            rows = []
            for item in payload:
                try:
                    obs_date = datetime.strptime(item["data"], "%d/%m/%Y").date()
                    value = float(str(item["valor"]).replace(",", "."))
                except (KeyError, ValueError) as exc:
                    logger.warning("Registro inválido ignorado na série %s: %s (%s)", series_id, item, exc)
                    continue
                rows.append({"observation_date": obs_date, "value": value})
            return SeriesFetchResult(series_id, provider_code, url, "ok", None, payload, rows)
        except requests.exceptions.RequestException as exc:
            last_error = str(exc)
            logger.warning(
                "Tentativa %s/%s falhou para série %s (código %s, janela %s–%s): %s",
                attempt, max_retries, series_id, provider_code, start, end, exc,
            )
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 10))

    return SeriesFetchResult(series_id, provider_code, url, "error", last_error, None, [])


def fetch_series(
    series_id: str,
    provider_code: str,
    start: Optional[date] = None,
    end: Optional[date] = None,
    timeout: int = settings.PIPELINE_TIMEOUT_SECONDS,
    max_retries: int = settings.PIPELINE_MAX_RETRIES,
) -> SeriesFetchResult:
    """Busca uma série do BCB SGS, dividindo em janelas quando necessário. Nunca lança exceção.

    Se `start` for None, usa `end - MAX_WINDOW_DAYS` como piso (ver limitação no docstring
    do módulo). Agrega os resultados de todas as janelas; o status final é 'ok' se pelo
    menos uma janela teve sucesso, 'empty' se todas vieram vazias, e 'error' apenas se
    todas as janelas falharam.
    """
    end = end or date.today()
    start = start or (end - timedelta(days=MAX_WINDOW_DAYS))

    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=MAX_WINDOW_DAYS), end)
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)

    all_rows: list[dict] = []
    all_raw: list = []
    last_url = ""
    had_ok = False
    had_data = False
    errors: list[str] = []

    for window_start, window_end in windows:
        result = _fetch_window(series_id, provider_code, window_start, window_end, timeout, max_retries)
        last_url = result.url
        if result.status == "ok":
            had_ok = True
            had_data = had_data or bool(result.rows)
            all_rows.extend(result.rows)
            if result.raw_payload:
                all_raw.extend(result.raw_payload)
        elif result.status == "empty":
            had_ok = True
        else:
            errors.append(result.error_message or "erro desconhecido")

    if not had_ok:
        return SeriesFetchResult(series_id, provider_code, last_url, "error", "; ".join(errors), None, [])

    status = "ok" if had_data else "empty"
    return SeriesFetchResult(series_id, provider_code, last_url, status, None, all_raw or None, all_rows)
