"""Fábrica de artefatos (spec-0002 §4), versão determinística.

Transforma um edital em documentos acionáveis: um **resumo executivo** de 1
página e um **checklist de habilitação** (Lei 14.133/21). Sem LLM — a geração é
determinística e testável; a redação por LLM de propostas técnicas é um upgrade
futuro. O checklist combina os documentos SEMPRE exigidos com os requisitos
específicos detectados no edital (reutiliza `decision.extract_requirements`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .decision import Requirement, ViabilityEngine, ViabilityReport, extract_requirements
from .models import Edital, Score
from .scoring import CompatibilityScorer

# Documentos de habilitação sempre exigidos (Lei 14.133/21, arts. 62-70).
_STANDARD_ITEMS: tuple[tuple[str, str], ...] = (
    ("juridica", "Ato constitutivo / contrato social consolidado"),
    ("juridica", "Comprovante de inscrição no CNPJ"),
    ("fiscal", "Certidão Negativa de Débitos Federais (RFB/PGFN) e FGTS"),
    ("fiscal", "Certidão Negativa de Débitos Estaduais"),
    ("fiscal", "Certidão Negativa de Débitos Municipais"),
    ("trabalhista", "Certidão Negativa de Débitos Trabalhistas (CNDT)"),
    ("economica", "Certidão negativa de falência / recuperação judicial"),
)


@dataclass(frozen=True)
class ChecklistItem:
    category: str  # juridica | fiscal | trabalhista | economica | tecnica
    item: str
    source: str  # "padrao" (sempre exigido) | "edital" (detectado no edital)
    detail: str = ""


def _fmt_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _requirement_to_item(r: Requirement) -> ChecklistItem | None:
    if r.code == "capital_social":
        return ChecklistItem(
            "economica",
            f"Comprovação de capital social mínimo de {_fmt_brl(float(r.required))}",
            "edital",
            "Contrato social integralizado ou balanço patrimonial.",
        )
    if r.code == "garantia":
        return ChecklistItem(
            "economica",
            f"Garantia contratual de {_fmt_brl(float(r.required))}",
            "edital",
            "Caução, seguro-garantia ou fiança bancária.",
        )
    if r.code == "volumetria":
        return ChecklistItem(
            "tecnica",
            f"Atestado de capacidade técnica: {float(r.required):g} TB/dia sustentados",
            "edital",
            "Emitido por pessoa jurídica de direito público ou privado.",
        )
    if r.code == "certificacao":
        return ChecklistItem("tecnica", f"Certificado {r.required}", "edital")
    return None  # prazo não é item de checklist (entra no resumo)


def habilitation_checklist(edital: Edital) -> list[ChecklistItem]:
    """Documentos de habilitação: base (sempre) + específicos do edital."""
    items = [ChecklistItem(cat, item, "padrao") for cat, item in _STANDARD_ITEMS]
    for r in extract_requirements(edital):
        it = _requirement_to_item(r)
        if it is not None:
            items.append(it)
    return items


def _prazo_dias(edital: Edital) -> int | None:
    for r in extract_requirements(edital):
        if r.code == "prazo":
            return int(r.required)
    return None


def executive_summary(edital: Edital, score: Score, report: ViabilityReport | None = None) -> str:
    """Resumo executivo em Markdown (1 página, leitura em segundos)."""
    prazo = _prazo_dias(edital)
    lines = [
        f"# Resumo Executivo — {edital.orgao}",
        "",
        f"- **Objeto:** {edital.objeto}",
        f"- **Valor estimado:** {_fmt_brl(edital.valor_estimado) if edital.valor_estimado else '—'}",
        f"- **Modalidade:** {edital.modalidade or '—'}   ·   **UF:** {edital.uf or '—'}",
        f"- **Abertura:** {edital.data_abertura or '—'}",
        f"- **Prazo de entrega:** {f'{prazo} dias úteis' if prazo is not None else '—'}",
        f"- **Fonte:** {edital.fonte}   ·   **ID:** {edital.bid_id}",
        f"- **Link:** {edital.url or '—'}",
        "",
        f"## Compatibilidade técnica: {score.value:.0f}%  ({score.recommendation.value})",
        "",
    ]
    if score.matched_categories:
        lines.append("**Aderências:** " + ", ".join(score.matched_categories))
    if score.missing_categories:
        lines.append("**Lacunas:** " + ", ".join(score.missing_categories))
    if report is not None:
        dec = report.decision.value.upper().replace("_", " ")
        lines += ["", f"## Recomendação Go/No-Go: **{dec}**  (P vitória {report.probability * 100:.0f}%)"]
        for b in report.blockers:
            tag = "🛑 IMPEDITIVO" if b.hard else "⚠️ Risco"
            lines.append(f"- {tag}: {b.detail}")
    return "\n".join(lines)


def render_checklist_md(items: list[ChecklistItem]) -> str:
    order = ["juridica", "fiscal", "trabalhista", "economica", "tecnica"]
    titles = {
        "juridica": "Habilitação Jurídica",
        "fiscal": "Regularidade Fiscal",
        "trabalhista": "Regularidade Trabalhista",
        "economica": "Qualificação Econômico-Financeira",
        "tecnica": "Qualificação Técnica",
    }
    out = ["# Checklist de Habilitação (Lei 14.133/21)", ""]
    for cat in order:
        group = [i for i in items if i.category == cat]
        if not group:
            continue
        out.append(f"## {titles[cat]}")
        for i in group:
            mark = " _(detectado no edital)_" if i.source == "edital" else ""
            out.append(f"- [ ] {i.item}{mark}")
            if i.detail:
                out.append(f"      - {i.detail}")
        out.append("")
    return "\n".join(out)


def generate_dossier(
    edital: Edital,
    scorer: CompatibilityScorer | None = None,
    profile=None,
) -> str:
    """Dossiê completo em Markdown: resumo executivo + checklist de habilitação."""
    scorer = scorer or CompatibilityScorer()
    score = scorer.score(edital)
    report = ViabilityEngine(scorer).evaluate(edital, profile) if profile is not None else None
    return (
        executive_summary(edital, score, report)
        + "\n\n---\n\n"
        + render_checklist_md(habilitation_checklist(edital))
    )


def safe_filename(bid_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", bid_id).strip("_") or "edital"
