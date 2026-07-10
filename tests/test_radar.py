"""Testes do Radar + parsing do PNCP + store de eventos (end-to-end offline)."""

import unittest
from pathlib import Path

from licita import pncp
from licita.models import Recommendation
from licita.radar import Radar
from licita.scoring import CompatibilityScorer
from licita.store import InMemoryEventStore

FIXTURE = Path(__file__).resolve().parent.parent / "licita" / "fixtures" / "sample_pncp.json"


class PncpParsingTest(unittest.TestCase):
    def test_parses_pncp_fields(self):
        editais = pncp.load_fixture(FIXTURE)
        self.assertEqual(len(editais), 3)
        saude = next(e for e in editais if "Saúde" in e.orgao)
        self.assertEqual(saude.uf, "DF")
        self.assertEqual(saude.valor_estimado, 14200000.0)
        self.assertIn("cloud", saude.searchable_text().lower())
        # o item (firewall/ICP) entrou no texto pesquisável
        self.assertIn("firewall", saude.searchable_text().lower())
        self.assertEqual(saude.raw["numeroControlePNCP"], saude.bid_id)

    def test_parse_item_is_defensive_on_missing_fields(self):
        e = pncp.parse_item({})  # nada
        self.assertEqual(e.bid_id, "")
        self.assertIsNone(e.valor_estimado)


class RadarTest(unittest.TestCase):
    def setUp(self) -> None:
        self.editais = pncp.load_fixture(FIXTURE)
        self.radar = Radar(CompatibilityScorer(), InMemoryEventStore())

    def test_ranks_by_compatibility(self):
        opps = self.radar.analyze(self.editais)
        # Ordenado desc; o edital de auditoria/logs imutáveis é o topo.
        scores = [o.score.value for o in opps]
        self.assertEqual(scores, sorted(scores, reverse=True))
        # O de limpeza fica no fim com score 0 e recomendação IGNORAR.
        self.assertEqual(opps[-1].score.value, 0.0)
        self.assertEqual(opps[-1].score.recommendation, Recommendation.IGNORAR)

    def test_run_persists_one_event_per_opportunity(self):
        store = InMemoryEventStore()
        radar = Radar(CompatibilityScorer(), store)
        opps = radar.run(self.editais, min_score=40.0)
        # Só os compatíveis (≥40) são gravados; limpeza (0) fica de fora.
        self.assertTrue(all(o.score.value >= 40 for o in opps))
        self.assertEqual(len(store), len(opps))
        ev = store.events[0]
        self.assertEqual(ev["kind"], "BidAnalyzed")
        self.assertIn("score", ev)

    def test_event_payload_is_serializable(self):
        import json

        opp = self.radar.analyze(self.editais)[0]
        json.dumps(opp.to_event())  # não levanta


if __name__ == "__main__":
    unittest.main()
