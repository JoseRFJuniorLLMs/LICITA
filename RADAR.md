# Heraclitus Gov Radar — MVP (núcleo real e testado)

O **coração** do sistema descrito em `md/spec-0001` — captura de licitações +
scoring de compatibilidade + ingestão como eventos imutáveis. Código real que
corre e passa testes, não scaffolding.

## O que é (e o que ainda NÃO é)

**É:** pacote `licita/` — captura do PNCP, scorer de compatibilidade
determinístico/explicável, ranking Go/No-Go, e ingestão append-only de eventos
`BidAnalyzed`.

**Ainda não é** (roadmap dos docs, não implementado — para não inflacionar):
CRM, geração de propostas por LLM, dashboards web, os 5 SaaS, matching semântico
por LLM. O scoring aqui é por **palavras-chave ponderadas** (custo zero, testável);
o upgrade semântico por LLM é um passo futuro.

## Estrutura

```
licita/
├── models.py     # Edital, Score, ScoredOpportunity (dataclasses puras)
├── scoring.py    # CompatibilityScorer + DEFAULT_TAXONOMY (o IP central)
├── pncp.py       # cliente PNCP (urllib) + parser defensivo + load_fixture
├── radar.py      # orquestra captura → score → ranking → ingestão
├── decision.py   # motor Go/No-Go: extrai requisitos + bloqueios + P_se (spec-0002 §3)
├── artifacts.py  # dossiê: resumo executivo + checklist de habilitação (spec-0002 §4)
├── pca.py        # forecasting: oportunidades ANTES do edital, via PCA (spec-0001)
├── api.py        # API REST (FastAPI): score/decide/dossier/radar/forecast
├── store.py      # EventStore: InMemory · Jsonl · HeraclitusDB (gRPC)
├── cli.py        # dashboards de terminal (radar + forecast)
└── fixtures/     # sample_pncp.json · sample_profile.json · sample_pca.json
tests/            # 46 testes (unittest, stdlib)
```

## API REST (FastAPI) — o Radar como serviço (tese SaaS dos docs)

`licita/api.py` expõe os motores já testados por HTTP. 6 endpoints:
`GET /health` · `POST /score` · `POST /decide` · `POST /dossier` (Markdown) ·
`GET /radar/demo` · `GET /forecast/demo`. Docs OpenAPI automáticos em `/docs`.

```bash
venv/Scripts/pip install uvicorn         # dep de runtime para servir
venv/Scripts/uvicorn licita.api:app --reload
# → http://localhost:8000/docs
```

Handlers são funções finas sobre os motores; testados diretamente (sem httpx/
servidor). O schema OpenAPI valida com 6 paths.

## Forecasting de PCA (spec-0001 — "o diferencial que ninguém faz")

Monitora os Planos Anuais de Contratação (PCA) do PNCP e encontra compras
planeadas **meses antes do edital**, classificadas por janela temporal
(IMINENTE ≤2m · PROXIMO 3-6m · FUTURO >6m). Muda "caçar editais" para
"preparar-se antes da publicação".

```bash
venv/Scripts/python.exe -m licita forecast --ref 202707   # referência jul/2027
```

Exemplo: Ministério da Justiça, solução de auditoria/logs imutáveis, **R$42M,
previsão 11/2027 (PROXIMO, 4 meses), 89% compat** — antes de existir edital.

> **Nota jurídica:** a antecipação serve para PREPARAR (documentação, atestados,
> demonstração, acompanhar a publicação) — NÃO para contato pré-edital com o
> agente público, que é juridicamente delicado (Lei 14.133/21).

## Motor Go/No-Go (spec-0002 §3)

Transforma "compatibilidade" em **decisão de licitar**. Extrai requisitos do
edital (capital social, atestado de volumetria, prazo, garantia, certificação),
cruza com o `CompanyProfile` e detecta **bloqueios intransponíveis**. Fórmula
`P_se = Φ × ∏ R_i × penalidade_prazo`: qualquer bloqueio HARD zera ⇒ NÃO PARTICIPAR.

