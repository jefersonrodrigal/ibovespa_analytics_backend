# Ibovespa Analytics — Backend

API FastAPI + pipeline de ingestão que alimenta o frontend React do projeto.
Nenhuma regra de negócio vive na camada HTTP: os módulos de rota (`app/api/`)
apenas orquestram chamadas a `src/` (ingestão, validação, persistência,
analytics) e convertem o resultado para JSON. `src/` não tem nenhuma
dependência de FastAPI — é Python puro, testável isoladamente.

**Regra central do projeto:** nenhum dado fictício é exibido. Quando não há
dado suficiente, os endpoints retornam `null`/lista vazia — nunca um valor
aproximado ou interpolado. Essa regra está refletida em toda a cadeia:
validação (`src/validation/quality.py`), cálculo de indicadores
(`src/analytics/`) e serialização (`app/serialization.py`).

Fontes, fórmulas e limitações conhecidas em detalhe:
[`docs/metodologia.md`](docs/metodologia.md) (também servido via
`GET /api/metodologia` para a página "Metodologia" do frontend).

## Stack

- **Python 3.12+** (testado com 3.15)
- **FastAPI** + **Uvicorn** (ASGI) — camada HTTP
- **SQLAlchemy 2.x** (`Engine`/`Session`, sem ORM declarativo — acesso via
  SQL/`pandas.read_sql` nos repositórios) + **psycopg2** — acesso ao Postgres
- **pandas** / **numpy** — toda a lógica de cálculo financeiro
- **Pydantic** — schemas de resposta (`app/schemas.py`)
- **PostgreSQL 15+** (desenvolvido e testado com PostgreSQL 18)
- **pytest** + **FastAPI `TestClient`** (via `httpx`) — suíte de testes
- **requests** — cliente HTTP para BCB SGS e brapi.dev
- **yfinance** — biblioteca para o backfill histórico do Ibovespa

Ver `requirements.txt` para as faixas de versão exatas de cada dependência.

## Estrutura de diretórios

```
backend/
  app/                       camada HTTP (FastAPI) — fina, sem regra de negócio
    main.py                    cria o FastAPI app, configura CORS, inclui os routers
    deps.py                    dependência de injeção: get_db() -> Session (via src.storage.db.session_scope)
    schemas.py                 modelos Pydantic das respostas estruturadas (summaries, health, pipeline run)
    serialization.py           DataFrame/Series -> JSON seguro (NaN/NaT/Decimal -> null/float)
    api/
      health.py                 GET /api/health
      ibovespa.py                GET /api/ibovespa/{prices,indicators,summary}
      macro.py                   GET /api/macro/{catalog,summary,comparison,<series_id>/observations}
      quality.py                 GET /api/quality/{pipeline-runs,pipeline-runs/{id}/steps,record-counts,sources}
      pipeline.py                 POST /api/pipeline/run
      metodologia.py               GET /api/metodologia (texto de docs/metodologia.md)

  src/                        lógica de negócio pura — sem dependência de FastAPI, importável/testável isoladamente
    config/settings.py          configuração via .env, constantes do domínio (TRADING_DAYS_PER_YEAR, MACRO_SERIES, ids de fonte)
    ingestion/
      yfinance_client.py          backfill histórico do Ibovespa (ticker ^BVSP, period="max")
      brapi_client.py              atualizações incrementais do Ibovespa (requer BRAPI_API_KEY)
      bcb_client.py                 séries macro via API SGS do Banco Central (janelas de até 3.600 dias)
      common.py                     PriceFetchResult — contrato comum de retorno dos clientes
    validation/quality.py        validação pré-persistência: duplicatas, preços inválidos, variação extrema, defasagem
    storage/
      db.py                        engine/sessão SQLAlchemy (cacheados por URL), session_scope() transacional
      repositories.py              todo o SQL: upserts idempotentes, leituras como DataFrame
    analytics/
      returns.py                   R(t), R(N), retorno no mês/ano
      moving_averages.py             MM20/50/200, distância % do preço, cruzamento (golden/death cross)
      risk.py                        volatilidade anualizada, drawdown, distribuição de retornos, melhores/piores pregões
      compare.py                     normalização base 100, índice por capitalização composta, equação de Fisher
    pipeline.py                  orquestra extract -> validate -> persist -> indicators -> consistency_check

  sql/schema.sql                schema completo (schemas raw/processed/analytics/ops), idempotente (IF NOT EXISTS)
  scripts/
    run_pipeline.py                execução manual do pipeline via CLI
    register_task_scheduler.ps1    registra a execução diária no Agendador de Tarefas do Windows
  docs/metodologia.md           fonte única da verdade sobre fontes, fórmulas e limitações
  tests/
    unit/                         fórmulas financeiras, fixtures sintéticas isoladas (sem banco)
    integration/                   persistência/idempotência/pipeline contra um Postgres de testes real
    quality/                       regras de validação de qualidade
    api/                           endpoints via FastAPI TestClient (banco vazio, indisponível, dado real)
  requirements.txt, pytest.ini, Dockerfile, .env.example
```

