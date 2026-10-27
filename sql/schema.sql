-- Plataforma de Analytics do Ibovespa — esquema de banco de dados
-- Camadas: raw (proveniência bruta) -> processed (padronizado) -> analytics (indicadores) -> ops (execuções)
-- Idempotente: pode ser executado múltiplas vezes (idempotent via IF NOT EXISTS / CREATE OR REPLACE).

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS processed;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS ops;

-- ===================================================================
-- processed: dimensões (ativos, fontes, catálogo de séries macro)
-- ===================================================================

CREATE TABLE IF NOT EXISTS processed.sources (
    source_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    base_url        TEXT,
    description     TEXT,
    terms_notes     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processed.assets (
    asset_id        TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    asset_class     TEXT NOT NULL,
    currency        TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processed.series_catalog (
    series_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    provider_code   TEXT NOT NULL,
    source_id       TEXT NOT NULL REFERENCES processed.sources(source_id),
    unit            TEXT NOT NULL,
    frequency       TEXT NOT NULL,
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ===================================================================
-- raw: payloads brutos recebidos das fontes, preservando proveniência
-- ===================================================================

CREATE TABLE IF NOT EXISTS raw.price_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES processed.sources(source_id),
    asset_id        TEXT NOT NULL,
    request_url     TEXT,
    status          TEXT NOT NULL CHECK (status IN ('ok', 'empty', 'error')),
    error_message   TEXT,
    raw_payload     JSONB,
    collected_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_raw_price_snapshots_asset_time
    ON raw.price_snapshots (asset_id, collected_at DESC);

CREATE TABLE IF NOT EXISTS raw.macro_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES processed.sources(source_id),
    series_id       TEXT NOT NULL,
    request_url     TEXT,
    status          TEXT NOT NULL CHECK (status IN ('ok', 'empty', 'error')),
    error_message   TEXT,
    raw_payload     JSONB,
    collected_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_raw_macro_snapshots_series_time
    ON raw.macro_snapshots (series_id, collected_at DESC);

-- ===================================================================
-- processed: fatos padronizados
-- ===================================================================

-- Unicidade por (ativo, data): a estratégia híbrida de ingestão (backfill histórico
-- via yfinance, atualizações diárias incrementais via brapi) faz com que a fonte de
-- um mesmo pregão possa mudar ao longo do tempo. `source_id` registra apenas quem
-- escreveu a linha por último; não faz parte da chave para evitar duas linhas para
-- o mesmo pregão com fontes diferentes.
CREATE TABLE IF NOT EXISTS processed.market_prices (
    id              BIGSERIAL PRIMARY KEY,
    asset_id        TEXT NOT NULL REFERENCES processed.assets(asset_id),
    trade_date      DATE NOT NULL,
    open            NUMERIC(18, 6),
    high            NUMERIC(18, 6),
    low             NUMERIC(18, 6),
    close           NUMERIC(18, 6) NOT NULL,
    volume          BIGINT,
    source_id       TEXT NOT NULL REFERENCES processed.sources(source_id),
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_market_prices UNIQUE (asset_id, trade_date),
    CONSTRAINT ck_market_prices_close_positive CHECK (close > 0)
);

CREATE INDEX IF NOT EXISTS ix_market_prices_asset_date
    ON processed.market_prices (asset_id, trade_date);

CREATE TABLE IF NOT EXISTS processed.macro_observations (
    id                  BIGSERIAL PRIMARY KEY,
    series_id           TEXT NOT NULL REFERENCES processed.series_catalog(series_id),
    observation_date    DATE NOT NULL,
    value               NUMERIC(18, 6) NOT NULL,
    unit                TEXT NOT NULL,
    frequency           TEXT NOT NULL,
    publication_date    DATE,
    source_id           TEXT NOT NULL REFERENCES processed.sources(source_id),
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_macro_observations UNIQUE (series_id, observation_date, source_id)
);

CREATE INDEX IF NOT EXISTS ix_macro_observations_series_date
    ON processed.macro_observations (series_id, observation_date);

-- ===================================================================
-- analytics: indicadores derivados
-- ===================================================================

CREATE TABLE IF NOT EXISTS analytics.daily_indicators (
    id              BIGSERIAL PRIMARY KEY,
    asset_id        TEXT NOT NULL REFERENCES processed.assets(asset_id),
    trade_date      DATE NOT NULL,
    close           NUMERIC(18, 6) NOT NULL,
    daily_return    NUMERIC(18, 8),
    return_21       NUMERIC(18, 8),
    return_63       NUMERIC(18, 8),
    return_126      NUMERIC(18, 8),
    return_252      NUMERIC(18, 8),
    ma_20           NUMERIC(18, 6),
    ma_50           NUMERIC(18, 6),
    ma_200          NUMERIC(18, 6),
    dist_ma_20_pct  NUMERIC(18, 8),
    dist_ma_50_pct  NUMERIC(18, 8),
    dist_ma_200_pct NUMERIC(18, 8),
    vol_21_annual   NUMERIC(18, 8),
    vol_63_annual   NUMERIC(18, 8),
    vol_252_annual  NUMERIC(18, 8),
    drawdown        NUMERIC(18, 8),
    running_max     NUMERIC(18, 6),
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_daily_indicators UNIQUE (asset_id, trade_date)
);

CREATE INDEX IF NOT EXISTS ix_daily_indicators_asset_date
    ON analytics.daily_indicators (asset_id, trade_date);

-- ===================================================================
-- ops: execuções do pipeline
-- ===================================================================

CREATE TABLE IF NOT EXISTS ops.pipeline_runs (
    run_id          BIGSERIAL PRIMARY KEY,
    trigger         TEXT NOT NULL CHECK (trigger IN ('manual', 'scheduled')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL CHECK (status IN ('running', 'success', 'partial_failure', 'failed')) DEFAULT 'running',
    reference_date  DATE,
    records_read    INT NOT NULL DEFAULT 0,
    records_written INT NOT NULL DEFAULT 0,
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS ix_pipeline_runs_started
    ON ops.pipeline_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS ops.pipeline_run_steps (
    step_id         BIGSERIAL PRIMARY KEY,
    run_id          BIGINT NOT NULL REFERENCES ops.pipeline_runs(run_id) ON DELETE CASCADE,
    step_name       TEXT NOT NULL CHECK (step_name IN ('extract', 'validate', 'persist', 'indicators', 'consistency_check')),
    target          TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('ok', 'error', 'skipped')),
    records_read    INT NOT NULL DEFAULT 0,
    records_written INT NOT NULL DEFAULT 0,
    error_message   TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_pipeline_run_steps_run
    ON ops.pipeline_run_steps (run_id);

-- ===================================================================
-- Dados de referência (dimensões) — metadados reais e documentados,
-- não são "dados de mercado", são o catálogo de fontes/séries.
-- ===================================================================

INSERT INTO processed.sources (source_id, name, base_url, description, terms_notes) VALUES
    ('YFINANCE', 'Yahoo Finance (via biblioteca yfinance)', 'https://query1.finance.yahoo.com',
     'Série histórica do Ibovespa (^BVSP) obtida via biblioteca não oficial yfinance.',
     'Fonte não oficial, sem SLA documentado publicamente; usada no desenvolvimento inicial conforme especificação do projeto. Não equivalente aos dados oficiais da B3.'),
    ('BCB_SGS', 'Banco Central do Brasil — Sistema Gerenciador de Séries Temporais (SGS)', 'https://api.bcb.gov.br/dados/serie',
     'API pública e oficial do Banco Central do Brasil para séries temporais macroeconômicas.',
     'API pública, sem necessidade de autenticação. Dados oficiais do BCB.'),
    ('BRAPI', 'brapi.dev', 'https://brapi.dev/api',
     'API de cotações de ativos da B3 (terceiros, não oficial da B3). Usada apenas para as atualizações diárias incrementais do Ibovespa; o histórico de longo prazo vem do yfinance.',
     'Requer token de autenticação (BRAPI_API_KEY). Profundidade de histórico e limite de requisições dependem do plano contratado na brapi.dev.')
ON CONFLICT (source_id) DO NOTHING;

INSERT INTO processed.assets (asset_id, name, asset_class, currency) VALUES
    ('^BVSP', 'Ibovespa', 'index', 'BRL')
ON CONFLICT (asset_id) DO NOTHING;

INSERT INTO processed.series_catalog (series_id, name, provider_code, source_id, unit, frequency, description) VALUES
    ('BCB_SGS_12',  'CDI — taxa de juros (diária)',                     '12',  'BCB_SGS', '% a.d.', 'daily',   'Taxa de juros CDI, percentual ao dia.'),
    ('BCB_SGS_11',  'Selic — taxa de juros efetiva (diária)',           '11',  'BCB_SGS', '% a.d.', 'daily',   'Taxa de juros Selic efetiva, percentual ao dia.'),
    ('BCB_SGS_432', 'Selic — meta definida pelo Copom',                 '432', 'BCB_SGS', '% a.a.', 'event',   'Meta da taxa Selic fixada pelo Copom, percentual ao ano.'),
    ('BCB_SGS_1',   'Dólar americano (venda) — PTAX',                   '1',   'BCB_SGS', 'R$/US$', 'daily',   'Taxa de câmbio PTAX de venda, R$ por US$.'),
    ('BCB_SGS_433', 'IPCA — variação mensal',                           '433', 'BCB_SGS', '%',      'monthly', 'Índice Nacional de Preços ao Consumidor Amplo, variação mensal percentual.')
ON CONFLICT (series_id) DO NOTHING;
