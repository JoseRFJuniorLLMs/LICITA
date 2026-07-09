"""Testes do motor Go/No-Go (extração de requisitos + viabilidade)."""

import unittest

from licita.decision import (
    CompanyProfile,
    Decision,
    ViabilityEngine,
    extract_requirements,
    parse_brl,
)
from licita.models import Edital


def edital(objeto: str) -> Edital:
    return Edital(bid_id="E-1", orgao="SERPRO", objeto=objeto)


# Edital "difícil": compatível tecnicamente, mas com barreiras de habilitação.
HARD = edital(
    "Solução de observabilidade e auditoria de logs imutáveis. "
    "Exige capital social mínimo de R$ 3.000.000,00. "
    "Atestado de capacidade técnica comprovando volumetria de 50 TB/dia sustentada. "
    "Prazo de entrega do plano de trabalho de apenas 5 dias úteis."
)


class ParsingTest(unittest.TestCase):
    def test_parse_brl(self):
        self.assertEqual(parse_brl("3.000.000,00"), 3000000.0)
        self.assertEqual(parse_brl("1.500,50"), 1500.5)

    def test_extracts_all_requirements(self):
        reqs = {r.code: r for r in extract_requirements(HARD)}
        self.assertEqual(reqs["capital_social"].required, 3000000.0)
        self.assertEqual(reqs["volumetria"].required, 50.0)
        self.assertEqual(reqs["volumetria"].unit, "TB/dia")
        self.assertEqual(reqs["prazo"].required, 5.0)
        self.assertFalse(reqs["prazo"].hard)  # prazo é SOFT
        self.assertTrue(reqs["capital_social"].hard)

    def test_volumetria_unit_normalized_to_tb(self):
        reqs = {r.code: r for r in extract_requirements(edital("volumetria de 500 GB/dia"))}
        self.assertAlmostEqual(reqs["volumetria"].required, 0.5)  # 500 GB = 0.5 TB


class ViabilityTest(unittest.TestCase):
    def setUp(self):
        self.engine = ViabilityEngine()

    def test_hard_blockers_force_no_go_and_zero_probability(self):
        weak = CompanyProfile(capital_social=1_500_000, volumetria_max_tb_dia=20)
        r = self.engine.evaluate(HARD, weak)
        self.assertEqual(r.decision, Decision.NAO_PARTICIPAR)
        self.assertEqual(r.probability, 0.0)
        codes = {b.code for b in r.blockers if b.hard}
        self.assertIn("capital_social", codes)
        self.assertIn("volumetria", codes)

    def test_qualified_company_gets_go(self):
        strong = CompanyProfile(
            capital_social=5_000_000, volumetria_max_tb_dia=80, prazo_confortavel_dias=3
        )
        r = self.engine.evaluate(HARD, strong)
        self.assertEqual(r.decision, Decision.PARTICIPAR)
        self.assertGreater(r.probability, 0.5)
        self.assertFalse([b for b in r.blockers if b.hard])

    def test_soft_prazo_penalizes_but_does_not_block(self):
        # Cumpre capital e volumetria, mas o prazo (5d) é menor que o confortável (10d).
        ok_but_tight = CompanyProfile(
            capital_social=5_000_000, volumetria_max_tb_dia=80, prazo_confortavel_dias=10
        )
        r = self.engine.evaluate(HARD, ok_but_tight)
        self.assertFalse([b for b in r.blockers if b.hard], "sem bloqueio hard")
        self.assertTrue([b for b in r.blockers if not b.hard], "prazo é aviso soft")
        # penalidade 0.8 aplicada, mas ainda viável.
        self.assertGreater(r.probability, 0.0)
        self.assertLess(r.probability, r.compat / 100.0)

    def test_certification_missing_is_hard_block(self):
        e = edital("auditoria com logs imutaveis. Exige certificacao ISO 27001.")
        r = self.engine.evaluate(e, CompanyProfile(certificacoes=frozenset()))
        self.assertEqual(r.decision, Decision.NAO_PARTICIPAR)
        r2 = self.engine.evaluate(e, CompanyProfile(certificacoes=frozenset({"ISO 27001"})))
        self.assertNotEqual(r2.decision, Decision.NAO_PARTICIPAR)

    def test_report_serializable(self):
        import json

        r = self.engine.evaluate(HARD, CompanyProfile())
        json.dumps(r.to_dict())


class ProfileLoaderTest(unittest.TestCase):
    FIXTURES = None  # set in setUp

    def setUp(self):
        from pathlib import Path

        self.FIXTURES = Path(__file__).resolve().parent.parent / "licita" / "fixtures"

    def test_from_dict_and_json_file(self):
        p = CompanyProfile.from_dict({"capital_social": 2_000_000, "certificacoes": ["ISO 27001"]})
        self.assertEqual(p.capital_social, 2_000_000.0)
        self.assertIn("ISO 27001", p.certificacoes)
        p2 = CompanyProfile.from_json_file(self.FIXTURES / "sample_profile.json")
        self.assertEqual(p2.volumetria_max_tb_dia, 30.0)
        self.assertEqual(p2.prazo_confortavel_dias, 10)

    def test_radar_fixture_editais_get_go_nogo(self):
        from licita import pncp

        editais = pncp.load_fixture(self.FIXTURES / "sample_pncp.json")
        profile = CompanyProfile.from_json_file(self.FIXTURES / "sample_profile.json")
        engine = ViabilityEngine()
        reports = {e.bid_id: engine.evaluate(e, profile) for e in editais}
        saude = next(e for e in editais if "Saúde" in e.orgao)
        rep = reports[saude.bid_id]
        # capital exigido 3M > 2M do perfil, e 50 TB/dia > 30 → dois bloqueios HARD.
        self.assertEqual(rep.decision, Decision.NAO_PARTICIPAR)
        hard = {b.code for b in rep.blockers if b.hard}
        self.assertIn("capital_social", hard)
        self.assertIn("volumetria", hard)


if __name__ == "__main__":
    unittest.main()
