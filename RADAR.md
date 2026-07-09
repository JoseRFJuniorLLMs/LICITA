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
├── store.py      # EventStore: InMemory (testes) + Jsonl (append-only durável)
├── cli.py        # dashboard de terminal
└── fixtures/sample_pncp.json   # resposta PNCP realista (dev/teste offline)
tests/            # 12 testes (unittest, stdlib)
```

## Correr

```bash
# Dashboard offline (fixture, sem rede):
venv/Scripts/python.exe -m licita radar

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

  **Estado honesto:** o mapeamento evento→episódio é **testado** (cliente injetável,
  3 testes, sem grpcio). O round-trip AO VIVO precisa de `grpcio` no venv + o serviço
  HeraclitusDB a responder — que **não** estavam disponíveis na verificação
  (venv sem grpcio; 127.0.0.1:7474 fechado). Para ativar:
  ```bash
  venv/Scripts/pip install grpcio
  venv/Scripts/pip install -e D:/DEV/HeraclitusDB/sdk/python
  venv/Scripts/python.exe -m licita radar --heraclitus 127.0.0.1:7474
  ```
  Sem isso, a CLI imprime o dashboard e avisa (stderr) em vez de crashar.

## Avisos honestos sobre os docs (`md/`)

- **Sintaxe SQL-Ledger inventada** (`CREATE EVENT TYPE`, `VERIFY PROPOSAL WITH
  MERKLE_PROOF`) não existe no HeraclitusDB — ele usa **GQL** (`gql.pest`). Os
  eventos `BidAnalyzed`/`BidDetected` mapeiam para episódios normais + `attrs`.
- **Contato pré-edital com o órgão** (spec-0001) é juridicamente delicado
  (Lei 14.133/21 e improbidade) — tratar com cautela jurídica, não como feature.
- O parser do PNCP é defensivo e testado por fixture; os nomes de campos ao vivo
  podem exigir ajuste fino em `pncp.parse_item` (isolado de propósito).
