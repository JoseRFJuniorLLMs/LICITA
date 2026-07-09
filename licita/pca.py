"""Forecasting de PCA — o diferencial "antes do edital" (spec-0001).

Monitora os Planos Anuais de Contratação (PCA) publicados no PNCP e identifica
compras PLANEADAS para os próximos meses — antes de existir edital. Muda a
estratégia de "caçar editais" para "preparar-se antes da publicação".

Reutiliza o `CompatibilityScorer`: cada item planeado é pontuado como um edital,
e classificado por janela temporal (quantos meses à frente). Determinístico e
testável (a referência temporal é injetada, não `datetime.now()`).

Nota jurídica honesta: a antecipação serve para PREPARAR (documentação, atestados,
demonstração do produto, acompanhar a publicação) — NÃO para contato pré-edital
com o agente público, que é juridicamente delicado (Lei 14.133/21).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .models import Edital, Score
from .pncp import _get
from .scoring import CompatibilityScorer


@dataclass(frozen=True)
class PcaItem:
    """Um item de um Plano Anual de Contratação (compra planeada, sem edital)."""

    pca_id: str
    orgao: str
    objeto: str
    valor_estimado: float | None = None
    ano_previsto: int | None = None
    mes_previsto: int | None = None  # 1-12
    uf: str | None = None
    categoria: str | None = None
    fonte: str = "pncp-pca"
    texto: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def as_edital(self) -> Edital:
        """Adapta o item planeado a um `Edital` para reutilizar o scorer."""
        return Edital(
            bid_id=self.pca_id,
            orgao=self.orgao,
            objeto=self.objeto,
            valor_estimado=self.valor_estimado,
            uf=self.uf,
            fonte=self.fonte,
            texto=self.texto,
            raw=self.raw,
        )


def _to_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def parse_pca_item(item: dict[str, Any]) -> PcaItem:
    """Normaliza um item da API de PCA do PNCP (defensivo)."""
    pca_id = str(
        item.get("numeroControlePNCP")
        or item.get("numeroItem")
        or item.get("id")
        or ""
    )
    objeto = item.get("descricao") or item.get("descricaoItem") or item.get("objeto") or ""
    orgao = (
        _get(item, "orgaoEntidade", "razaoSocial")
        or item.get("orgao")
        or item.get("nomeOrgao")
        or ""
    )
    valor = _to_float(
        item.get("valorTotal")
        or item.get("valorTotalEstimado")
        or item.get("valorUnitarioEstimado")
    )
    ano = _to_int(item.get("anoPca") or item.get("ano") or item.get("anoDesejado"))
    mes = _to_int(item.get("mesPrevisto") or item.get("mesDesejado"))
    data = item.get("dataDesejada") or item.get("dataPrevista")
    if (ano is None or mes is None) and isinstance(data, str) and len(data) >= 7:
        # "2027-11-..." → ano=2027, mes=11
        try:
            ano = ano or int(data[:4])
            mes = mes or int(data[5:7])
        except ValueError:
            pass
    uf = _get(item, "unidadeOrgao", "ufSigla") or item.get("uf")
    categoria = item.get("categoriaItemPcaNome") or item.get("categoria")
    extra = item.get("informacaoComplementar") or item.get("justificativa") or ""
    return PcaItem(
        pca_id=pca_id,
        orgao=str(orgao),
        objeto=str(objeto),
        valor_estimado=valor,
        ano_previsto=ano,
        mes_previsto=mes,
        uf=uf,
        categoria=categoria,
        texto=str(extra),
        raw=item,
    )


def parse_pca_response(payload: dict[str, Any]) -> list[PcaItem]:
    items = payload.get("data") or payload.get("items") or payload.get("itens") or []
    if not isinstance(items, list):
        return []
    return [parse_pca_item(it) for it in items if isinstance(it, dict)]


def load_pca_fixture(path: str | Path) -> list[PcaItem]:
    return parse_pca_response(json.loads(Path(path).read_text(encoding="utf-8")))


def months_ahead(item: PcaItem, ref_year: int, ref_month: int) -> int | None:
    """Meses da referência até à previsão do item. `None` se sem previsão."""
    if item.ano_previsto is None:
        return None
    mes = item.mes_previsto if item.mes_previsto is not None else 6  # meio do ano
    delta = (item.ano_previsto - ref_year) * 12 + (mes - ref_month)
    return max(0, delta)


class ForecastWindow(str, Enum):
    IMINENTE = "iminente"  # <= 2 meses
    PROXIMO = "proximo"    # 3-6 meses
    FUTURO = "futuro"      # > 6 meses
    SEM_DATA = "sem_data"


def classify_window(months: int | None) -> ForecastWindow:
    if months is None:
        return ForecastWindow.SEM_DATA
    if months <= 2:
        return ForecastWindow.IMINENTE
    if months <= 6:
        return ForecastWindow.PROXIMO
    return ForecastWindow.FUTURO


@dataclass(frozen=True)
class ForecastedOpportunity:
    item: PcaItem
    score: Score
    months_ahead: int | None
    window: ForecastWindow

    @property
    def prepare_action(self) -> str:
        if self.window == ForecastWindow.FUTURO:
            return "Preparar atestados/documentação e demonstração; acompanhar publicação."
        if self.window in (ForecastWindow.PROXIMO, ForecastWindow.IMINENTE):
            return "Finalizar habilitação e proposta; monitorar publicação de perto."
        return "Sem data prevista; monitorar o PCA do órgão."

    def to_dict(self) -> dict[str, Any]:
        return {
            "pca_id": self.item.pca_id,
            "orgao": self.item.orgao,
            "objeto": self.item.objeto,
            "valor_estimado": self.item.valor_estimado,
            "uf": self.item.uf,
            "months_ahead": self.months_ahead,
            "window": self.window.value,
            "score": self.score.to_dict(),
            "prepare_action": self.prepare_action,
        }


class ForecastEngine:
    """Pontua e classifica itens de PCA por compatibilidade + janela temporal."""

    def __init__(self, scorer: CompatibilityScorer | None = None) -> None:
        self.scorer = scorer or CompatibilityScorer()

    def forecast(
        self,
        items: list[PcaItem],
        ref_year: int,
        ref_month: int,
        min_score: float = 0.0,
    ) -> list[ForecastedOpportunity]:
        out: list[ForecastedOpportunity] = []
        for item in items:
            score = self.scorer.score(item.as_edital())
            if score.value < min_score:
                continue
            m = months_ahead(item, ref_year, ref_month)
            out.append(ForecastedOpportunity(item, score, m, classify_window(m)))
        # Ordena por compatibilidade desc; empate → o mais próximo primeiro.
        out.sort(key=lambda o: (-o.score.value, o.months_ahead if o.months_ahead is not None else 9999))
        return out