```python
from licita import Edital, CompanyProfile, ViabilityEngine
r = ViabilityEngine().evaluate(edital, CompanyProfile(capital_social=1_500_000, volumetria_max_tb_dia=20))
# r.decision == Decision.NAO_PARTICIPAR ; r.blockers == [capital, volumetria (HARD), prazo (SOFT)]
```

Exemplo: edital com 54% de aderência técnica mas capital exigido R$3M (empresa
tem R$1.5M) e atestado 50 TB/dia (empresa tem 20) → **NÃO PARTICIPAR, P=0%**.

## Correr

```bash
# Dashboard offline (fixture, sem rede):
venv/Scripts/python.exe -m licita radar

# Com decisão Go/No-Go por edital (perfil da empresa em JSON):
venv/Scripts/python.exe -m licita radar --profile licita/fixtures/sample_profile.json

# Gerar um dossiê .md (resumo executivo + checklist de habilitação) por oportunidade:
venv/Scripts/python.exe -m licita radar --profile licita/fixtures/sample_profile.json --artifacts out/

# Gravar eventos num ledger append-only (NDJSON):
venv/Scripts/python.exe -m licita radar --ledger data/ledger.ndjson

# Ao vivo no PNCP (janela YYYYMMDD YYYYMMDD):
venv/Scripts/python.exe -m licita radar --live 20260701 20260731

# Testes:
venv/Scripts/python.exe -m unittest discover -s tests -v
```

Exemplo de saída (fixture): Ministério da Saúde (auditoria + logs imutáveis) →
**89% PARTICIPAR**; SERPRO (BD + observabilidade) → **49% AVALIAR**; material de
limpeza → **0% IGNORAR**.

## Ligação ao HeraclitusDB

`store.EventStore` é o contrato de ingestão. Implementações:
- `InMemoryEventStore` — testes.
- `JsonlEventStore` — append-only durável em NDJSON (stand-in local).
- **`HeraclitusEventStore`** — append de cada `BidAnalyzed` como **episódio** no
  HeraclitusDB via o SDK oficial (`heraclitusdb.connect`). Mapeia: `objeto`→conteúdo,
  e órgão/score/recomendação/valor/UF→`attrs`; namespace `agent_id="licita-radar"`.
  Consultável depois por GQL:
  `MATCH (n) WHERE n.agent_id = "licita-radar" RETURN n`.

  **✅ VERIFICADO AO VIVO (2026-07-09):** round-trip completo provado contra um
  HeraclitusDB real (gRPC): `Radar.run` ingeriu 2 `BidAnalyzed`, e o GQL
  `MATCH (n) WHERE n.agent_id = "licita-radar" RETURN n` devolveu-os com
  score/recomendação intactos (attrs aninhados em `attrs`). Ativação:
  `pip install grpcio + -e <repo>/HeraclitusDB/sdk/python` e
  `python -m licita radar --heraclitus <addr>`. Sem SDK, a CLI degrada com
  aviso em stderr (não crasha).

## Avisos honestos sobre os docs (`md/`)

- **Sintaxe SQL-Ledger inventada** (`CREATE EVENT TYPE`, `VERIFY PROPOSAL WITH
  MERKLE_PROOF`) não existe no HeraclitusDB — ele usa **GQL** (`gql.pest`). Os
  eventos `BidAnalyzed`/`BidDetected` mapeiam para episódios normais + `attrs`.
- **Contato pré-edital com o órgão** (spec-0001) é juridicamente delicado
  (Lei 14.133/21 e improbidade) — tratar com cautela jurídica, não como feature.
- **✅ Parser validado contra o PNCP REAL (2026-07-09):** `fetch_contratacoes`
  na janela 2026-07-01→09 (Pregão Eletrônico) devolveu 10 contratações reais;
  `bid_id`/`orgao`/`objeto` todos preenchidos e o scorer comportou-se
  corretamente (0% para objetos irrelevantes). A API viva confere com a fixture.
- **✅ API servida ao vivo (2026-07-09):** `uvicorn licita.api:app` respondeu
  por HTTP real — `/health` 200, `/radar/demo` (2 opps, top 89%),
  `POST /score` (70% participar), `/docs` OpenAPI 200.
