"""Radar — orquestra captura → scoring → ranking → ingestão de eventos.

É o "coração do sistema" (spec-0001) reduzido ao essencial e testável:
recebe editais de uma fonte, pontua cada um, ordena por compatibilidade e
regista as oportunidades como eventos imutáveis no store.
"""

from __future__ import annotations

from typing import Iterable

from .models import Edital, ScoredOpportunity
from .scoring import CompatibilityScorer
from .store import EventStore


class Radar:
    def __init__(self, scorer: CompatibilityScorer, store: EventStore | None = None) -> None:
        self.scorer = scorer
        self.store = store

    def analyze(self, editais: Iterable[Edital]) -> list[ScoredOpportunity]:
        """Pontua e ordena (desc). Não persiste — função pura, ideal p/ testes."""
        scored = [ScoredOpportunity(e, self.scorer.score(e)) for e in editais]
        scored.sort(key=lambda o: o.score.value, reverse=True)
        return scored

    def run(
        self, editais: Iterable[Edital], min_score: float = 0.0
    ) -> list[ScoredOpportunity]:
        """Analisa, filtra por `min_score` e grava um evento por oportunidade."""
        opportunities = [o for o in self.analyze(editais) if o.score.value >= min_score]
        if self.store is not None:
            for opp in opportunities:
                self.store.append(opp.to_event())
        return opportunities
