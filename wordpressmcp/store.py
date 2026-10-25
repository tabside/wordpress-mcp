"""SQLite storage: OAuth clients, pending logins, codes and tokens.

Codes and tokens are stored only as SHA-256 hashes. The WordPress Application
Passwords are not stored here; they come from the environment only.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any

from .crypto import hash_secret

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    client_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    data TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_requests (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    params TEXT NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_codes (
    code_hash TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    scopes TEXT NOT NULL,
    code_challenge TEXT NOT NULL,
    redirect_uri TEXT NOT NULL,
    redirect_uri_explicit INTEGER NOT NULL,
    resource TEXT,
    expires_at INTEGER NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    revoke_others INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tokens (
    token_hash TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    client_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    scopes TEXT NOT NULL,
    resource TEXT,
    family_id TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    last_used INTEGER,
    revoked INTEGER NOT NULL DEFAULT 0,
    rotated INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS tokens_user ON tokens(user_id);
CREATE INDEX IF NOT EXISTS tokens_family ON tokens(family_id);
"""


@dataclass
class AuthCodeRow:
    code_hash: str
    client_id: str
    user_id: str
    scopes: list[str]
    code_challenge: str
    redirect_uri: str
    redirect_uri_explicit: bool
    resource: str | None
    expires_at: int
    used: bool
    revoke_others: bool


@dataclass
class TokenRow:
    token_hash: str
    kind: str
    client_id: str
    user_id: str
    scopes: list[str]
    resource: str | None
    family_id: str
    expires_at: int
    created_at: int
    last_used: int | None
    revoked: bool
    rotated: bool


