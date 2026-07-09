"""CLI do Radar: `python -m licita [radar]`.

Por omissão corre offline sobre a fixture do PNCP (sem rede) e imprime um
dashboard de oportunidades ordenado por compatibilidade — a versão terminal do
painel de spec-0001. Com `--live D1 D2` (YYYYMMDD) busca o PNCP ao vivo.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import pncp
from .models import ScoredOpportunity
from .radar import Radar
from .scoring import CompatibilityScorer
from .store import HeraclitusEventStore, JsonlEventStore

FIXTURE = Path(__file__).parent / "fixtures" / "sample_pncp.json"


def _fmt_valor(v: float | None) -> str:
    if v is None:
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _bar(value: float, width: int = 20) -> str:
    filled = round(value / 100 * width)
    return "█" * filled + "░" * (width - filled)


def print_dashboard(opportunities: list[ScoredOpportunity]) -> None:
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
        print()


def main(argv: list[str] | None = None) -> int:
    # O console do Windows usa cp1252 por omissão e não codifica ≥/█/✓. Forçar
    # UTF-8 no stdout torna o dashboard portável (Windows e Unix).
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

    parser = argparse.ArgumentParser(prog="licita", description="Heraclitus Gov Radar")
    parser.add_argument("command", nargs="?", default="radar", choices=["radar"])
    parser.add_argument("--live", nargs=2, metavar=("DATA_INI", "DATA_FIM"),
                        help="Busca ao vivo no PNCP (YYYYMMDD YYYYMMDD)")
    parser.add_argument("--min-score", type=float, default=0.0)
    parser.add_argument("--ledger", metavar="PATH",
                        help="Grava eventos append-only (NDJSON) neste caminho")
    parser.add_argument("--heraclitus", nargs="?", const="127.0.0.1:7474", metavar="ADDR",
                        help="Ingesta no HeraclitusDB via gRPC (precisa grpcio + serviço)")
    args = parser.parse_args(argv)

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
    print_dashboard(opportunities)

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
