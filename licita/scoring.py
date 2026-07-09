"""Scorer de compatibilidade — o IP central do Radar.

Determinístico, explicável e testável: casa a taxonomia da proposta de valor do
HeraclitusDB (logs imutáveis, auditoria, event sourcing, ...) contra o texto do
edital e devolve um score 0-100 com o detalhe do que casou e do que faltou.

Matching robusto para português: normaliza acentos e caixa antes de casar, e usa
fronteiras de palavra para evitar falsos positivos (ex.: "ia" dentro de "polícia").
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .models import CategoryHit, Edital, Recommendation, Score


def _norm(text: str) -> str:
    """minúsculas + remoção de acentos (NFKD) — casa 'auditória'≈'auditoria'."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


@dataclass(frozen=True)
class Category:
    """Uma dimensão da taxonomia: peso + termos que a evidenciam."""

    name: str
    weight: float
    terms: tuple[str, ...]


# Taxonomia default derivada de spec-0001. Pesos refletem a aderência ao core do
# HeraclitusDB: imutabilidade/auditoria valem mais que "IA" genérica.
DEFAULT_TAXONOMY: tuple[Category, ...] = (
    Category("logs_imutaveis", 1.0, (
        "log imutavel", "logs imutaveis", "registro imutavel", "registros imutaveis",
        "imutavel", "imutabilidade", "event sourcing", "append-only", "append only",
        "write-ahead", "wal", "ledger", "cadeia de blocos", "tamper", "worm",
    )),
    Category("auditoria", 1.0, (
        "auditoria", "auditavel", "auditabilidade", "trilha de auditoria",
        "rastreabilidade", "rastreavel", "proveniencia", "provenance", "log de acesso",
    )),
    Category("banco_de_dados", 0.95, (
        "banco de dados", "base de dados", "sgbd", "database", "data lake", "datalake",
        "big data", "postgres", "postgresql", "oracle", "sql server", "mysql",
        "armazenamento de dados", "data warehouse",
    )),
    Category("seguranca_compliance", 0.8, (
        "lgpd", "seguranca da informacao", "siem", "criptografia", "criptografico",
        "integridade", "merkle", "hash", "assinatura digital", "icp-brasil",
        "conformidade", "gestao de riscos", "iso 27001",
    )),
    Category("observabilidade", 0.7, (
        "observabilidade", "monitoramento", "monitoracao", "telemetria", "metricas",
        "logs", "logging", "elastic", "grafana", "prometheus",
    )),
    Category("inteligencia_artificial", 0.55, (
        "inteligencia artificial", "aprendizado de maquina", "machine learning",
        "busca vetorial", "embeddings", "rag", "modelo de linguagem", "llm",
        "processamento de linguagem natural",
    )),
)


def _term_present(norm_text: str, term: str) -> bool:
    """Casa `term` como sequência de palavras inteiras dentro de `norm_text`."""
    nterm = _norm(term)
    # Fronteiras: qualquer caractere não-alfanumérico (inclui início/fim) delimita.
    pattern = r"(?<![a-z0-9])" + re.escape(nterm) + r"(?![a-z0-9])"
    return re.search(pattern, norm_text) is not None


class CompatibilityScorer:
    """Calcula o score de compatibilidade de um edital contra a taxonomia."""

    def __init__(
        self,
        taxonomy: tuple[Category, ...] = DEFAULT_TAXONOMY,
        participar_min: float = 70.0,
        avaliar_min: float = 40.0,
    ) -> None:
        if not taxonomy:
            raise ValueError("taxonomy must not be empty")
        if not (0 <= avaliar_min <= participar_min <= 100):
            raise ValueError("thresholds must satisfy 0 <= avaliar_min <= participar_min <= 100")
        self.taxonomy = taxonomy
        self.participar_min = participar_min
        self.avaliar_min = avaliar_min

    def score(self, edital: Edital) -> Score:
        norm_text = _norm(edital.searchable_text())
        hits: list[CategoryHit] = []
        weighted_sum = 0.0
        total_weight = 0.0
        for cat in self.taxonomy:
            matched = tuple(t for t in cat.terms if _term_present(norm_text, t))
            present = len(matched) > 0
            hits.append(CategoryHit(cat.name, cat.weight, matched, present))
            total_weight += cat.weight
            if present:
                weighted_sum += cat.weight
        value = (weighted_sum / total_weight) * 100.0 if total_weight else 0.0
        return Score(value=value, recommendation=self._recommend(value), hits=tuple(hits))

    def _recommend(self, value: float) -> Recommendation:
        if value >= self.participar_min:
            return Recommendation.PARTICIPAR
        if value >= self.avaliar_min:
            return Recommendation.AVALIAR
        return Recommendation.IGNORAR