## Arquitetura de dados — camadas

```
raw        ->  processed      ->  analytics            ->  ops
(payload       (preços e          (indicadores            (execuções do
 bruto da       observações        derivados:              pipeline:
 fonte, com     padronizados:      retornos, médias        status, passos,
 proveniência)  market_prices,     móveis, volatilidade,   contagens,
                macro_observations) drawdown)              erros)
```

- **`raw.price_snapshots` / `raw.macro_snapshots`**: um registro por chamada a
  uma fonte externa, com `request_url`, `status` (`ok`/`empty`/`error`),
  `error_message` e o `raw_payload` (JSONB) completo. Preserva a proveniência
  bruta mesmo quando a extração falha — nunca é sobrescrito.
- **`processed.market_prices`**: um preço por `(asset_id, trade_date)`
  (`UNIQUE`). `source_id` registra **apenas quem escreveu a linha por último**
  — não faz parte da chave de unicidade, porque a estratégia híbrida de
  ingestão (yfinance no backfill, brapi nas atualizações) faz a fonte mudar
  entre execuções sem que isso deva gerar uma segunda linha para o mesmo
  pregão.
- **`processed.macro_observations`**: `UNIQUE (series_id, observation_date,
  source_id)` — aqui a fonte é sempre `BCB_SGS`, então a chave é efetivamente
  por `(series_id, observation_date)`.
- **`analytics.daily_indicators`**: um registro por `(asset_id, trade_date)`,
  recalculado por completo a cada execução do pipeline a partir de todo o
  histórico em `market_prices` (nunca incrementalmente — ver
  `recompute_daily_indicators` em `src/pipeline.py`), para que uma correção
  retroativa de preço pela fonte nunca deixe indicadores desatualizados
  "presos" no histórico.
- **`ops.pipeline_runs` / `ops.pipeline_run_steps`**: uma linha por execução
  do pipeline e uma por passo (`extract`, `validate`, `persist`, `indicators`,
  `consistency_check`) de cada fonte, com contagem de registros lidos/gravados
  e mensagem de erro — é o que alimenta a página "Qualidade dos Dados".

Tabelas de dimensão (`processed.sources`, `processed.assets`,
`processed.series_catalog`) são seedadas pelo próprio `sql/schema.sql`
(`INSERT ... ON CONFLICT DO NOTHING`) — não são "dados de mercado", são o
catálogo documentado de fontes e séries.

## API

CORS liberado apenas para `FRONTEND_ORIGIN` (padrão
`http://localhost:5173`). Documentação interativa automática em `/docs`
(Swagger) e `/redoc`.

