"""Testes do forecasting de PCA (parsing + janelas + engine)."""

import unittest
from pathlib import Path

from licita.pca import (
    ForecastEngine,
    ForecastWindow,
    classify_window,
    load_pca_fixture,
    months_ahead,
    parse_pca_item,
)

FIXTURE = Path(__file__).resolve().parent.parent / "licita" / "fixtures" / "sample_pca.json"


class PcaParsingTest(unittest.TestCase):
    def test_parses_pca_items(self):
        items = load_pca_fixture(FIXTURE)
        self.assertEqual(len(items), 3)
        just = next(i for i in items if "Justiça" in i.orgao)
        self.assertEqual(just.valor_estimado, 42000000.0)
        self.assertEqual(just.ano_previsto, 2027)
        self.assertEqual(just.mes_previsto, 11)
        self.assertEqual(just.uf, "DF")

    def test_data_desejada_fills_year_month(self):
        items = load_pca_fixture(FIXTURE)
        dataprev = next(i for i in items if "DATAPREV" in i.orgao)
        # veio de dataDesejada "2027-03-15"
        self.assertEqual(dataprev.ano_previsto, 2027)
        self.assertEqual(dataprev.mes_previsto, 3)

    def test_parse_is_defensive(self):
        i = parse_pca_item({})
        self.assertEqual(i.pca_id, "")
        self.assertIsNone(i.valor_estimado)


class WindowTest(unittest.TestCase):
    def test_months_ahead(self):
        items = load_pca_fixture(FIXTURE)
        just = next(i for i in items if "Justiça" in i.orgao)  # 2027-11
        self.assertEqual(months_ahead(just, 2027, 7), 4)  # jul→nov
        self.assertEqual(months_ahead(just, 2027, 11), 0)
        self.assertEqual(months_ahead(just, 2028, 1), 0)  # passado ⇒ clamp 0

    def test_classify_window(self):
        self.assertEqual(classify_window(1), ForecastWindow.IMINENTE)
        self.assertEqual(classify_window(4), ForecastWindow.PROXIMO)
        self.assertEqual(classify_window(10), ForecastWindow.FUTURO)
        self.assertEqual(classify_window(None), ForecastWindow.SEM_DATA)


class ForecastTest(unittest.TestCase):
    def test_ranks_and_classifies(self):
        items = load_pca_fixture(FIXTURE)
        fc = ForecastEngine().forecast(items, ref_year=2027, ref_month=7)
        # topo é o de auditoria/imutável (Justiça), 4 meses à frente (PROXIMO).
        self.assertIn("Justiça", fc[0].item.orgao)
        self.assertEqual(fc[0].months_ahead, 4)
        self.assertEqual(fc[0].window, ForecastWindow.PROXIMO)
        # mobiliário fica no fim com score 0.
        self.assertEqual(fc[-1].score.value, 0.0)
        # ordenado por score desc.
        scores = [o.score.value for o in fc]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_min_score_filters(self):
        items = load_pca_fixture(FIXTURE)
        fc = ForecastEngine().forecast(items, 2027, 7, min_score=40.0)
        self.assertTrue(all(o.score.value >= 40 for o in fc))
        self.assertTrue(all("mobiliário" not in o.item.objeto.lower() for o in fc))

    def test_serializable(self):
        import json

        fc = ForecastEngine().forecast(load_pca_fixture(FIXTURE), 2027, 7)
        json.dumps([o.to_dict() for o in fc])


if __name__ == "__main__":
    unittest.main()
