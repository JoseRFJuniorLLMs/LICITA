"""Testes da API REST (chamando os handlers diretamente, sem httpx/servidor)."""

import unittest

from licita.api import (
    DecideIn,
    EditalIn,
    ProfileIn,
    app,
    decide_endpoint,
    dossier_endpoint,
    forecast_demo,
    health,
    radar_demo,
    score_endpoint,
)

HARD_OBJ = (
    "Solução de auditoria e logs imutáveis. Exige capital social mínimo de "
    "R$ 3.000.000,00. Atestado de volumetria de 50 TB/dia."
)


class ApiTest(unittest.TestCase):
    def test_health(self):
        self.assertEqual(health()["status"], "ok")

    def test_score_endpoint(self):
        r = score_endpoint(EditalIn(objeto="auditoria e logs imutáveis, banco de dados, LGPD"))
        self.assertGreaterEqual(r["value"], 40.0)
        self.assertIn("recommendation", r)

    def test_decide_endpoint_blocks_underqualified(self):
        body = DecideIn(edital=EditalIn(objeto=HARD_OBJ), profile=ProfileIn(capital_social=1_000_000))
        r = decide_endpoint(body)
        self.assertEqual(r["decision"], "nao_participar")
        self.assertTrue(any(b["hard"] for b in r["blockers"]))

    def test_decide_without_profile_uses_default(self):
        r = decide_endpoint(DecideIn(edital=EditalIn(objeto="compra simples")))
        self.assertIn("decision", r)  # não crasha sem perfil

    def test_dossier_endpoint_returns_markdown(self):
        md = dossier_endpoint(DecideIn(edital=EditalIn(objeto=HARD_OBJ, valor_estimado=14_200_000)))
        self.assertIn("# Resumo Executivo", md)
        self.assertIn("Checklist de Habilitação", md)

    def test_radar_demo(self):
        rows = radar_demo()
        self.assertEqual(len(rows), 3)
        # ranqueado desc
        self.assertGreaterEqual(rows[0]["score"]["value"], rows[-1]["score"]["value"])

    def test_forecast_demo(self):
        rows = forecast_demo(ref_year=2027, ref_month=7)
        self.assertTrue(rows)
        self.assertIn("months_ahead", rows[0])
        self.assertGreaterEqual(rows[0]["score"]["value"], rows[-1]["score"]["value"])

    def test_all_routes_registered(self):
        paths = {r.path for r in app.routes}
        for p in ("/health", "/score", "/decide", "/dossier", "/radar/demo", "/forecast/demo"):
            self.assertIn(p, paths)


if __name__ == "__main__":
    unittest.main()
