"""API REST (FastAPI) — expõe o Radar como serviço (tese SaaS dos docs).

Endpoints finos sobre os motores já testados (`scoring`, `decision`, `artifacts`,
`radar`, `pca`). A lógica de negócio vive nos módulos; aqui é só a fronteira HTTP.

Correr:  venv/Scripts/uvicorn licita.api:app --reload    (precisa de uvicorn)
Docs:    http://localhost:8000/docs  (OpenAPI automático do FastAPI)

Nota: os handlers são funções simples (o decorator do FastAPI devolve a função
original), por isso são testáveis diretamente, sem httpx/servidor.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import pncp
from .artifacts import generate_dossier
from .decision import CompanyProfile, ViabilityEngine
from .models import Edital
from .pca import ForecastEngine, PcaClient, load_pca_fixture
from .radar import Radar
from .scoring import CompatibilityScorer

_FIX = Path(__file__).parent / "fixtures"
_WEB = Path(__file__).parent / "web"
_scorer = CompatibilityScorer()

# Clientes AO VIVO (módulo-level de propósito: os testes injetam fakes aqui).
_pncp_client = pncp.PNCPClient()
_pca_client = PcaClient()

# Cache TTL dos resultados live — o PNCP é lento (segundos/página) e público;
# não martelamos a API deles a cada refresh do browser.
_LIVE_TTL_SECS = 600.0
_live_cache: dict[str, tuple[float, list[dict]]] = {}


def _cached(key: str, builder) -> tuple[list[dict], bool]:
    now = time.monotonic()
    hit = _live_cache.get(key)
    if hit and now - hit[0] < _LIVE_TTL_SECS:
        return hit[1], True
    rows = builder()
    _live_cache[key] = (now, rows)
    return rows, False


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


# ── Endpoints AO VIVO (PNCP real) ──────────────────────────────────────────


@app.get("/radar/live")
def radar_live(
    dias: int = 7,
    modalidade: int | None = 6,
    min_score: float = 0.0,
    max_paginas: int = 3,
) -> dict:
    """Radar sobre contratações REAIS do PNCP nos últimos `dias`.

    Pagina a API pública (até `max_paginas` × 50) e pontua tudo. Cache de 10 min
    por janela. `modalidade=6` = Pregão Eletrônico; `modalidade=0` remove o filtro.
    """
    dias = max(1, min(dias, 30))
    max_paginas = max(1, min(max_paginas, 10))
    mod = modalidade if modalidade else None
    fim = date.today()
    inicio = fim - timedelta(days=dias)
    key = f"radar:{inicio}:{fim}:{mod}:{max_paginas}"

    def build() -> list[dict]:
        editais = _pncp_client.fetch_contratacoes_all(
            inicio.strftime("%Y%m%d"), fim.strftime("%Y%m%d"),
            codigo_modalidade=mod, max_paginas=max_paginas,
        )
        return [o.to_dict() for o in Radar(_scorer).analyze(editais)]

    try:
        rows, from_cache = _cached(key, build)
    except Exception as e:  # PNCP em baixo/lento → 502 explícito, não 500 anónimo
        raise HTTPException(status_code=502, detail=f"PNCP indisponível: {e}")
    return {
        "items": [r for r in rows if r["score"]["value"] >= min_score],
        "meta": {
            "fonte": "pncp-live",
            "janela": [inicio.isoformat(), fim.isoformat()],
            "modalidade": mod,
            "total_analisado": len(rows),
            "cache": from_cache,
        },
    }


@app.get("/forecast/live")
def forecast_live(
    ano: int = 0,
    min_score: float = 0.0,
    id_usuario: int = 3,
    max_paginas: int = 2,
) -> dict:
    """Forecast sobre itens de PCA REAIS do PNCP (amostra paginada).

    Honestidade: o universo de PCA é >1M itens/ano — isto é uma AMOSTRA de até
    `max_paginas` × 50 planos, pontuada e classificada por janela temporal.
    """
    hoje = date.today()
    ano = ano or hoje.year
    max_paginas = max(1, min(max_paginas, 10))
    key = f"pca:{ano}:{id_usuario}:{max_paginas}"

    def build() -> list[dict]:
        items = _pca_client.fetch_pca(ano, id_usuario=id_usuario, max_paginas=max_paginas)
        return [o.to_dict() for o in ForecastEngine(_scorer).forecast(items, hoje.year, hoje.month, 0.0)]

    try:
        rows, from_cache = _cached(key, build)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"PNCP indisponível: {e}")
    return {
        "items": [r for r in rows if r["score"]["value"] >= min_score],
        "meta": {
            "fonte": "pncp-pca-live",
            "ano": ano,
            "amostra": True,
            "total_analisado": len(rows),
            "cache": from_cache,
        },
    }


# ── Frontend (SPA do Radar) ────────────────────────────────────────────────
# A raiz serve o index.html; os restantes assets (css/js/svg) saem do mount
# estático. Montado por ÚLTIMO para não ensombrar as rotas de API acima.
if _WEB.is_dir():

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_WEB / "index.html")

    app.mount("/", StaticFiles(directory=str(_WEB), html=True), name="web")