### Saúde

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/health` | `{ database_connected, last_successful_run_at, last_successful_run_reference_date }`. Verifica a conexão real com o banco configurado — não depende de injeção de dependência de teste. |

### Ibovespa (`/api/ibovespa`)

| Método | Rota | Query params | Descrição |
|---|---|---|---|
| GET | `/prices` | `start?`, `end?` (ISO date) | Histórico bruto: `trade_date, open, high, low, close, volume, source_id, ingested_at`. |
| GET | `/indicators` | `start?`, `end?` | `analytics.daily_indicators` completo: retornos (21/63/126/252p), MM20/50/200 + distância %, volatilidade anualizada (21/63/252p), drawdown, running_max. |
| GET | `/summary` | — | KPIs da página Visão Geral (`IbovespaSummary`): último fechamento/data, variação diária, retorno no mês/ano (calculado on-the-fly a partir dos preços, não persistido), retorno 252p, vol. anualizada 21p, drawdown atual, dias de defasagem. Campos `null` quando o histórico é insuficiente — nunca um valor aproximado. |

### Macroeconomia (`/api/macro`)

| Método | Rota | Query params | Descrição |
|---|---|---|---|
| GET | `/catalog` | — | `series_id, name, provider_code, source_id, unit, frequency, description` de todas as séries cadastradas. |
| GET | `/{series_id}/observations` | `start?`, `end?` | Observações brutas de uma série (`observation_date, value, unit, frequency, source_id`). |
| GET | `/summary` | — | `MacroSummary`: últimos valores de Selic meta/efetiva, CDI, USD/BRL, IPCA; acumulados de 12 meses (CDI e IPCA via capitalização composta, USD/BRL via razão simples primeiro/último); juro real aproximado (Fisher entre Selic meta vigente e IPCA acumulado 12m). |
| GET | `/comparison` | `start?`, `end?` | `ComparisonResponse`: Ibovespa, CDI (capitalizado), USD/BRL e IPCA (capitalizado) normalizados em base 100 na primeira observação de cada série dentro do período — prontas para o gráfico de comparação. Inclui `real_return` (nominal, inflação acumulada, retorno real via Fisher) do Ibovespa no período. |

Identificadores de série usados pelo backend (`app/api/macro.py`):
`BCB_SGS_432` (Selic meta), `BCB_SGS_11` (Selic efetiva), `BCB_SGS_12` (CDI),
`BCB_SGS_1` (USD/BRL PTAX venda), `BCB_SGS_433` (IPCA mensal).

### Qualidade dos dados (`/api/quality`)

| Método | Rota | Query params | Descrição |
|---|---|---|---|
| GET | `/pipeline-runs` | `limit=30` | Execuções do pipeline, mais recentes primeiro. |
| GET | `/pipeline-runs/{run_id}/steps` | — | Passos de uma execução. `404` se `run_id` não existir. |
| GET | `/record-counts` | — | Contagem de registros por tabela/fonte-ou-série, com data mín./máx. |
| GET | `/sources` | — | Fontes cadastradas (`YFINANCE`, `BCB_SGS`, `BRAPI`) com descrição e notas de uso/termos. |

### Pipeline (`/api/pipeline`)

| Método | Rota | Descrição |
|---|---|---|
| POST | `/run` | Executa o pipeline completo de forma síncrona (endpoint `def`, roda em threadpool — não bloqueia o event loop) e devolve o resumo real (`PipelineRunSummary`): status, registros lidos/gravados, passos, aviso de defasagem. Chamado pelo botão "Executar pipeline agora" da página "Qualidade dos Dados". |

### Metodologia

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/metodologia` | Conteúdo de `docs/metodologia.md` como texto plano (`text/plain`), renderizado como Markdown pelo frontend. |

## Pipeline de ingestão

Orquestrado por `run_pipeline()` em `src/pipeline.py`, chamado tanto pelo
endpoint `POST /api/pipeline/run` quanto por `scripts/run_pipeline.py`
(execução agendada). Cada fonte roda em sua própria transação
(`session_scope`) — a falha de uma fonte não derruba as demais nem é
convertida silenciosamente em sucesso:

1. **`run_ibovespa_step`** — estratégia híbrida:
   - **Sem nenhum preço persistido** (primeira execução): `yfinance`,
     `period="max"`, fonte `YFINANCE`.
   - **Já existe histórico**: `brapi.dev`, pedindo apenas
     `última_data_persistida + 1 dia` até hoje, fonte `BRAPI`. Isso existe
     porque o plano gratuito da brapi limita o histórico por requisição a ~3
     meses — insuficiente para o backfill, mas perfeito para atualizações
     incrementais de poucos dias.
   - Grava o snapshot bruto (`raw.price_snapshots`) mesmo em erro, valida as
     linhas (`validate_market_price_rows`) e faz upsert idempotente em
     `processed.market_prices`.
2. **`run_macro_step`** (uma vez por série em `settings.MACRO_SERIES`) —
   busca o BCB SGS a partir da última observação persistida (ou do piso
   inicial de `hoje − 3.600 dias` na primeira carga de cada série), valida e
   faz upsert em `processed.macro_observations`.
3. **`recompute_daily_indicators`** — recalcula `analytics.daily_indicators`
   do zero a partir de **todo** o histórico de `market_prices` (não
   incremental — ver justificativa na seção de arquitetura de dados acima).
4. **`check_staleness`** — compara a última data disponível com a data de
   referência (dias úteis aproximados, sem calendário oficial B3/ANBIMA);
   gera aviso (não erro) acima de 3 dias úteis de defasagem.
5. Grava o resumo da execução em `ops.pipeline_runs`/`ops.pipeline_run_steps`.
   Status final: `success` (tudo ok), `partial_failure` (alguma fonte falhou
   mas ao menos uma teve sucesso) ou `failed` (nenhuma fonte teve sucesso, ou
   exceção não tratada — capturada no `except` externo de `run_pipeline`, que
   sempre registra `records_read`/`records_written` mesmo em falha total).

Execução manual:

```powershell
.venv\Scripts\python scripts\run_pipeline.py
```