class Store:
    def __init__(self, path: str):
        if path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)
        if path != ":memory:":
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass

    # ------------------------------------------------------------------ helpers
    def _run(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def _all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    async def _a(self, fn, *args):
        return await asyncio.to_thread(fn, *args)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    async def ping(self) -> bool:
        return (await self._a(self._one, "SELECT 1")) is not None

    def cleanup_sync(self) -> None:
        now = int(time.time())
        self._run("DELETE FROM auth_requests WHERE expires_at < ?", (now,))
        self._run("DELETE FROM auth_codes WHERE expires_at < ?", (now - 3600,))
        # keep revoked/rotated refresh tokens a while for reuse detection
        self._run("DELETE FROM tokens WHERE expires_at < ?", (now - 86400,))

    async def cleanup(self) -> None:
        await self._a(self.cleanup_sync)

    # ------------------------------------------------------------------ clients
    async def get_client(self, client_id: str) -> tuple[str, dict[str, Any], int] | None:
        row = await self._a(self._one, "SELECT kind, data, updated_at FROM clients WHERE client_id = ?", (client_id,))
        if row is None:
            return None
        return row["kind"], json.loads(row["data"]), row["updated_at"]

    async def save_client(self, client_id: str, kind: str, data: dict[str, Any]) -> None:
        await self._a(
            self._run,
            "INSERT INTO clients(client_id, kind, data, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(client_id) DO UPDATE SET kind=excluded.kind, data=excluded.data, updated_at=excluded.updated_at",
            (client_id, kind, json.dumps(data), int(time.time())),
        )

    async def client_names(self) -> dict[str, str]:
        rows = await self._a(self._all, "SELECT client_id, data FROM clients")
        out = {}
        for row in rows:
            try:
                out[row["client_id"]] = json.loads(row["data"]).get("client_name") or ""
            except ValueError:
                out[row["client_id"]] = ""
        return out

    # ------------------------------------------------------------ auth requests
    async def save_auth_request(self, request_id: str, client_id: str, params: dict[str, Any], ttl: int) -> None:
        await self._a(
            self._run,
            "INSERT INTO auth_requests(id, client_id, params, expires_at) VALUES (?,?,?,?)",
            (request_id, client_id, json.dumps(params), int(time.time()) + ttl),
        )

    async def get_auth_request(self, request_id: str) -> tuple[str, dict[str, Any]] | None:
        row = await self._a(
            self._one, "SELECT client_id, params, expires_at FROM auth_requests WHERE id = ?", (request_id,)
        )
        if row is None or row["expires_at"] < int(time.time()):
            return None
        return row["client_id"], json.loads(row["params"])

    async def delete_auth_request(self, request_id: str) -> None:
        await self._a(self._run, "DELETE FROM auth_requests WHERE id = ?", (request_id,))

    # -------------------------------------------------------------------- codes
    async def save_auth_code(
        self,
        code: str,
        *,
        client_id: str,
        user_id: str,
        scopes: list[str],
        code_challenge: str,
        redirect_uri: str,
        redirect_uri_explicit: bool,
        resource: str | None,
        ttl: int,
        revoke_others: bool,
    ) -> None:
        await self._a(
            self._run,
            "INSERT INTO auth_codes(code_hash, client_id, user_id, scopes, code_challenge, redirect_uri, "
            "redirect_uri_explicit, resource, expires_at, revoke_others) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                hash_secret(code),
                client_id,
                user_id,
                json.dumps(scopes),
                code_challenge,
                redirect_uri,
                int(redirect_uri_explicit),
                resource,
                int(time.time()) + ttl,
                int(revoke_others),
            ),
        )

    async def get_auth_code(self, code: str) -> AuthCodeRow | None:
        row = await self._a(self._one, "SELECT * FROM auth_codes WHERE code_hash = ?", (hash_secret(code),))
        if row is None:
            return None
        return AuthCodeRow(
            code_hash=row["code_hash"],
            client_id=row["client_id"],
            user_id=row["user_id"],
            scopes=json.loads(row["scopes"]),
            code_challenge=row["code_challenge"],
            redirect_uri=row["redirect_uri"],
            redirect_uri_explicit=bool(row["redirect_uri_explicit"]),
            resource=row["resource"],
            expires_at=row["expires_at"],
            used=bool(row["used"]),
            revoke_others=bool(row["revoke_others"]),
        )

    async def consume_auth_code(self, code_hash: str) -> bool:
        cur = await self._a(
            self._run,
            "UPDATE auth_codes SET used = 1 WHERE code_hash = ? AND used = 0 AND expires_at >= ?",
            (code_hash, int(time.time())),
        )
        return cur.rowcount == 1

    # ------------------------------------------------------------------- tokens
    async def save_token(
        self,
        token: str,
        *,
        kind: str,
        client_id: str,
        user_id: str,
        scopes: list[str],
        resource: str | None,
        family_id: str,
        ttl: int,
    ) -> None:
        now = int(time.time())
        await self._a(
            self._run,
            "INSERT INTO tokens(token_hash, kind, client_id, user_id, scopes, resource, family_id, expires_at, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (hash_secret(token), kind, client_id, user_id, json.dumps(scopes), resource, family_id, now + ttl, now),
        )

    @staticmethod
    def _token_row(row: sqlite3.Row) -> TokenRow:
        return TokenRow(
            token_hash=row["token_hash"],
            kind=row["kind"],
            client_id=row["client_id"],
            user_id=row["user_id"],
            scopes=json.loads(row["scopes"]),
            resource=row["resource"],
            family_id=row["family_id"],
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            last_used=row["last_used"],
            revoked=bool(row["revoked"]),
            rotated=bool(row["rotated"]),
        )

    async def get_token(self, token: str, kind: str) -> TokenRow | None:
        row = await self._a(
            self._one, "SELECT * FROM tokens WHERE token_hash = ? AND kind = ?", (hash_secret(token), kind)
        )
        return self._token_row(row) if row else None

    async def touch_token(self, token_hash: str) -> None:
        await self._a(self._run, "UPDATE tokens SET last_used = ? WHERE token_hash = ?", (int(time.time()), token_hash))

    async def mark_rotated(self, token_hash: str) -> bool:
        cur = await self._a(
            self._run,
            "UPDATE tokens SET rotated = 1 WHERE token_hash = ? AND rotated = 0 AND revoked = 0 AND expires_at >= ?",
            (token_hash, int(time.time())),
        )
        return cur.rowcount == 1

    async def revoke_family(self, family_id: str) -> int:
        cur = await self._a(self._run, "UPDATE tokens SET revoked = 1 WHERE family_id = ? AND revoked = 0", (family_id,))
        return cur.rowcount

    async def revoke_user(self, user_id: str, *, except_family: str | None = None) -> int:
        if except_family:
            cur = await self._a(
                self._run,
                "UPDATE tokens SET revoked = 1 WHERE user_id = ? AND revoked = 0 AND family_id != ?",
                (user_id, except_family),
            )
        else:
            cur = await self._a(self._run, "UPDATE tokens SET revoked = 1 WHERE user_id = ? AND revoked = 0", (user_id,))
        return cur.rowcount

    async def connections(self, user_id: str | None = None) -> list[dict[str, Any]]:
        """Active token families (one per connected application), newest activity first."""
        now = int(time.time())
        sql = (
            "SELECT family_id, user_id, client_id, MIN(created_at) AS created, MAX(COALESCE(last_used, 0)) AS last_used, "
            "MAX(expires_at) AS expires FROM tokens WHERE revoked = 0 AND expires_at >= ?"
        )
        params: tuple = (now,)
        if user_id is not None:
            sql += " AND user_id = ?"
            params = (now, user_id)
        sql += " GROUP BY family_id ORDER BY last_used DESC"
        rows = await self._a(self._all, sql, params)
        return [dict(r) for r in rows]
