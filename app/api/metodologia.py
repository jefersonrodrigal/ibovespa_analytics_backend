"""Serve o conteúdo de docs/metodologia.md — fonte única da verdade, também usada no README."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/api", tags=["metodologia"])

_DOC_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "metodologia.md"


@router.get("/metodologia", response_class=PlainTextResponse)
def get_metodologia() -> str:
    """Conteúdo em Markdown de docs/metodologia.md (fontes, fórmulas, limitações)."""
    if not _DOC_PATH.exists():
        raise HTTPException(status_code=404, detail="docs/metodologia.md não encontrado.")
    return _DOC_PATH.read_text(encoding="utf-8")
