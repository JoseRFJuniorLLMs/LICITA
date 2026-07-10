"""Utilizadores e participações — event-sourced, append-only (a tese do projeto).

Cada ação é um EVENTO imutável num ledger NDJSON (`UserRegistered`,
`ParticipationClaimed`, `ParticipationReleased`); o estado atual é o replay do
log. Zero dependências externas; thread-safe.

Regra de negócio (pedido do produto): **uma licitação só pode ser estudada por
um utilizador de cada vez** — o claim é exclusivo; um segundo utilizador recebe
conflito até o primeiro libertar.
"""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _slug(text: str) -> str:
    """user_id determinístico a partir do email (estável entre sessões)."""
    norm = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", norm).strip("-") or "user"


@dataclass
class User:
    user_id: str
    name: str
    email: str

    def to_dict(self) -> dict[str, Any]:
        return {"user_id": self.user_id, "name": self.name, "email": self.email}


@dataclass
class Participation:
    bid_id: str
    user_id: str
    user_name: str
    claimed_at: float
    edital: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bid_id": self.bid_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "claimed_at": self.claimed_at,
        }


class ConflictError(Exception):
    """A licitação já está a ser estudada por outro utilizador."""


class ParticipationStore:
    """Ledger NDJSON de eventos + estado em memória (replay no arranque)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.users: dict[str, User] = {}
        self.claims: dict[str, Participation] = {}
        self._replay()

    # ── log ────────────────────────────────────────────────────────────────
    def _replay(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                self._apply(json.loads(line))
            except (json.JSONDecodeError, KeyError):
                continue  # linha corrompida não derruba o boot; o resto vale

    def _append(self, event: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _apply(self, ev: dict[str, Any]) -> None:
        kind = ev.get("kind")
        if kind == "UserRegistered":
            u = User(ev["user_id"], ev["name"], ev["email"])
            self.users[u.user_id] = u
        elif kind == "ParticipationClaimed":
            self.claims[ev["bid_id"]] = Participation(
                bid_id=ev["bid_id"],
                user_id=ev["user_id"],
                user_name=ev.get("user_name", ev["user_id"]),
                claimed_at=ev.get("ts", 0.0),
                edital=ev.get("edital", {}),
            )
        elif kind == "ParticipationReleased":
            self.claims.pop(ev["bid_id"], None)

    # ── API ────────────────────────────────────────────────────────────────
    def register_user(self, name: str, email: str) -> User:
        """Regista (ou devolve) o utilizador. Idempotente por email."""
        name, email = name.strip(), email.strip().lower()
        if not name or "@" not in email:
            raise ValueError("nome e email válidos são obrigatórios")
        user_id = _slug(email)
        with self._lock:
            existing = self.users.get(user_id)
            if existing and existing.name == name:
                return existing
            ev = {
                "kind": "UserRegistered", "user_id": user_id,
                "name": name, "email": email, "ts": time.time(),
            }
            self._append(ev)
            self._apply(ev)
            return self.users[user_id]

    def claim(self, bid_id: str, user_id: str, edital: dict[str, Any] | None = None) -> Participation:
        """Reclama a licitação para o utilizador. Exclusivo: 2.º utilizador → ConflictError."""
        with self._lock:
            user = self.users.get(user_id)
            if user is None:
                raise ValueError(f"utilizador desconhecido: {user_id}")
            cur = self.claims.get(bid_id)
            if cur is not None:
                if cur.user_id == user_id:
                    return cur  # idempotente para o próprio
                raise ConflictError(f"já em estudo por {cur.user_name}")
            ev = {
                "kind": "ParticipationClaimed", "bid_id": bid_id,
                "user_id": user_id, "user_name": user.name,
                "edital": edital or {}, "ts": time.time(),
            }
            self._append(ev)
            self._apply(ev)
            return self.claims[bid_id]

    def release(self, bid_id: str, user_id: str) -> bool:
        """Liberta a licitação (só o dono pode). True se libertou."""
        with self._lock:
            cur = self.claims.get(bid_id)
            if cur is None:
                return False
            if cur.user_id != user_id:
                raise ConflictError(f"pertence a {cur.user_name}")
            ev = {"kind": "ParticipationReleased", "bid_id": bid_id, "user_id": user_id, "ts": time.time()}
            self._append(ev)
            self._apply(ev)
            return True

    def all_claims(self) -> list[Participation]:
        with self._lock:
            return sorted(self.claims.values(), key=lambda p: -p.claimed_at)

    def get_user(self, user_id: str) -> User | None:
        return self.users.get(user_id)
