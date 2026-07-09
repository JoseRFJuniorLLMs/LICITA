"""Heraclitus Gov Radar — MVP real e testável.

Núcleo do "Radar de Licitações" (spec-0001/0002): captura editais do PNCP,
calcula compatibilidade com a proposta de valor do HeraclitusDB (logs imutáveis,
auditoria, event sourcing, ...) e regista cada oportunidade como um evento.

Escopo honesto: isto é o CORE que prova o valor — captura + scoring determinístico
+ ingestão de eventos. NÃO é a "plataforma multibilionária" dos docs (CRM, LLMs,
dashboards, 5 SaaS): isso é roadmap. O scoring aqui é por palavras-chave
(explicável, sem custo, testável); matching semântico por LLM é um upgrade futuro.
"""

from .models import Edital, CategoryHit, Score, ScoredOpportunity, Recommendation
from .scoring import CompatibilityScorer, DEFAULT_TAXONOMY
from .radar import Radar
from .decision import (
    CompanyProfile,
    Decision,
    ViabilityEngine,
    ViabilityReport,
    Blocker,
    Requirement,
)
from .store import EventStore, InMemoryEventStore, JsonlEventStore, HeraclitusEventStore
from .pca import (
    PcaItem,
    ForecastEngine,
    ForecastedOpportunity,
    ForecastWindow,
)
from .artifacts import generate_dossier, habilitation_checklist, executive_summary

__all__ = [
    "Edital",
    "CategoryHit",
    "Score",
    "ScoredOpportunity",
    "Recommendation",
    "CompatibilityScorer",
    "DEFAULT_TAXONOMY",
    "Radar",
    "EventStore",
    "InMemoryEventStore",
    "JsonlEventStore",
    "HeraclitusEventStore",
    "CompanyProfile",
    "Decision",
    "ViabilityEngine",
    "ViabilityReport",
    "Blocker",
    "Requirement",
    "PcaItem",
    "ForecastEngine",
    "ForecastedOpportunity",
    "ForecastWindow",
    "generate_dossier",
    "habilitation_checklist",
    "executive_summary",
]
