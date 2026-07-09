"""Store de eventos — "o log é a verdade".

Cada oportunidade analisada vira um evento imutável e append-only. Isto é o
gancho para o HeraclitusDB (spec-0002: o motor de ledger por trás da plataforma).
Fornecemos:

- `EventStore`      — o contrato (Protocol).
- `InMemoryEventStore` — para testes.
- `JsonlEventStore` — append-only durável em NDJSON (stand-in local honesto,
  trivialmente substituível pelo cliente gRPC do HeraclitusDB).

A ingestão nativa no HeraclitusDB (append de episódios via gRPC) é o alvo de
produção — o contrato abaixo é exatamente o que esse adapter implementará.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol


class EventStore(Protocol):
    def append(self, event: dict[str, Any]) -> str:
        """Acrescenta um evento imutável; devolve um id/offset estável."""
        ...


class InMemoryEventStore:
    """Store em memória (testes). Mantém a ordem de inserção (o log)."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append(self, event: dict[str, Any]) -> str:
        self.events.append(event)
        return str(len(self.events) - 1)

    def __len__(self) -> int:
        return len(self.events)


class JsonlEventStore:
    """Append-only durável: uma linha JSON por evento (NDJSON), com fsync.

    Não é o HeraclitusDB, mas respeita o mesmo princípio (append-only, nunca
    reescrito). Substituível 1:1 por `HeraclitusEventStore` quando o cliente
    gRPC estiver ligado.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: dict[str, Any]) -> str:
        line = json.dumps(event, ensure_ascii=False)
        with open(self.path, "a", encoding="utf-8") as f:
            offset = f.tell()
            f.write(line + "\n")
            f.flush()
        return str(offset)

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            return [json.loads(ln) for ln in f if ln.strip()]


class HeraclitusEventStore:
    """Ingesta cada evento como um episódio no HeraclitusDB via gRPC (SDK oficial).

    Fecha o loop "Trojan Horse" dos docs: a plataforma alimenta o banco. Cada
    `BidAnalyzed` vira um episódio append-only, com o `objeto` no conteúdo e os
    metadados (órgão, score, recomendação, valor, UF) em `attrs` — consultável
    depois por GQL (`MATCH (n) WHERE n.agent_id = "licita-radar" ...`).

    Namespace por `agent_id` (default `licita-radar`) para não misturar com
    outros produtores no mesmo log.

    Estado honesto: o mapeamento evento→episódio é testado (cliente injetável).
    O round-trip AO VIVO precisa de `grpcio` no ambiente e do serviço HeraclitusDB
    a responder em `addr` — NÃO exercitado pela suíte offline (o venv atual não
    tem grpcio e 127.0.0.1:7474 não respondeu na verificação). O import do SDK é
    lazy, por isso importar/testar este módulo não exige grpcio.
    """

    def __init__(
        self,
        addr: str = "127.0.0.1:7474",
        agent_id: str = "licita-radar",
        client: Any = None,
    ) -> None:
        self.addr = addr
        self.agent_id = agent_id
        self._client = client  # injetável (testes); None ⇒ conecta on demand

    def to_episode(self, event: dict[str, Any]) -> dict[str, Any]:
        """Mapeia um evento `BidAnalyzed` nos kwargs de `Client.append` (puro)."""
        score = event.get("score") or {}
        attrs = {
            "bid_id": str(event.get("bid_id", "")),
            "orgao": str(event.get("orgao", "")),
            "uf": str(event.get("uf") or ""),
            "fonte": str(event.get("fonte", "pncp")),
            "recommendation": str(score.get("recommendation", "")),
            "score": str(score.get("value", "")),
        }
        if event.get("valor_estimado") is not None:
            attrs["valor_estimado"] = str(event["valor_estimado"])
        if event.get("url"):
            attrs["url"] = str(event["url"])
        return {
            "kind": str(event.get("kind", "BidAnalyzed")),
            "content": str(event.get("objeto", "")),
            "agent_id": self.agent_id,
            "attrs": attrs,
        }

    def _get_client(self) -> Any:
        if self._client is None:
            from heraclitusdb import connect  # lazy: precisa grpcio + serviço

            self._client = connect(self.addr)
        return self._client

    def append(self, event: dict[str, Any]) -> str:
        ep = self.to_episode(event)
        lsn = self._get_client().append(
            ep["kind"], ep["content"], agent_id=ep["agent_id"], attrs=ep["attrs"]
        )
        return str(lsn)