Agendamento diário (Windows, Agendador de Tarefas):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_task_scheduler.ps1
```

Em Linux/Mac, via `cron`:

```cron
0 19 * * 1-5 /caminho/para/backend/.venv/bin/python /caminho/para/backend/scripts/run_pipeline.py --trigger scheduled
```

## Validação de qualidade (`src/validation/quality.py`)

Nunca inventa ou corrige valores — apenas classifica, loga e, quando crítico,
rejeita o registro antes da persistência:

- **Preços** (`validate_market_price_rows`): data duplicada no lote (erro),
  fechamento nulo/≤0 (erro), `low > high` (aviso), volume negativo (aviso),
  variação diária acima de 15% em módulo frente ao fechamento anterior
  (aviso — dado real preservado, só sinalizado).
- **Observações macro** (`validate_macro_observation_rows`): data duplicada
  no lote (erro), valor nulo (erro).
- **Defasagem** (`check_staleness`): aviso quando a última data disponível
  está a mais de 3 dias úteis da data de referência.

## Fórmulas financeiras (`src/analytics/`)

Todas operam sobre `pandas.Series` de preços de fechamento ordenados
ascendentemente por data de pregão (sem linhas para dias sem pregão). Janelas
sem histórico suficiente produzem `NaN`/`None` — nunca uma aproximação.

| Indicador | Fórmula | Módulo |
|---|---|---|
| Retorno diário | `R(t) = P(t)/P(t-1) - 1` | `returns.daily_return` |
| Retorno em N pregões | `R(N) = P(t)/P(t-N) - 1` (N ∈ {21, 63, 126, 252}) | `returns.return_n_periods` |
| Retorno no mês / ano | retorno acumulado desde a 1ª data ≥ início do mês/ano corrente até o último preço | `returns.month_to_date_return` / `year_to_date_return` |
| Média móvel simples | média dos últimos N fechamentos (N ∈ {20, 50, 200}) | `moving_averages.moving_average` |
| Distância da MA | `close/MA - 1` | `moving_averages.distance_from_ma_pct` |
| Cruzamento de médias | `"golden"` quando MA curta cruza para cima da longa, `"death"` para baixo | `moving_averages.detect_crossover` |
| Volatilidade anualizada | desvio-padrão amostral dos retornos diários na janela × √252 (N ∈ {21, 63, 252}) | `risk.rolling_volatility_annualized` |
| Drawdown | `DD(t) = P(t)/max(P(0..t)) - 1` (sempre ≤ 0) | `risk.drawdown` |
| Drawdown máximo | `MDD = min(DD(t))` no intervalo | `risk.max_drawdown` |
| Distribuição de retornos | contagem, média, desvio-padrão, mín/máx, percentis 5/25/50/75/95 | `risk.returns_distribution` |
| Normalização base 100 | `série / primeiro_valor_não_nulo × 100` | `compare.normalize_to_base` |
| Índice por capitalização composta | `idx(0) = 100; idx(t) = idx(t-1) × (1 + taxa(t)/100)` — usado para CDI e IPCA no gráfico de comparação | `compare.build_compounded_index` |
| Taxa acumulada composta | `∏(1 + taxa/100) - 1` — usado para CDI/IPCA acumulados 12m | `compare.accumulated_rate` |
| Retorno real (Fisher) | `(1 + nominal)/(1 + inflação) - 1` | `compare.real_return_fisher` |

`TRADING_DAYS_PER_YEAR = 252` (`src/config/settings.py` e
`src/analytics/risk.py`).

## Fontes de dados

| Dado | Fonte | Identificador | Observação |
|---|---|---|---|
| Ibovespa — backfill histórico | Yahoo Finance via `yfinance` | Ticker `^BVSP` | Fonte não oficial. Só usada quando não há nenhum preço persistido. |
| Ibovespa — atualizações diárias | brapi.dev | Ticker `^BVSP` | Fonte não oficial. Requer `BRAPI_API_KEY`, enviado via header `Authorization: Bearer` (nunca na URL, para não ficar gravado em claro no `request_url` da proveniência). Plano gratuito: histórico limitado a ~3 meses por requisição. |
| CDI (diário) | Banco Central — SGS | série `12` | API pública, sem autenticação. |
| Selic efetiva (diária) | Banco Central — SGS | série `11` | — |
| Selic meta (Copom) | Banco Central — SGS | série `432` | Publicada com data de vigência, que pode ser futura em relação à divulgação. |
| USD/BRL (PTAX venda) | Banco Central — SGS | série `1` | — |
| IPCA (variação mensal) | Banco Central — SGS | série `433` | BCB redistribui a série oficial calculada pelo IBGE; SIDRA não foi integrado diretamente nesta versão. |

A API do BCB SGS rejeita janelas de data acima de ~10 anos (confirmado
empiricamente: HTTP 406/502); `bcb_client.fetch_series` divide qualquer
período longo em janelas de até 3.600 dias e usa esse mesmo valor como piso
na primeira carga de cada série (quando ainda não há histórico persistido),
em vez de tentar adivinhar a data real de início de cada série.

Detalhes completos (inclusive a decisão de não integrar IBGE SIDRA e a
mecânica exata da estratégia híbrida de ingestão): `docs/metodologia.md`.

## Configuração (`.env`)

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=ibovespa_analytics
DB_USER=ibovespa_app
DB_PASSWORD=change-me

DB_TEST_NAME=ibovespa_analytics_test
DB_TEST_USER=ibovespa_app
DB_TEST_PASSWORD=change-me

LOG_LEVEL=INFO
PIPELINE_TIMEOUT_SECONDS=120
PIPELINE_MAX_RETRIES=3

BRAPI_API_KEY=change-me            # https://brapi.dev/dashboard
FRONTEND_ORIGIN=http://localhost:5173
```

