"""Configuração central da aplicação, carregada de variáveis de ambiente (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    """Levantado quando uma configuração obrigatória está ausente."""


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(
            f"Variável de ambiente obrigatória '{name}' não definida. "
            f"Copie .env.example para .env e preencha os valores."
        )
    return value


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    name: str
    user: str
    password: str

    @property
    def sqlalchemy_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


def get_database_config(for_tests: bool = False) -> DatabaseConfig:
    if for_tests:
        return DatabaseConfig(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            name=_require("DB_TEST_NAME"),
            user=_require("DB_TEST_USER"),
            password=_require("DB_TEST_PASSWORD"),
        )
    return DatabaseConfig(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        name=_require("DB_NAME"),
        user=_require("DB_USER"),
        password=_require("DB_PASSWORD"),
    )


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
PIPELINE_TIMEOUT_SECONDS = int(os.getenv("PIPELINE_TIMEOUT_SECONDS", "120"))
PIPELINE_MAX_RETRIES = int(os.getenv("PIPELINE_MAX_RETRIES", "3"))

TRADING_DAYS_PER_YEAR = 252
IBOVESPA_ASSET_ID = "^BVSP"
YFINANCE_SOURCE_ID = "YFINANCE"
BCB_SOURCE_ID = "BCB_SGS"
BRAPI_SOURCE_ID = "BRAPI"
BRAPI_API_KEY = os.getenv("BRAPI_API_KEY")
BRAPI_BASE_URL = "https://brapi.dev/api"

MACRO_SERIES = {
    "BCB_SGS_12": {"provider_code": "12", "unit": "% a.d.", "frequency": "daily"},
    "BCB_SGS_11": {"provider_code": "11", "unit": "% a.d.", "frequency": "daily"},
    "BCB_SGS_432": {"provider_code": "432", "unit": "% a.a.", "frequency": "event"},
    "BCB_SGS_1": {"provider_code": "1", "unit": "R$/US$", "frequency": "daily"},
    "BCB_SGS_433": {"provider_code": "433", "unit": "%", "frequency": "monthly"},
}
