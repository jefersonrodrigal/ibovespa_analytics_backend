"""Endpoint para disparar o pipeline manualmente.

Roda de forma síncrona (função `def`, não `async def` — o FastAPI já executa
endpoints síncronos numa threadpool, sem bloquear o event loop). Pode levar
alguns minutos na primeira carga; chamadas incrementais são rápidas.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.schemas import PipelineRunSummary
from src.pipeline import run_pipeline

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/run", response_model=PipelineRunSummary)
def trigger_pipeline_run() -> PipelineRunSummary:
    """Executa o pipeline completo (extração, validação, persistência, indicadores) e
    devolve o resumo real da execução — nunca reporta sucesso sem confirmação."""
    summary = run_pipeline(trigger="manual")
    return PipelineRunSummary(**summary)
