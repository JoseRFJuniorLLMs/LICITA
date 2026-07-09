"""Cliente do PNCP (Portal Nacional de Contratações Públicas).

Fonte oficial de dados abertos de compras públicas (spec-0001). Este cliente
busca contratações via a API pública de consulta e normaliza cada item num
`Edital`. Sem dependências externas: usa `urllib` (stdlib).

Nota honesta: o parser mapeia os campos usuais do PNCP de forma defensiva
(`.get` com fallbacks), validado contra a fixture offline. O endpoint/campos ao
vivo podem exigir ajustes finos — por isso o parsing é isolado em `parse_item`,
testável sem rede, e o `raw` original é sempre preservado.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

from .models import Edital

# API pública de consulta do PNCP (dados abertos).
PNCP_BASE = "https://pncp.gov.br/api/consulta/v1"


def _get(d: dict[str, Any], *path: str, default: Any = None) -> Any:
    """Acesso encadeado seguro: _get(item, 'orgaoEntidade', 'razaoSocial')."""
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def parse_item(item: dict[str, Any]) -> Edital:
    """Normaliza um item da API do PNCP num `Edital`. Defensivo por design."""
    bid_id = (
        item.get("numeroControlePNCP")
        or item.get("numeroControlePncp")
        or item.get("id")
        or ""
    )
    objeto = item.get("objetoCompra") or item.get("objeto") or ""
    orgao = (
        _get(item, "orgaoEntidade", "razaoSocial")
        or _get(item, "orgaoEntidade", "nome")
        or item.get("orgao")
        or ""
    )
    uf = _get(item, "unidadeOrgao", "ufSigla") or item.get("uf")
    valor = item.get("valorTotalEstimado") or item.get("valorEstimado")
    try:
        valor = float(valor) if valor is not None else None
    except (TypeError, ValueError):
        valor = None
    modalidade = item.get("modalidadeNome") or item.get("modalidade")
    data_abertura = (
        item.get("dataAberturaProposta")
        or item.get("dataPublicacaoPncp")
        or item.get("dataAbertura")
    )
    url = item.get("linkSistemaOrigem") or item.get("url")
    # Texto para o scorer: objeto + informação/itens quando presentes.
    extra = item.get("informacaoComplementar") or item.get("descricao") or ""
    itens = item.get("itens") or []
    if isinstance(itens, list):
        extra += "\n" + "\n".join(
            str(it.get("descricao", "")) for it in itens if isinstance(it, dict)
        )
    return Edital(
        bid_id=str(bid_id),
        orgao=str(orgao),
        objeto=str(objeto),
        valor_estimado=valor,
        modalidade=modalidade,
        data_abertura=data_abertura,
        uf=uf,
        fonte="pncp",
        url=url,
        texto=str(extra).strip(),
        raw=item,
    )


def parse_response(payload: dict[str, Any]) -> list[Edital]:
    """Extrai a lista de itens de uma resposta do PNCP (campo `data`)."""
    items = payload.get("data") or payload.get("items") or payload.get("content") or []
    if not isinstance(items, list):
        return []
    return [parse_item(it) for it in items if isinstance(it, dict)]


class PNCPClient:
    """Busca contratações do PNCP. Injetável: `opener` permite testes/mocks."""

    def __init__(self, base_url: str = PNCP_BASE, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def fetch_contratacoes(
        self,
        data_inicial: str,
        data_final: str,
        pagina: int = 1,
        tamanho_pagina: int = 50,
        codigo_modalidade: int | None = None,
    ) -> list[Edital]:
        """GET /contratacoes/publicacao — janela [data_inicial, data_final] (YYYYMMDD)."""
        params = {
            "dataInicial": data_inicial,
            "dataFinal": data_final,
            "pagina": pagina,
            "tamanhoPagina": tamanho_pagina,
        }
        if codigo_modalidade is not None:
            params["codigoModalidadeContratacao"] = codigo_modalidade
        url = f"{self.base_url}/contratacoes/publicacao?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 (trusted gov host)
            payload = json.loads(resp.read().decode("utf-8"))
        return parse_response(payload)


def load_fixture(path: str | Path) -> list[Edital]:
    """Carrega editais de uma fixture JSON no formato de resposta do PNCP (offline)."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return parse_response(payload)


def editais_from_items(items: Iterable[dict[str, Any]]) -> list[Edital]:
    return [parse_item(it) for it in items]
