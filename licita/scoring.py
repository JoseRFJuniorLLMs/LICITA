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


# Nova Taxonomia Geral de TI: cobre todas as verticais principais.
# Pesos equilibrados (1.0) pois o objetivo agora é abranger qualquer oportunidade de TI.
DEFAULT_TAXONOMY: tuple[Category, ...] = (
    Category("desenvolvimento_software", 1.0, (
        "fabrica de software", "desenvolvimento", "api", "aplicativo", 
        "mobile", "frontend", "backend", "sistema web", "sistemas web", "software",
        "sustentacao de sistemas", "manutencao de software"
    )),
    Category("infraestrutura_nuvem", 1.0, (
        "cloud", "nuvem", "aws", "azure", "google cloud", "servidores", 
        "virtualizacao", "datacenter", "kubernetes", "docker", "hospedagem"
    )),
    Category("seguranca_informacao", 1.0, (
        "firewall", "antivirus", "soc", "pentest", "seguranca da informacao", 
        "lgpd", "criptografia", "seguranca cibernetica", "cyberseguranca"
    )),
    Category("suporte_outsourcing", 1.0, (
        "service desk", "help desk", "suporte tecnico", "outsourcing de impressao", 
        "manutencao de computadores", "atendimento ao usuario", "suporte de ti"
    )),
    Category("redes_conectividade", 1.0, (
        "switches", "roteadores", "wi-fi", "wifi", "cabeamento estruturado", 
        "fibra optica", "link de internet", "wan", "lan", "telecomunicacoes"
    )),
    Category("hardware_ti", 1.0, (
        "notebooks", "desktops", "computadores", "monitores", "servidores fisicos", 
        "storage", "equipamentos de informatica", "perifericos"
    )),
    Category("banco_de_dados_dados", 1.0, (
        "banco de dados", "big data", "data warehouse", "bi", "business intelligence", 
        "engenharia de dados", "sgbd", "bancos de dados"
    )),
    Category("licenciamento", 1.0, (
        "licenciamento", "licencas de software", "microsoft 365", "google workspace", 
        "adobe", "oracle", "vmware", "red hat"
    )),
    Category("inteligencia_artificial", 1.0, (
        "inteligencia artificial", "ia", "machine learning", "aprendizado de maquina",
        "visao computacional", "processamento de linguagem natural", "llm"
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
