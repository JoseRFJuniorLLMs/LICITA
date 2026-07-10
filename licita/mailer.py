"""Envio de email ao participar numa licitação.

SMTP real quando configurado por variáveis de ambiente; sem configuração, o
email vai para um OUTBOX em disco (`data/outbox/*.txt`) — nada se perde e o
sistema diz a verdade sobre o que fez (`sent` vs `outbox`).

Config (env):
  LICITA_SMTP_HOST  — ex.: smtp.gmail.com (sem isto → outbox)
  LICITA_SMTP_PORT  — default 587 (STARTTLS)
  LICITA_SMTP_USER / LICITA_SMTP_PASS
  LICITA_SMTP_FROM  — default = LICITA_SMTP_USER
"""

from __future__ import annotations

import os
import re
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any


def _fmt_brl(v: Any) -> str:
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"


def build_participation_email(user_name: str, edital: dict[str, Any]) -> tuple[str, str]:
    """(assunto, corpo) com TODAS as informações da licitação."""
    score = edital.get("score") or {}
    lines = [
        f"Olá {user_name},",
        "",
        "Você marcou PARTICIPAR nesta licitação no Heraclitus Gov Radar.",
        "Segue o dossiê completo:",
        "",
        f"Órgão:            {edital.get('orgao') or '—'}",
        f"Objeto:           {edital.get('objeto') or '—'}",
        f"Nº controle PNCP: {edital.get('bid_id') or '—'}",
        f"Esfera:           {(edital.get('esfera') or '—').capitalize()}",
        f"UF:               {edital.get('uf') or '—'}",
        f"Modalidade:       {edital.get('modalidade') or '—'}",
        f"Valor estimado:   {_fmt_brl(edital.get('valor_estimado'))}",
        f"Publicação:       {edital.get('data_publicacao') or '—'}",
        f"Abertura:         {edital.get('data_abertura') or '—'}",
        f"Link do edital:   {edital.get('url') or '—'}",
        "",
        f"Score de compatibilidade: {score.get('value', '—')}%"
        f"  →  {(score.get('recommendation') or '—').upper()}",
        f"Categorias casadas: {', '.join(score.get('matched') or []) or 'nenhuma'}",
        "",
        "Próximos passos sugeridos:",
        "  1. Ler o edital completo no link acima e anotar os prazos.",
        "  2. Verificar requisitos de habilitação (capital social, atestados).",
        "  3. Preparar a documentação e a proposta.",
        "",
        "— Heraclitus Gov Radar",
    ]
    assunto = f"[Gov Radar] Participação: {(edital.get('objeto') or edital.get('bid_id') or '')[:80]}"
    return assunto, "\n".join(lines)


def send_email(to_addr: str, subject: str, body: str, outbox_dir: str | Path = "data/outbox") -> str:
    """Envia por SMTP se configurado; senão grava no outbox. Devolve 'sent'|'outbox'."""
    host = os.environ.get("LICITA_SMTP_HOST", "").strip()
    if host:
        msg = EmailMessage()
        msg["From"] = os.environ.get("LICITA_SMTP_FROM") or os.environ.get("LICITA_SMTP_USER", "radar@localhost")
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content(body)
        port = int(os.environ.get("LICITA_SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            user = os.environ.get("LICITA_SMTP_USER", "")
            if user:
                s.login(user, os.environ.get("LICITA_SMTP_PASS", ""))
            s.send_message(msg)
        return "sent"
    # Outbox: um ficheiro por email, auditável.
    out = Path(outbox_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe_to = re.sub(r"[^a-z0-9@.]+", "_", to_addr.lower())
    fname = out / f"{int(time.time() * 1000)}-{safe_to}.txt"
    fname.write_text(f"To: {to_addr}\nSubject: {subject}\n\n{body}", encoding="utf-8")
    return "outbox"
