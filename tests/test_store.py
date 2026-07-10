"""Testes do HeraclitusEventStore — mapeamento evento→episódio + forwarding.

Usa um cliente FAKE (injetável), por isso NÃO precisa de grpcio nem de um
serviço HeraclitusDB a correr. O round-trip ao vivo é responsabilidade do SDK
oficial (`heraclitusdb.connect`) e fica fora do escopo desta suíte offline.
"""

import unittest
from pathlib import Path

from licita import pncp
from licita.radar import Radar
from licita.scoring import CompatibilityScorer
from licita.store import HeraclitusEventStore

FIXTURE = Path(__file__).resolve().parent.parent / "licita" / "fixtures" / "sample_pncp.json"


class FakeClient:
    """Imita heraclitusdb.Client.append; regista as chamadas."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._lsn = 0

    def append(self, kind, content, *, agent_id="", session_id="", attrs=None, **kw):
        self.calls.append(
            {"kind": kind, "content": content, "agent_id": agent_id, "attrs": attrs or {}}
        )
        self._lsn += 1
        return self._lsn


class HeraclitusStoreTest(unittest.TestCase):
    def top_opportunity(self):
        editais = pncp.load_fixture(FIXTURE)
        return Radar(CompatibilityScorer()).analyze(editais)[0]

    def test_maps_event_to_episode(self):
        store = HeraclitusEventStore(agent_id="licita-radar")
        opp = self.top_opportunity()
        ep = store.to_episode(opp.to_event())
        self.assertEqual(ep["kind"], "BidAnalyzed")
        self.assertEqual(ep["agent_id"], "licita-radar")
        # o objeto (não o órgão) vai no conteúdo do episódio
        self.assertIn("fábrica", ep["content"].lower())
        self.assertEqual(ep["attrs"]["orgao"], opp.edital.orgao)  # órgão vai em attrs
        self.assertEqual(ep["attrs"]["recommendation"], "participar")
        self.assertEqual(ep["attrs"]["bid_id"], opp.edital.bid_id)
        self.assertEqual(ep["attrs"]["uf"], "DF")
        # attrs são todos str (contrato map<string,string> do proto).
        self.assertTrue(all(isinstance(v, str) for v in ep["attrs"].values()))

    def test_append_forwards_to_client_and_returns_lsn(self):
        fake = FakeClient()
        store = HeraclitusEventStore(client=fake)
        opp = self.top_opportunity()
        lsn = store.append(opp.to_event())
        self.assertEqual(lsn, "1")
        self.assertEqual(len(fake.calls), 1)
        call = fake.calls[0]
        self.assertEqual(call["kind"], "BidAnalyzed")
        self.assertEqual(call["agent_id"], "licita-radar")
        self.assertEqual(call["attrs"]["orgao"], opp.edital.orgao)

    def test_radar_run_persists_through_heraclitus_store(self):
        fake = FakeClient()
        radar = Radar(CompatibilityScorer(), HeraclitusEventStore(client=fake))
        editais = pncp.load_fixture(FIXTURE)
        opps = radar.run(editais, min_score=40.0)
        self.assertEqual(len(fake.calls), len(opps))
        self.assertTrue(all(c["kind"] == "BidAnalyzed" for c in fake.calls))


if __name__ == "__main__":
    unittest.main()
