"""CLI do Radar: `python -m licita [radar]`.

Por omissão corre offline sobre a fixture do PNCP (sem rede) e imprime um
dashboard de oportunidades ordenado por compatibilidade — a versão terminal do
painel de spec-0001. Com `--live D1 D2` (YYYYMMDD) busca o PNCP ao vivo.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import datetime

from . import pncp
from .artifacts import generate_dossier, safe_filename
from .decision import CompanyProfile, ViabilityEngine, ViabilityReport
from .models import ScoredOpportunity
from .pca import ForecastedOpportunity, ForecastEngine, load_pca_fixture
from .radar import Radar
from .scoring import CompatibilityScorer
from .store import HeraclitusEventStore, JsonlEventStore

FIXTURE = Path(__file__).parent / "fixtures" / "sample_pncp.json"
PCA_FIXTURE = Path(__file__).parent / "fixtures" / "sample_pca.json"


def _fmt_valor(v: float | None) -> str:
    if v is None:
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _bar(value: float, width: int = 20) -> str:
    filled = round(value / 100 * width)
    return "█" * filled + "░" * (width - filled)


def print_dashboard(
    opportunities: list[ScoredOpportunity],
    decisions: dict[str, ViabilityReport] | None = None,
) -> None:
    total = len(opportunities)
    compat = sum(1 for o in opportunities if o.score.value >= 40)
    muito = sum(1 for o in opportunities if o.score.value >= 70)
    print("=" * 60)
    print("  HERACLITUS RADAR — Oportunidades de Licitação")
    print("=" * 60)
    print(f"  Analisadas: {total}   Compatíveis (≥40): {compat}   Muito compatíveis (≥70): {muito}")
    print("-" * 60)
    for o in opportunities:
        s = o.score
        print(f"  [{s.value:5.1f}%] {_bar(s.value)}  {s.recommendation.value.upper()}")
        print(f"     {o.edital.orgao}  ·  {_fmt_valor(o.edital.valor_estimado)}  ·  {o.edital.uf or '—'}")
        print(f"     {o.edital.objeto[:88]}{'…' if len(o.edital.objeto) > 88 else ''}")
        if s.matched_categories:
            print(f"     ✓ {', '.join(s.matched_categories)}")
        if s.missing_categories:
            print(f"     ✗ {', '.join(s.missing_categories)}")
        rep = decisions.get(o.edital.bid_id) if decisions else None
        if rep is not None:
            dec = rep.decision.value.upper().replace("_", " ")
            print(f"     ▶ Go/No-Go: {dec}  (P vitória {rep.probability * 100:.0f}%)")
            for b in rep.blockers:
                print(f"        {'✗ HARD ' if b.hard else '! prazo'}  {b.detail}")
        print()


def print_forecast(opps: list[ForecastedOpportunity]) -> None:
    print("=" * 60)
    print("  HERACLITUS FORECAST — Oportunidades ANTES do edital (PCA)")
    print("=" * 60)
    print(f"  Itens planeados analisados: {len(opps)}")
    print("-" * 60)
    for o in opps:
        janela = o.window.value.upper()
        quando = f"{o.months_ahead} meses" if o.months_ahead is not None else "sem data"
        prev = (
            f"{o.item.mes_previsto:02d}/{o.item.ano_previsto}"
            if o.item.ano_previsto and o.item.mes_previsto
            else (str(o.item.ano_previsto) if o.item.ano_previsto else "—")
        )
        print(f"  [{o.score.value:5.1f}%] {_bar(o.score.value)}  {janela} ({quando})")
        print(f"     {o.item.orgao}  ·  {_fmt_valor(o.item.valor_estimado)}  ·  previsão {prev}")
        print(f"     {o.item.objeto[:88]}{'…' if len(o.item.objeto) > 88 else ''}")
        print(f"     ▶ {o.prepare_action}")
        print()


def forecast_cmd(args) -> int:
    items = load_pca_fixture(PCA_FIXTURE)  # live PCA fetch = item futuro
    if args.ref:
        ref_year, ref_month = int(args.ref[:4]), int(args.ref[4:6])
    else:
        today = datetime.date.today()
        ref_year, ref_month = today.year, today.month
    opps = ForecastEngine().forecast(items, ref_year, ref_month, min_score=args.min_score)
    print_forecast(opps)
    return 0


def main(argv: list[str] | None = None) -> int:
    # O console do Windows usa cp1252 por omissão e não codifica ≥/█/✓. Forçar
    # UTF-8 no stdout torna o dashboard portável (Windows e Unix).
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

    parser = argparse.ArgumentParser(prog="licita", description="Heraclitus Gov Radar")
    parser.add_argument("command", nargs="?", default="radar", choices=["radar", "forecast"])
    parser.add_argument("--ref", metavar="YYYYMM",
                        help="[forecast] referência temporal (default: hoje)")
    parser.add_argument("--live", nargs=2, metavar=("DATA_INI", "DATA_FIM"),
                        help="Busca ao vivo no PNCP (YYYYMMDD YYYYMMDD)")
    parser.add_argument("--min-score", type=float, default=0.0)
    parser.add_argument("--ledger", metavar="PATH",
                        help="Grava eventos append-only (NDJSON) neste caminho")
    parser.add_argument("--heraclitus", nargs="?", const="127.0.0.1:7474", metavar="ADDR",
                        help="Ingesta no HeraclitusDB via gRPC (precisa grpcio + serviço)")
    parser.add_argument("--profile", metavar="PATH",
                        help="Perfil da empresa (JSON) → decisão Go/No-Go por edital")
    parser.add_argument("--artifacts", metavar="DIR",
                        help="Gera um dossiê .md (resumo + checklist) por oportunidade em DIR")
    args = parser.parse_args(argv)

    if args.command == "forecast":
        return forecast_cmd(args)

    if args.live:
        editais = pncp.PNCPClient().fetch_contratacoes(args.live[0], args.live[1])
    else:
        editais = pncp.load_fixture(FIXTURE)

    if args.heraclitus:
        store = HeraclitusEventStore(addr=args.heraclitus)
        store_desc = f"HeraclitusDB @ {args.heraclitus}"
    elif args.ledger:
        store = JsonlEventStore(args.ledger)
        store_desc = args.ledger
    else:
        store, store_desc = None, None

    radar = Radar(CompatibilityScorer())
    opportunities = [o for o in radar.analyze(editais) if o.score.value >= args.min_score]

    decisions = None
    if args.profile:
        profile = CompanyProfile.from_json_file(args.profile)
        engine = ViabilityEngine()
        decisions = {o.edital.bid_id: engine.evaluate(o.edital, profile) for o in opportunities}

    print_dashboard(opportunities, decisions)

    if args.artifacts:
        out_dir = Path(args.artifacts)
        out_dir.mkdir(parents=True, exist_ok=True)
        profile = CompanyProfile.from_json_file(args.profile) if args.profile else None
        for opp in opportunities:
            md = generate_dossier(opp.edital, profile=profile)
            (out_dir / f"{safe_filename(opp.edital.bid_id)}.md").write_text(md, encoding="utf-8")
        print(f"  {len(opportunities)} dossiê(s) .md gerado(s) em {out_dir}")

    if store is not None:
        try:
            for opp in opportunities:
                store.append(opp.to_event())
            print(f"  {len(opportunities)} evento(s) BidAnalyzed gravado(s) em {store_desc}")
        except ImportError:
            print(
                "  ⚠ Ingestão no HeraclitusDB indisponível: falta o SDK.\n"
                "    Instala:  venv/Scripts/pip install grpcio && "
                "pip install -e D:/DEV/HeraclitusDB/sdk/python",
                file=sys.stderr,
            )
            return 2
        except Exception as e:  # conexão recusada, serviço em baixo, etc.
            print(
                f"  ⚠ Ingestão no HeraclitusDB falhou ({type(e).__name__}: {e}).\n"
                f"    Confirma que o serviço responde em {store_desc}.",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
