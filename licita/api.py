"""API REST (FastAPI) — expõe o Radar como serviço (tese SaaS dos docs).

Endpoints finos sobre os motores já testados (`scoring`, `decision`, `artifacts`,
`radar`, `pca`). A lógica de negócio vive nos módulos; aqui é só a fronteira HTTP.

Correr:  venv/Scripts/uvicorn licita.api:app --reload    (precisa de uvicorn)
Docs:    http://localhost:8000/docs  (OpenAPI automático do FastAPI)

Nota: os handlers são funções simples (o decorator do FastAPI devolve a função
original), por isso são testáveis diretamente, sem httpx/servidor.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from . import pncp
from .artifacts import generate_dossier
from .decision import CompanyProfile, ViabilityEngine
from .models import Edital
from .pca import ForecastEngine, load_pca_fixture
from .radar import Radar
from .scoring import CompatibilityScorer

_FIX = Path(__file__).parent / "fixtures"
_scorer = CompatibilityScorer()


class EditalIn(BaseModel):
    objeto: str
    orgao: str = ""
    valor_estimado: float | None = None
    modalidade: str | None = None
    uf: str | None = None
    texto: str = ""
    bid_id: str = "input"

    def to_edital(self) -> Edital:
        return Edital(
            bid_id=self.bid_id,
            orgao=self.orgao,
            objeto=self.objeto,
            valor_estimado=self.valor_estimado,
            modalidade=self.modalidade,
            uf=self.uf,
            texto=self.texto,
        )


class ProfileIn(BaseModel):
    capital_social: float = 0.0
    volumetria_max_tb_dia: float = 0.0
    garantia_max: float = 0.0
    certificacoes: list[str] = Field(default_factory=list)
    prazo_confortavel_dias: int = 10

    def to_profile(self) -> CompanyProfile:
        return CompanyProfile.from_dict(self.model_dump())


class DecideIn(BaseModel):
    edital: EditalIn
    profile: ProfileIn | None = None


app = FastAPI(title="Heraclitus Gov Radar API", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "heraclitus-gov-radar", "version": "0.1.0"}


@app.post("/score")
def score_endpoint(edital: EditalIn) -> dict:
    """Compatibilidade técnica (0-100) + recomendação, de um edital."""
    return _scorer.score(edital.to_edital()).to_dict()


@app.post("/decide")
def decide_endpoint(body: DecideIn) -> dict:
    """Decisão Go/No-Go: cruza requisitos do edital com o perfil da empresa."""
    profile = body.profile.to_profile() if body.profile else CompanyProfile()
    return ViabilityEngine(_scorer).evaluate(body.edital.to_edital(), profile).to_dict()


@app.post("/dossier", response_class=PlainTextResponse)
def dossier_endpoint(body: DecideIn) -> str:
    """Dossiê em Markdown: resumo executivo + checklist de habilitação."""
    profile = body.profile.to_profile() if body.profile else None
    return generate_dossier(body.edital.to_edital(), profile=profile)


@app.get("/radar/demo")
def radar_demo(min_score: float = 0.0) -> list[dict]:
    """Radar sobre a fixture PNCP embutida (offline) — oportunidades ranqueadas."""
    editais = pncp.load_fixture(_FIX / "sample_pncp.json")
    opps = [o for o in Radar(_scorer).analyze(editais) if o.score.value >= min_score]
    return [o.to_dict() for o in opps]


@app.get("/forecast/demo")
def forecast_demo(ref_year: int = 2027, ref_month: int = 7, min_score: float = 0.0) -> list[dict]:
    """Forecast de PCA sobre a fixture embutida — oportunidades antes do edital."""
    items = load_pca_fixture(_FIX / "sample_pca.json")
    return [o.to_dict() for o in ForecastEngine(_scorer).forecast(items, ref_year, ref_month, min_score)]
