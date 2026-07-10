"""Modelos de domínio do Radar (dataclasses puras, zero dependências externas)."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class Edital:
    """Um edital/licitação normalizado a partir de uma fonte (ex.: PNCP).

    Campos mínimos para scoring e rastreabilidade. `raw` guarda o payload
    original da fonte (o log é a verdade: nunca descartamos o bruto)."""

    bid_id: str
    orgao: str
    objeto: str
    valor_estimado: float | None = None
    modalidade: str | None = None
    data_abertura: str | None = None  # ISO-8601 quando disponível
    uf: str | None = None
    fonte: str = "pncp"
    url: str | None = None
    texto: str = ""  # objeto + descrição + itens, concatenado para o scorer
    esfera: str | None = None  # federal | estadual | municipal | distrital
    data_publicacao: str | None = None  # dataPublicacaoPncp (p/ "novas")
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def searchable_text(self) -> str:
        """Todo o texto relevante para casar palavras-chave."""
        parts = [self.objeto or "", self.texto or "", self.modalidade or "", self.orgao or ""]
        return "\n".join(p for p in parts if p)


class Recommendation(str, Enum):
    PARTICIPAR = "participar"
    AVALIAR = "avaliar"
    IGNORAR = "ignorar"


@dataclass(frozen=True)
class CategoryHit:
    """Resultado de uma categoria da taxonomia num edital."""

    category: str
    weight: float
    matched: tuple[str, ...]  # termos encontrados
    present: bool

    @property
    def score(self) -> float:
        return 1.0 if self.present else 0.0


@dataclass(frozen=True)
class Score:
    """Score de compatibilidade 0-100 + explicação (matched/missing por categoria)."""

    value: float  # 0..100
    recommendation: Recommendation
    hits: tuple[CategoryHit, ...]

    @property
    def matched_categories(self) -> list[str]:
        return [h.category for h in self.hits if h.present]

    @property
    def missing_categories(self) -> list[str]:
        return [h.category for h in self.hits if not h.present]

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": round(self.value, 1),
            "recommendation": self.recommendation.value,
            "matched": self.matched_categories,
            "missing": self.missing_categories,
            "breakdown": [
                {"category": h.category, "weight": h.weight, "present": h.present, "matched": list(h.matched)}
                for h in self.hits
            ],
        }


@dataclass(frozen=True)
class ScoredOpportunity:
    """Um edital + o seu score. A unidade que vira evento no ledger."""

    edital: Edital
    score: Score

    def to_event(self) -> dict[str, Any]:
        """Payload de evento imutável (BidAnalyzed): o que se grava no HeraclitusDB."""
        return {
            "kind": "BidAnalyzed",
            "bid_id": self.edital.bid_id,
            "orgao": self.edital.orgao,
            "objeto": self.edital.objeto,
            "valor_estimado": self.edital.valor_estimado,
            "uf": self.edital.uf,
            "fonte": self.edital.fonte,
            "url": self.edital.url,
            "score": self.score.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self.edital)
        d.pop("raw", None)
        d["score"] = self.score.to_dict()
        return d
