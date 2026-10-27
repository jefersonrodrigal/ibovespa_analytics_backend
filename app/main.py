"""Ibovespa Analytics — API FastAPI.

Expõe, via HTTP/JSON, a mesma lógica de negócio usada pelo pipeline
(`src/analytics`, `src/storage`, `src/pipeline.py`) para o frontend React.
Nenhuma regra de negócio vive aqui — os módulos de rota só orquestram
chamadas a `src/*` e convertem o resultado para JSON.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app.api import health, ibovespa, macro, metodologia, pipeline, quality  # noqa: E402

app = FastAPI(
    title="Ibovespa Analytics API",
    description="Dados reais do Ibovespa (histórico + atualizações diárias) e séries macroeconômicas do BCB.",
    version="1.0.0",
)

_frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(ibovespa.router)
app.include_router(macro.router)
app.include_router(quality.router)
app.include_router(pipeline.router)
app.include_router(metodologia.router)
