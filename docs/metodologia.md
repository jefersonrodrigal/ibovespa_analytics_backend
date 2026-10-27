## Fontes de dados

| Dado | Fonte | Identificador | Observações |
|---|---|---|---|
| Ibovespa — histórico (backfill inicial) | Yahoo Finance, via biblioteca `yfinance` | Ticker `^BVSP` | **Fonte não oficial.** Usada apenas na primeira carga (quando ainda não há preços persistidos), para trazer o histórico longo necessário aos indicadores de 252 pregões/MM200. |
| Ibovespa — atualizações diárias (incremental) | brapi.dev | Ticker `^BVSP` | **Fonte não oficial** (também não é a B3). Usada para todas as atualizações após a primeira carga. Requer token (`BRAPI_API_KEY`). O plano gratuito permite no máximo 3 meses de histórico por requisição — por isso a brapi nunca é usada para o backfill, só para janelas curtas e incrementais (dias desde a última atualização), o que funciona em qualquer plano. |
| CDI (taxa diária) | Banco Central do Brasil — SGS | Série `12` | API pública, sem autenticação. |
| Selic efetiva (taxa diária) | Banco Central do Brasil — SGS | Série `11` | API pública, sem autenticação. |
| Selic meta (Copom) | Banco Central do Brasil — SGS | Série `432` | Publicada com data de vigência, que pode ser futura em relação à data de divulgação. |
| USD/BRL (PTAX venda) | Banco Central do Brasil — SGS | Série `1` | API pública, sem autenticação. |
| IPCA (variação mensal) | Banco Central do Brasil — SGS | Série `433` | O BCB redistribui a série oficial do IPCA, calculada pelo IBGE. O IBGE SIDRA não foi integrado diretamente nesta versão — decisão documentada, não uma lacuna oculta. |

### Limitação verificada da API do BCB SGS

Durante o desenvolvimento, confirmou-se empiricamente que a API pública do BCB SGS
rejeita (HTTP 406) ou falha (HTTP 502) quando o intervalo entre `dataInicial` e
`dataFinal` excede aproximadamente 10 anos, e rejeita janelas anteriores ao início
real de cada série. Por isso:

- O pipeline divide qualquer período longo em janelas de até 3.600 dias.
- Na primeira carga de uma série (sem histórico anterior), o piso inicial usado é
  `hoje − 3.600 dias` (~9,86 anos) em vez de uma tentativa de adivinhar a data real
  de início de cada série. Isso é uma limitação documentada de **profundidade do
  histórico inicial**, não uma data inventada para os valores em si — todo valor
  exibido é exatamente o que a API do BCB retornou.
- Atualizações incrementais subsequentes usam a última data já persistida como
  início, portanto essa limitação só afeta a primeira carga.

### Limitação da biblioteca yfinance

`yfinance` acessa endpoints não documentados publicamente do Yahoo Finance. Chamadas
podem falhar de forma transitória (erros de rede, alterações no formato de resposta).
O pipeline trata essas falhas com novas tentativas e backoff, e nunca substitui uma
falha por dados fictícios — se a extração falhar, a execução é registrada como erro
para aquela fonte.

### Estratégia híbrida de ingestão do Ibovespa (yfinance + brapi)

O pipeline decide a fonte automaticamente a cada execução, com base no que já
está persistido:

- **Sem nenhum preço persistido** (primeira execução): usa `yfinance` com
  `period="max"` para trazer todo o histórico disponível.
- **Já existe histórico**: usa a **brapi**, pedindo apenas o intervalo entre
  `última_data_persistida + 1 dia` e hoje.

Essa divisão existe porque, ao testar a brapi nesta sessão com um token real,
confirmou-se que o plano gratuito retorna HTTP 400 (com o código do plano
exigido) para qualquer período acima de 3 meses — insuficiente para o backfill,
mas perfeito para atualizações diárias de poucos dias.

A coluna `source_id` de `processed.market_prices` registra **apenas quem
escreveu aquele pregão por último** (não faz parte da chave de unicidade,
que é só `(asset_id, trade_date)`), evitando que o mesmo dia apareça duas vezes
quando a fonte muda entre execuções. O token da brapi é enviado via header
`Authorization: Bearer`, nunca como parâmetro de URL — não fica gravado em
claro no campo de proveniência (`request_url`) do snapshot bruto.

## Fórmulas utilizadas

Todas as fórmulas abaixo estão implementadas em `src/analytics/` e cobertas por
testes unitários em `tests/unit/`.

**Retorno diário**
```
R(t) = P(t) / P(t-1) - 1
```

**Retorno em N pregões**
```
R(N) = P(t) / P(t-N) - 1
```
Requer N+1 observações; com histórico insuficiente, o resultado é indisponível
(nunca uma aproximação).

**Médias móveis simples (20/50/200 pregões)**
Média aritmética simples dos últimos N fechamentos. Indisponível enquanto não
houver N observações.

**Volatilidade anualizada**
```
Vol = desvio-padrão amostral dos retornos diários da janela × √252
```
Convenção de 252 pregões/ano. Usa desvio-padrão amostral (ddof=1).

**Drawdown**
```
DD(t) = P(t) / max(P(0..t)) - 1
```

**Drawdown máximo**
```
MDD = mínimo de DD(t) no intervalo analisado
```

**Retorno real (equação de Fisher)**
```
Retorno real = (1 + retorno nominal) / (1 + inflação do período) - 1
```

**Índice de capitalização composta (CDI/Selic)**
```
idx(0) = 100
idx(t) = idx(t-1) × (1 + taxa_dia(t) / 100)
```

## Convenções e limitações de comparação

- Séries são normalizadas para base 100 na primeira observação disponível dentro
  do período selecionado — não há reindexação para uma data fixa global.
- Ibovespa, CDI e Selic têm frequência diária; o IPCA tem frequência mensal. A
  comparação visual entre séries de frequências diferentes mostra trajetórias
  reais, não um pareamento ponto-a-ponto por data.
- O retorno real deflacionado usa a inflação acumulada (capitalização composta
  das variações mensais do IPCA) dentro do mesmo intervalo do retorno nominal.
- Variações diárias do Ibovespa acima de 15% (em módulo) são destacadas como
  aviso de qualidade, mas **não são removidas**: são o dado real reportado pela
  fonte.
- Datas duplicadas no mesmo lote de ingestão são tratadas como erro de qualidade
  e a linha duplicada é descartada antes da persistência (a primeira ocorrência
  no lote é mantida).

## Frequência de atualização

O pipeline (`src/pipeline.py`, executável via `scripts/run_pipeline.py`) é
projetado para rodar uma vez por dia, após o fechamento do mercado. Ele é
idempotente: reexecuções no mesmo dia atualizam os registros existentes via
upsert (chave única por ativo/data para preços; por série/data/fonte para
observações macro), sem duplicar linhas.

## Diferença entre dados oficiais e dados de terceiros

Os valores do Ibovespa exibidos nesta aplicação vêm de duas fontes de
terceiros — Yahoo Finance (`yfinance`, histórico) e brapi.dev (atualizações
diárias) — **nunca diretamente da B3**. Pequenas diferenças de precisão,
horário de corte do pregão ou ajustes retroativos em relação à série oficial
da B3 são esperadas e não devem ser interpretadas como erro do pipeline. A
página "Qualidade dos Dados" mostra, por pregão, qual fonte gravou o valor
mais recente (`source_id`). As séries macroeconômicas
(CDI, Selic, USD/BRL, IPCA) vêm diretamente da API oficial do Banco Central do
Brasil (SGS).
