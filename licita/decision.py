"""Motor de Recomendação Go/No-Go (spec-0002 §3).

Transforma a compatibilidade técnica numa decisão real de licitar: extrai
requisitos do edital (capital social, atestado de volumetria, prazo, garantia,
certificação), cruza-os com o perfil da empresa e detecta **bloqueios
intransponíveis** (barreiras de habilitação/técnicas). Determinístico e testável.

Fórmula (adaptada da spec-0002):
    P_se = Φ × ∏ R_i × penalidade_prazo
onde Φ = aderência técnica (score/100), R_i ∈ {0,1} por requisito HARD (0 se há
cláusula impeditiva), e a penalidade de prazo é um fator SOFT (<1) para janelas
apertadas. Qualquer bloqueio HARD zera a probabilidade ⇒ NÃO PARTICIPAR.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .models import Edital
from .scoring import CompatibilityScorer, _norm

# Unidades de volumetria normalizadas para TB/dia.
_VOL_TO_TB = {"gb": 0.001, "tb": 1.0, "pb": 1000.0}


def parse_brl(s: str) -> float:
    """'3.000.000,00' → 3000000.0 (formato brasileiro: '.' milhar, ',' decimal)."""
    s = s.strip().replace(".", "").replace(",", ".")
    return float(s)


@dataclass(frozen=True)
class CompanyProfile:
    """Cadastro da empresa licitante (capacidade técnica e financeira)."""

    capital_social: float = 0.0
    volumetria_max_tb_dia: float = 0.0  # maior atestado de capacidade sustentada
    garantia_max: float = 0.0
    certificacoes: frozenset[str] = frozenset()
    prazo_confortavel_dias: int = 10  # abaixo disto o prazo é um risco

    @classmethod
    def from_dict(cls, d: dict) -> "CompanyProfile":
        return cls(
            capital_social=float(d.get("capital_social", 0) or 0),
            volumetria_max_tb_dia=float(d.get("volumetria_max_tb_dia", 0) or 0),
            garantia_max=float(d.get("garantia_max", 0) or 0),
            certificacoes=frozenset(d.get("certificacoes", []) or []),
            prazo_confortavel_dias=int(d.get("prazo_confortavel_dias", 10) or 10),
        )

    @classmethod
    def from_json_file(cls, path: str | Path) -> "CompanyProfile":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass(frozen=True)
class Requirement:
    code: str  # capital_social | volumetria | prazo | garantia | certificacao
    label: str
    required: float | str
    unit: str = ""
    hard: bool = True


@dataclass(frozen=True)
class Blocker:
    code: str
    hard: bool
    detail: str


class Decision(str, Enum):
    PARTICIPAR = "participar"
    AVALIAR = "avaliar"
    NAO_PARTICIPAR = "nao_participar"


@dataclass(frozen=True)
class ViabilityReport:
    edital_id: str
    compat: float  # 0..100 (aderência técnica Φ×100)
    probability: float  # 0..1 (P_se)
    decision: Decision
    blockers: tuple[Blocker, ...] = field(default_factory=tuple)
    requirements: tuple[Requirement, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "edital_id": self.edital_id,
            "compat": round(self.compat, 1),
            "probability": round(self.probability, 4),
            "decision": self.decision.value,
            "blockers": [
                {"code": b.code, "hard": b.hard, "detail": b.detail} for b in self.blockers
            ],
        }


def extract_requirements(edital: Edital) -> list[Requirement]:
    """Extrai requisitos do texto do edital via padrões (defensivo)."""
    t = _norm(edital.searchable_text())
    reqs: list[Requirement] = []

    m = re.search(r"capital social minimo de r\$\s*([\d.,]+)", t)
    if m:
        reqs.append(Requirement("capital_social", "Capital social mínimo", parse_brl(m.group(1)), "R$"))

    m = re.search(r"garantia(?:\s+contratual)?\s+de\s+r\$\s*([\d.,]+)", t)
    if m:
        reqs.append(Requirement("garantia", "Garantia contratual", parse_brl(m.group(1)), "R$"))

    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(tb|gb|pb)\s*/\s*dia", t)
    if m:
        val = float(m.group(1).replace(",", ".")) * _VOL_TO_TB[m.group(2)]
        reqs.append(Requirement("volumetria", "Atestado de volumetria", val, "TB/dia"))

    m = re.search(r"(\d+)\s*dias?\s*uteis", t)
    if m:
        # Prazo é SOFT: aperta a decisão, mas não desabilita por si só.
        reqs.append(Requirement("prazo", "Prazo de entrega", float(m.group(1)), "dias úteis", hard=False))

    for iso in re.findall(r"iso\s*(\d{4,5})", t):
        reqs.append(Requirement("certificacao", f"Certificação ISO {iso}", f"ISO {iso}", "cert"))

    return reqs


class ViabilityEngine:
    """Calcula P_se e a decisão Go/No-Go para um edital + perfil de empresa."""

    def __init__(self, scorer: CompatibilityScorer | None = None, participar_min: float = 0.5) -> None:
        self.scorer = scorer or CompatibilityScorer()
        self.participar_min = participar_min

    def evaluate(self, edital: Edital, profile: CompanyProfile) -> ViabilityReport:
        phi = self.scorer.score(edital).value / 100.0
        reqs = extract_requirements(edital)
        blockers: list[Blocker] = []
        prazo_penalty = 1.0

        for r in reqs:
            met, detail = self._check(r, profile)
            if met:
                continue
            blockers.append(Blocker(r.code, r.hard, detail))
            if not r.hard:
                prazo_penalty *= 0.8

        hard_block = any(b.hard for b in blockers)
        probability = 0.0 if hard_block else phi * prazo_penalty
        decision = self._decide(probability, hard_block)
        return ViabilityReport(
            edital.bid_id, phi * 100.0, probability, decision, tuple(blockers), tuple(reqs)
        )

    def _check(self, r: Requirement, p: CompanyProfile) -> tuple[bool, str]:
        if r.code == "capital_social":
            ok = p.capital_social >= float(r.required)
            return ok, (
                f"Exige capital social de R$ {float(r.required):,.2f}; "
                f"cadastro atual R$ {p.capital_social:,.2f}."
            )
        if r.code == "garantia":
            ok = p.garantia_max >= float(r.required)
            return ok, (
                f"Exige garantia de R$ {float(r.required):,.2f}; "
                f"capacidade atual R$ {p.garantia_max:,.2f}."
            )
        if r.code == "volumetria":
            ok = p.volumetria_max_tb_dia >= float(r.required)
            return ok, (
                f"Exige atestado de {float(r.required):g} TB/dia; "
                f"maior atestado atual {p.volumetria_max_tb_dia:g} TB/dia."
            )
        if r.code == "prazo":
            ok = p.prazo_confortavel_dias <= float(r.required)
            return ok, (
                f"Prazo de {int(r.required)} dias úteis abaixo do confortável "
                f"({p.prazo_confortavel_dias} dias) — risco de multa."
            )
        if r.code == "certificacao":
            ok = str(r.required) in p.certificacoes
            return ok, f"Exige {r.required}; ausente no cadastro."
        return True, ""

    def _decide(self, probability: float, hard_block: bool) -> Decision:
        if hard_block:
            return Decision.NAO_PARTICIPAR
        if probability >= self.participar_min:
            return Decision.PARTICIPAR
        return Decision.AVALIAR
