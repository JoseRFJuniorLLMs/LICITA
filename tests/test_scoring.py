"""Testes do scorer de compatibilidade (determinístico e explicável)."""

import unittest

from licita.models import Edital, Recommendation
from licita.scoring import CompatibilityScorer, DEFAULT_TAXONOMY


def edital(objeto: str, texto: str = "") -> Edital:
    return Edital(bid_id="x", orgao="Órgão", objeto=objeto, texto=texto)


class ScoringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scorer = CompatibilityScorer()

    def test_high_compatibility_hits_core_categories(self):
        e = edital(
            "Solução de auditoria com registro imutável de logs, event sourcing, "
            "banco de dados e conformidade LGPD."
        )
        s = self.scorer.score(e)
        self.assertGreaterEqual(s.value, 70.0)
        self.assertEqual(s.recommendation, Recommendation.PARTICIPAR)
        for cat in ("logs_imutaveis", "auditoria", "banco_de_dados", "seguranca_compliance"):
            self.assertIn(cat, s.matched_categories, cat)

    def test_irrelevant_bid_scores_zero(self):
        s = self.scorer.score(edital("Aquisição de material de limpeza e higiene."))
        self.assertEqual(s.value, 0.0)
        self.assertEqual(s.recommendation, Recommendation.IGNORAR)

    def test_accents_and_case_are_normalized(self):
        # "AUDITÓRIA" (acento/caixa) tem de casar 'auditoria'.
        s = self.scorer.score(edital("Serviço de AUDITÓRIA e RASTREABILIDADE."))
        self.assertIn("auditoria", s.matched_categories)

    def test_word_boundaries_avoid_false_positives(self):
        # 'ia' (IA) NÃO pode casar dentro de 'polícia'/'diária'.
        s = self.scorer.score(edital("Contratação de vigilância para a polícia; diária de campo."))
        self.assertNotIn("inteligencia_artificial", s.matched_categories)

    def test_score_is_weighted_average_of_present_categories(self):
        # Só 'banco_de_dados' (peso 0.95) presente ⇒ 0.95 / soma_pesos * 100.
        s = self.scorer.score(edital("Aquisição de banco de dados relacional."))
        total_weight = sum(c.weight for c in DEFAULT_TAXONOMY)
        expected = 0.95 / total_weight * 100.0
        self.assertAlmostEqual(s.value, expected, places=4)
        self.assertEqual(s.matched_categories, ["banco_de_dados"])

    def test_deterministic(self):
        e = edital("auditoria e logs imutáveis")
        self.assertEqual(self.scorer.score(e).value, self.scorer.score(e).value)

    def test_thresholds_validated(self):
        with self.assertRaises(ValueError):
            CompatibilityScorer(participar_min=10, avaliar_min=50)  # avaliar > participar


if __name__ == "__main__":
    unittest.main()
