"""API REST (FastAPI) — expõe o Radar como serviço (tese SaaS dos docs).

Endpoints finos sobre os motores já testados (`scoring`, `decision`, `artifacts`,
`radar`, `pca`). A lógica de negócio vive nos módulos; aqui é só a fronteira HTTP.

Correr:  venv/Scripts/uvicorn licita.api:app --reload    (precisa de uvicorn)
Docs:    http://localhost:8000/docs  (OpenAPI automático do FastAPI)

Nota: os handlers são funções simples (o decorator do FastAPI devolve a função
original), por isso são testáveis diretamente, sem httpx/servidor.
"""

from __future__ import annotations

import os
import time
from datetime import date, timedelta
from pathlib import Path

import secrets

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import mailer, pncp
from .artifacts import generate_dossier
from .decision import CompanyProfile, ViabilityEngine
from .models import Edital
from .participation import ConflictError, ParticipationStore
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

# Utilizadores + participações (event-sourced, NDJSON). Diretório configurável
# para o deploy (LICITA_DATA_DIR); default ./data relativo ao working dir.
_DATA_DIR = Path(os.environ.get("LICITA_DATA_DIR", "data"))
_participations = ParticipationStore(_DATA_DIR / "participations.ndjson")


def _cached(key: str, builder) -> tuple[list[dict], bool]:
    now = time.monotonic()
    hit = _live_cache.get(key)
    if hit and now - hit[0] < _LIVE_TTL_SECS:
        return hit[1], True
    try:
        rows = builder()
    except Exception:
        # Stale-while-error: o PNCP é instável — cache velha é melhor do que
        # nenhum dado. Só propaga se nunca tivermos conseguido nada.
        if hit:
            return hit[1], True
        raise
    _live_cache[key] = (now, rows)
    return rows, False


def _default_radar_build() -> list[dict]:
    """O build do radar live com os defaults (o que o frontend pede)."""
    fim = date.today()
    inicio = fim - timedelta(days=7)
    editais = _pncp_client.fetch_contratacoes_all(
        inicio.strftime("%Y%m%d"), fim.strftime("%Y%m%d"), codigo_modalidade=6, max_paginas=3,
    )
    return [o.to_dict() for o in Radar(_scorer).analyze(editais)]


def _warm_loop() -> None:
    """Aquece a cache do radar em background: o utilizador NUNCA espera o PNCP.

    Opt-in via LICITA_WARM_LIVE=1 (ligado no systemd de produção; OFF em testes
    para não puxar rede no import).
    """
    while True:
        try:
            fim = date.today()
            inicio = fim - timedelta(days=7)
            key = f"radar:{inicio}:{fim}:6:3"
            rows = _default_radar_build()
            _live_cache[key] = (time.monotonic(), rows)
        except Exception:
            pass  # próxima volta tenta de novo; a cache velha continua a servir
        time.sleep(_LIVE_TTL_SECS)


if os.environ.get("LICITA_WARM_LIVE") == "1":
    import threading

    threading.Thread(target=_warm_loop, daemon=True, name="licita-warm").start()


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


# ── Utilizadores & Participações (auth por token de sessão) ────────────────

# token → user_id, em memória (re-login após restart do serviço).
_sessions: dict[str, str] = {}


def _auth_user(authorization: str | None) -> str:
    """Resolve o Bearer token numa sessão válida → user_id, ou 401."""
    if authorization and authorization.startswith("Bearer "):
        uid = _sessions.get(authorization[7:])
        if uid:
            return uid
    raise HTTPException(status_code=401, detail="sessão inválida — faça login")


class RegisterIn(BaseModel):
    username: str
    password: str
    name: str = ""
    email: str = ""


class LoginIn(BaseModel):
    username: str
    password: str
    email: str = ""  # opcional: atualiza o email para receber dossiês


class ClaimIn(BaseModel):
    bid_id: str
    edital: dict = Field(default_factory=dict)  # snapshot p/ o email/dossiê


class ReleaseIn(BaseModel):
    bid_id: str


def _session_for(user) -> dict:
    token = secrets.token_urlsafe(24)
    _sessions[token] = user.user_id
    return {**user.to_dict(), "token": token}


@app.post("/auth/register", status_code=201)
def auth_register(body: RegisterIn) -> dict:
    """Cria a conta (usuário+senha) e já devolve uma sessão."""
    try:
        user = _participations.register_user(body.username, body.password, body.name, body.email)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _session_for(user)


@app.post("/auth/login")
def auth_login(body: LoginIn) -> dict:
    """Valida usuário+senha → sessão (token). Email opcional atualiza o cadastro."""
    user = _participations.authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="usuário ou senha inválidos")
    if body.email and "@" in body.email and body.email.strip().lower() != user.email:
        user = _participations.set_email(user.user_id, body.email)
    return _session_for(user)


@app.get("/participations")
def list_participations() -> list[dict]:
    """Quem está a estudar o quê — visível a todos (evita estudo duplicado)."""
    return [p.to_dict() for p in _participations.all_claims()]


@app.post("/participations", status_code=201)
def claim_participation(
    body: ClaimIn, background: BackgroundTasks, authorization: str | None = Header(default=None)
) -> dict:
    """Reclama a licitação para o utilizador da sessão (exclusivo) + dossiê por email."""
    user_id = _auth_user(authorization)
    try:
        p = _participations.claim(body.bid_id, user_id, body.edital)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    user = _participations.get_user(user_id)
    email_status = "sem_email"
    if user and user.email and body.edital:
        assunto, corpo = mailer.build_participation_email(user.name, body.edital)
        # Em background: o claim não espera pelo SMTP.
        background.add_task(mailer.send_email, user.email, assunto, corpo, _DATA_DIR / "outbox")
        email_status = "queued"
    return {**p.to_dict(), "email": email_status}


@app.post("/participations/release")
def release_participation(
    body: ReleaseIn, authorization: str | None = Header(default=None)
) -> dict:
    """Liberta a licitação (só o dono da sessão)."""
    user_id = _auth_user(authorization)
    try:
        released = _participations.release(body.bid_id, user_id)
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"released": released}


# ── Frontend (SPA do Radar) ────────────────────────────────────────────────
# A raiz serve o index.html; os restantes assets (css/js/svg) saem do mount
# estático. Montado por ÚLTIMO para não ensombrar as rotas de API acima.
if _WEB.is_dir():

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_WEB / "index.html")

    app.mount("/", StaticFiles(directory=str(_WEB), html=True), name="web")
