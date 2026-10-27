"""Validação de qualidade dos dados recebidos das fontes, antes da persistência.

Nunca inventa ou corrige valores: apenas classifica, loga e, quando crítico,
rejeita o registro. Divergências não críticas (ex.: variação diária extrema)
são registradas como aviso, não como erro — o dado real da fonte é preservado.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

Severity = Literal["warning", "error"]


@dataclass
class QualityIssue:
    severity: Severity
    field: str
    message: str
    reference: str


EXTREME_DAILY_MOVE_THRESHOLD = 0.15  # 15% — acima disso, aviso (não bloqueio)
STALENESS_BUSINESS_DAYS_WARNING = 3


def validate_market_price_rows(rows: list[dict]) -> tuple[list[dict], list[QualityIssue]]:
    """Valida linhas de preço já padronizadas. Retorna (linhas_validas, problemas)."""
    issues: list[QualityIssue] = []
    seen_dates: set[date] = set()
    clean_rows: list[dict] = []

    sorted_rows = sorted(rows, key=lambda r: r["trade_date"])
    prev_close: float | None = None

    for row in sorted_rows:
        trade_date = row["trade_date"]
        close = row.get("close")

        if trade_date in seen_dates:
            issues.append(QualityIssue("error", "trade_date", f"Data duplicada no lote: {trade_date}", str(trade_date)))
            continue
        seen_dates.add(trade_date)

        if close is None or close <= 0:
            issues.append(QualityIssue("error", "close", f"Fechamento inválido ({close}) em {trade_date}", str(trade_date)))
            continue

        low, high, open_, volume = row.get("low"), row.get("high"), row.get("open"), row.get("volume")
        if low is not None and high is not None and low > high:
            issues.append(QualityIssue("warning", "low_high", f"low > high em {trade_date} (low={low}, high={high})", str(trade_date)))
        if volume is not None and volume < 0:
            issues.append(QualityIssue("warning", "volume", f"Volume negativo em {trade_date}", str(trade_date)))

        if prev_close is not None and prev_close > 0:
            move = close / prev_close - 1
            if abs(move) > EXTREME_DAILY_MOVE_THRESHOLD:
                issues.append(
                    QualityIssue(
                        "warning",
                        "close",
                        f"Variação diária extrema em {trade_date}: {move:+.2%} (fechamento anterior {prev_close}, atual {close})",
                        str(trade_date),
                    )
                )
        prev_close = close
        clean_rows.append(row)

    return clean_rows, issues


def validate_macro_observation_rows(rows: list[dict], series_id: str) -> tuple[list[dict], list[QualityIssue]]:
    issues: list[QualityIssue] = []
    seen_dates: set[date] = set()
    clean_rows: list[dict] = []

    for row in rows:
        obs_date = row["observation_date"]
        value = row.get("value")

        if obs_date in seen_dates:
            issues.append(QualityIssue("error", "observation_date", f"Data duplicada no lote ({series_id}): {obs_date}", str(obs_date)))
            continue
        seen_dates.add(obs_date)

        if value is None:
            issues.append(QualityIssue("error", "value", f"Valor nulo em {series_id} ({obs_date})", str(obs_date)))
            continue

        clean_rows.append(row)

    return clean_rows, issues


def check_staleness(last_available_date: date | None, as_of: date) -> QualityIssue | None:
    """Verifica se a última data disponível está defasada em relação a `as_of`.

    Não distingue feriados especificamente (exigiria calendário oficial B3/ANBIMA),
    mas ignora fins de semana na contagem de dias úteis aproximada.
    """
    if last_available_date is None:
        return QualityIssue("error", "staleness", "Nenhum dado disponível.", "")

    business_days_gap = 0
    cursor = last_available_date
    while cursor < as_of:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            business_days_gap += 1

    if business_days_gap > STALENESS_BUSINESS_DAYS_WARNING:
        return QualityIssue(
            "warning",
            "staleness",
            f"Última data disponível ({last_available_date}) está {business_days_gap} dias úteis atrás de {as_of}.",
            str(last_available_date),
        )
    return None
