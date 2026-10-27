"""Endpoints de qualidade dos dados: execuções do pipeline, fontes e contagem de registros."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.serialization import df_to_records
from src.storage import repositories

router = APIRouter(prefix="/api/quality", tags=["quality"])


@router.get("/pipeline-runs")
def get_pipeline_runs(limit: int = 30, db: Session = Depends(get_db)) -> list[dict]:
    """Histórico de execuções do pipeline, mais recentes primeiro."""
    return df_to_records(repositories.get_pipeline_runs(db, limit=limit))


@router.get("/pipeline-runs/{run_id}/steps")
def get_pipeline_run_steps(run_id: int, db: Session = Depends(get_db)) -> list[dict]:
    """Passos (extract/validate/persist/indicators/consistency_check) de uma execução específica."""
    steps = df_to_records(repositories.get_pipeline_run_steps(db, run_id))
    if not steps:
        raise HTTPException(status_code=404, detail=f"Nenhum passo encontrado para run_id={run_id}.")
    return steps


@router.get("/record-counts")
def get_record_counts(db: Session = Depends(get_db)) -> list[dict]:
    """Quantidade de registros por tabela/fonte-ou-série, com data mínima e máxima."""
    return df_to_records(repositories.get_record_counts(db))


@router.get("/sources")
def get_sources(db: Session = Depends(get_db)) -> list[dict]:
    """Fontes de dados cadastradas (BCB_SGS, YFINANCE, BRAPI), com descrição e observações de uso."""
    return df_to_records(repositories.get_sources(db))
