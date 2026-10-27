"""Endpoint de saúde: conectividade com o banco e última execução bem-sucedida."""
from __future__ import annotations

from fastapi import APIRouter

from app.schemas import HealthResponse
from src.storage import db, repositories

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Verifica a conexão real com o PostgreSQL (não assume sucesso)."""
    connected = db.check_connection()
    if not connected:
        return HealthResponse(database_connected=False)

    with db.session_scope() as session:
        last_run = repositories.get_last_successful_run(session)

    if last_run is None:
        return HealthResponse(database_connected=True)

    return HealthResponse(
        database_connected=True,
        last_successful_run_at=str(last_run["finished_at"]),
        last_successful_run_reference_date=str(last_run["reference_date"]),
    )
