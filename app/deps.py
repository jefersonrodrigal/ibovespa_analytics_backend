"""Dependências compartilhadas dos endpoints (sessão de banco de dados)."""
from __future__ import annotations

from typing import Iterator

from sqlalchemy.orm import Session

from src.storage import db


def get_db() -> Iterator[Session]:
    with db.session_scope() as session:
        yield session