`src/config/settings.py` carrega essas variáveis via `python-dotenv` e levanta
`ConfigError` (com mensagem explícita) se uma variável obrigatória estiver
ausente — nunca cai em um valor padrão silencioso para credenciais.

## Instalação e execução

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
# edite .env com host/porta/usuário/senha do PostgreSQL e o token da brapi
```

### Banco de dados

```sql
CREATE ROLE ibovespa_app LOGIN PASSWORD 'sua-senha-aqui';
CREATE DATABASE ibovespa_analytics OWNER ibovespa_app ENCODING 'UTF8';
CREATE DATABASE ibovespa_analytics_test OWNER ibovespa_app ENCODING 'UTF8';
```

```powershell
psql -U ibovespa_app -h localhost -d ibovespa_analytics -f sql\schema.sql
psql -U ibovespa_app -h localhost -d ibovespa_analytics_test -f sql\schema.sql
```

### Primeira carga de dados

```powershell
.venv\Scripts\python scripts\run_pipeline.py
```

### Subir a API

```powershell
.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

Swagger em `http://localhost:8000/docs`.

## Testes

```powershell
.venv\Scripts\pytest -q
```

76 testes em 4 suítes (`pytest.ini`: `testpaths = tests`):

- **`tests/unit/`** — fórmulas financeiras e regras de qualidade, fixtures
  sintéticas isoladas, sem banco de dados.
- **`tests/integration/`** — persistência, upsert idempotente, pipeline
  completo contra um PostgreSQL de testes real (`ibovespa_analytics_test`,
  nunca mockado).
- **`tests/quality/`** — regras de `src/validation/quality.py`.
- **`tests/api/`** — endpoints via FastAPI `TestClient`, cobrindo banco vazio,
  banco indisponível e resposta refletindo dado real persistido (nunca
  hardcoded).

`GET /api/health` verifica deliberadamente a conexão com o banco **configurado
de verdade** (via `src/storage/db.check_connection`), não um banco injetado
por dependência de teste — é por isso que o endpoint existe, para refletir o
estado real da infraestrutura.

## Docker

```bash
docker compose up --build   # a partir da raiz do repositório, não deste diretório
```

`Dockerfile` usa `python:3.12-slim`, instala `libpq-dev`/`gcc` (requeridos
por `psycopg2-binary`) e sobe `uvicorn app.main:app --host 0.0.0.0 --port
8000`. Orquestrado junto com `db` (Postgres) e `frontend` pelo
`docker-compose.yml` na raiz do projeto. **Não validado nesta máquina de
desenvolvimento** (sem Docker instalado; backend validado diretamente via
`uvicorn --reload`) — revise as credenciais em `docker-compose.yml` antes do
primeiro uso.

## Limitações conhecidas

- Sem calendário de feriados B3/ANBIMA — `check_staleness` usa apenas dias
  úteis aproximados (todo dia que não é sábado/domingo).
- `yfinance` acessa endpoints não documentados do Yahoo Finance; falhas
  transitórias não são automaticamente convertidas em sucesso — ficam
  registradas como erro na execução do pipeline.
- IBGE SIDRA não integrado diretamente (decisão documentada — o BCB SGS já
  redistribui o IPCA oficial do IBGE).
- Sem code-splitting/paginação nos endpoints de série histórica (`/prices`,
  `/indicators`, `/{series_id}/observations`) — devolvem o intervalo
  solicitado por completo; para o volume de dados do projeto (séries diárias
  de poucos anos) isso é aceitável, mas não escalaria para séries de alta
  frequência ou décadas de histórico sem paginação.
