"""Testes de utilizadores + participações (event-sourced) e do mailer."""

import tempfile
import unittest
from pathlib import Path

from licita.mailer import build_participation_email, send_email
from licita.participation import ConflictError, ParticipationStore


def _store(tmp: str) -> ParticipationStore:
    return ParticipationStore(Path(tmp) / "part.ndjson")


class TestParticipationStore(unittest.TestCase):
    def test_register_is_idempotent_by_email(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = _store(tmp)
            a = s.register_user("Ana", "ana@x.com")
            b = s.register_user("Ana", "ANA@X.COM ")
            self.assertEqual(a.user_id, b.user_id)

    def test_register_rejects_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = _store(tmp)
            with self.assertRaises(ValueError):
                s.register_user("", "ana@x.com")
            with self.assertRaises(ValueError):
                s.register_user("Ana", "sem-arroba")

    def test_claim_is_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = _store(tmp)
            ana = s.register_user("Ana", "ana@x.com")
            beto = s.register_user("Beto", "beto@x.com")
            s.claim("BID-1/2026", ana.user_id, {"objeto": "x"})
            with self.assertRaises(ConflictError):
                s.claim("BID-1/2026", beto.user_id)
            # idempotente para o próprio dono
            p = s.claim("BID-1/2026", ana.user_id)
            self.assertEqual(p.user_name, "Ana")

    def test_release_only_by_owner_then_reclaimable(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = _store(tmp)
            ana = s.register_user("Ana", "ana@x.com")
            beto = s.register_user("Beto", "beto@x.com")
            s.claim("B", ana.user_id)
            with self.assertRaises(ConflictError):
                s.release("B", beto.user_id)
            self.assertTrue(s.release("B", ana.user_id))
            s.claim("B", beto.user_id)  # agora pode
            self.assertEqual(s.claims["B"].user_name, "Beto")

    def test_state_survives_restart_via_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "part.ndjson"
            s1 = ParticipationStore(path)
            ana = s1.register_user("Ana", "ana@x.com")
            s1.claim("B1", ana.user_id)
            s1.claim("B2", ana.user_id)
            s1.release("B2", ana.user_id)
            s2 = ParticipationStore(path)  # replay do log
            self.assertIn("B1", s2.claims)
            self.assertNotIn("B2", s2.claims)
            self.assertIn(ana.user_id, s2.users)


class TestMailer(unittest.TestCase):
    def test_email_body_has_all_info(self):
        ed = {"bid_id": "X/26", "orgao": "Org", "objeto": "auditoria", "esfera": "federal",
              "uf": "DF", "valor_estimado": 1234567.89, "url": "https://pncp.gov.br/x",
              "score": {"value": 89.0, "recommendation": "participar", "matched": ["auditoria"]}}
        subj, body = build_participation_email("Ana", ed)
        for must in ("X/26", "Org", "auditoria", "Federal", "DF", "1.234.567,89",
                     "https://pncp.gov.br/x", "89.0", "PARTICIPAR"):
            self.assertIn(must, body)
        self.assertIn("Participação", subj)

    def test_send_without_smtp_goes_to_outbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = send_email("a@b.com", "Assunto", "Corpo", outbox_dir=tmp)
            self.assertEqual(st, "outbox")
            files = list(Path(tmp).glob("*.txt"))
            self.assertEqual(len(files), 1)
            self.assertIn("Corpo", files[0].read_text(encoding="utf-8"))


class TestEsferaParsing(unittest.TestCase):
    def test_esfera_from_orgao_entidade(self):
        from licita.pncp import parse_item
        for sid, nome in (("F", "federal"), ("E", "estadual"), ("M", "municipal")):
            e = parse_item({"numeroControlePNCP": "1", "objetoCompra": "x",
                            "orgaoEntidade": {"razaoSocial": "O", "esferaId": sid}})
            self.assertEqual(e.esfera, nome)
        e = parse_item({"numeroControlePNCP": "1", "objetoCompra": "x"})
        self.assertIsNone(e.esfera)

    def test_data_publicacao_captured(self):
        from licita.pncp import parse_item
        e = parse_item({"numeroControlePNCP": "1", "objetoCompra": "x",
                        "dataPublicacaoPncp": "2026-07-10T00:00:00"})
        self.assertEqual(e.data_publicacao, "2026-07-10T00:00:00")


if __name__ == "__main__":
    unittest.main()
