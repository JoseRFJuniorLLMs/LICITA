"""Testes do gerador de artefatos (resumo executivo + checklist)."""

import unittest

from licita.artifacts import (
    generate_dossier,
    habilitation_checklist,
    safe_filename,
)
from licita.decision import CompanyProfile
from licita.models import Edital


def edital(objeto: str) -> Edital:
    return Edital(
        bid_id="00394-1-000123/2026",
        orgao="Ministério da Saúde",
        objeto=objeto,
        valor_estimado=14200000.0,
        modalidade="Pregão Eletrônico",
        uf="DF",
    )


DEMANDING = edital(
    "Solução de auditoria e logs imutáveis. Exige capital social mínimo de "
    "R$ 3.000.000,00. Atestado de volumetria de 50 TB/dia. Certificação ISO 27001."
)


class ChecklistTest(unittest.TestCase):
    def test_standard_items_always_present(self):
        items = habilitation_checklist(edital("compra simples"))
        cats = {i.category for i in items}
        self.assertTrue({"juridica", "fiscal", "trabalhista", "economica"} <= cats)
        self.assertTrue(all(i.source == "padrao" for i in items))

    def test_edital_specific_items_detected(self):
        items = habilitation_checklist(DEMANDING)
        edital_items = [i for i in items if i.source == "edital"]
        joined = " | ".join(i.item for i in edital_items)
        self.assertIn("capital social", joined.lower())
        self.assertIn("50 TB/dia", joined)
        self.assertIn("ISO 27001", joined)
        # a qualificação técnica passa a existir por causa dos atestados/cert.
        self.assertTrue(any(i.category == "tecnica" for i in items))

    def test_safe_filename(self):
        self.assertEqual(safe_filename("00394-1-000123/2026"), "00394-1-000123_2026")
        self.assertEqual(safe_filename("///"), "edital")


class DossierTest(unittest.TestCase):
    def test_dossier_has_summary_and_checklist(self):
        md = generate_dossier(DEMANDING)
        self.assertIn("# Resumo Executivo", md)
        self.assertIn("Compatibilidade técnica", md)
        self.assertIn("Checklist de Habilitação", md)
        self.assertIn("14.200.000,00", md)  # valor formatado
        self.assertIn("- [ ]", md)  # itens do checklist

    def test_dossier_with_profile_includes_go_nogo(self):
        weak = CompanyProfile(capital_social=1_000_000, volumetria_max_tb_dia=10)
        md = generate_dossier(DEMANDING, profile=weak)
        self.assertIn("Go/No-Go", md)
        self.assertIn("IMPEDITIVO", md)  # bloqueios hard renderizados


if __name__ == "__main__":
    unittest.main()
