"""Engine e sessão SQLAlchemy para acesso ao PostgreSQL."""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import DatabaseConfig, get_database_config


@lru_cache(maxsize=8)
def _engine_for_url(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, future=True)


def get_engine(for_tests: bool = False) -> Engine:
    """Engine cacheado pela URL de conexão resolvida (não pela flag `for_tests`).

    Isso garante que uma mudança de configuração (.env) sempre resolva para o
    engine correto, mesmo que `for_tests` permaneça o mesmo valor — importante
    para a suíte de testes, que também exercita o caminho `for_tests=False`
    apontando para o banco de testes via variáveis de ambiente.
    """
    config: DatabaseConfig = get_database_config(for_tests=for_tests)
    return _engine_for_url(config.sqlalchemy_url)


def get_session_factory(for_tests: bool = False) -> sessionmaker:
    return sessionmaker(bind=get_engine(for_tests=for_tests), future=True)


@contextmanager
def session_scope(for_tests: bool = False) -> Iterator[Session]:
    """Fornece uma sessão transacional: commit em sucesso, rollback em exceção."""
    factory = get_session_factory(for_tests=for_tests)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_connection(for_tests: bool = False) -> bool:
    try:
        engine = get_engine(for_tests=for_tests)
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return True
    except Exception:
        return False
