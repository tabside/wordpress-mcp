"""HTML pages: login (OAuth consent) and the account page of a gateway user.

GET  /login?req=<id>   login form for a pending authorization request
POST /login            check user name and password (GATEWAY_USERS), issue the code, redirect
GET  /account          self-service: connected applications, disconnect
POST /account/login | /account/logout | /account/disconnect
"""

from __future__ import annotations

import asyncio
import html
import secrets
import time
from datetime import datetime, timezone

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from ..config import Settings
from ..crypto import hash_password, verify_password
from ..limits import MemoryLimiter, RateLimited, audit
from ..store import Store
from .provider import GatewayAuthProvider

CSRF_COOKIE = "wpmcp_login"
SESSION_COOKIE = "wpmcp_account"

SCOPE_TEXT = {
    "wordpress:read": "Beiträge, Seiten, Kategorien, Schlagwörter und Medien der konfigurierten WordPress-Seiten lesen",
    "wordpress:write": "Beiträge und Seiten anlegen, ändern, zurücksetzen und in den Papierkorb legen, Dateien hochladen (jeweils nur mit Bestätigung)",
}

# Verifying against a dummy hash for unknown names keeps the response time the same.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16), iterations=600_000)


class LoginRejected(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message

STYLE = """
  :root { color-scheme: light dark; }
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0; padding: 24px 16px;
         background: #f4f5f7; color: #1b1f24; }
  .card { max-width: 540px; margin: 0 auto 18px; background: #fff; color: #1b1f24; border-radius: 10px;
          padding: 28px 28px 22px; box-shadow: 0 2px 12px rgba(0,0,0,.08); }
  h1 { font-size: 20px; margin: 0 0 6px; }
  p { line-height: 1.45; margin: 10px 0; }
  a { color: #2563eb; }
  .muted { color: #5b6471; font-size: 14px; }
  ul { padding-left: 20px; margin: 6px 0 14px; }
  label { display: block; font-size: 14px; margin: 14px 0 4px; }
  label.check { display: flex; gap: 8px; align-items: center; margin-top: 16px; }
  label.check input { width: auto; }
  input { width: 100%; box-sizing: border-box; padding: 10px 12px; font-size: 16px; border: 1px solid #c8ccd2;
          border-radius: 6px; background: #fff; color: #1b1f24; }
  input:focus { outline: 2px solid #2563eb; outline-offset: 1px; border-color: #2563eb; }
  .row { display: flex; gap: 10px; margin-top: 20px; }
  button { flex: 1; padding: 11px 14px; font-size: 16px; border-radius: 6px; border: 1px solid #2563eb;
           background: #2563eb; color: #fff; cursor: pointer; }
  button.secondary { background: transparent; color: inherit; border-color: #9aa1a9; }
  button.small { flex: none; padding: 6px 10px; font-size: 14px; }
  button.danger { background: #b91c1c; border-color: #b91c1c; }
  .error { background: #fde8e8; color: #9b1c1c; border-radius: 6px; padding: 10px 12px; font-size: 14px; }
  .notice { background: #e8f5e9; color: #1b5e20; border-radius: 6px; padding: 10px 12px; font-size: 14px; }
  .client { font-weight: 600; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  td, th { text-align: left; padding: 8px 6px; border-bottom: 1px solid #e5e7eb; vertical-align: middle; }
  form.inline { display: inline; }
  @media (prefers-color-scheme: dark) {
    body { background: #15181c; color: #e6e8eb; }
    .card { background: #1f242a; color: #e6e8eb; box-shadow: 0 2px 12px rgba(0,0,0,.4); }
    a { color: #7aa7ff; }
    .muted { color: #a3abb5; }
    input { background: #15181c; color: #e6e8eb; border-color: #3a4149; }
    button.secondary { border-color: #6b7280; }
    .error { background: #3b1414; color: #fca5a5; }
    .notice { background: #12301a; color: #a7e3b3; }
    td, th { border-bottom-color: #3a4149; }
  }
"""

HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self' https: http://127.0.0.1:* http://localhost:*; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
}



def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    doc = (
        '<!doctype html><html lang="de"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">'
        f"<title>{html.escape(title)}</title><style>{STYLE}</style></head><body>{body}</body></html>"
    )
    return HTMLResponse(doc, status_code=status, headers=HEADERS)


def simple_page(title: str, text: str, status: int = 400) -> HTMLResponse:
    return _page(title, f'<div class="card"><h1>{html.escape(title)}</h1><p>{html.escape(text)}</p></div>', status)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _fmt(ts: int | None) -> str:
    if not ts:
        return "nie"
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M")


class Pages:
    def __init__(self, settings: Settings, provider: GatewayAuthProvider, store: Store, limiter: MemoryLimiter):
        self._s = settings
        self._provider = provider
        self._store = store
        self._limiter = limiter
        self._sessions: dict[str, tuple[str, float, str]] = {}  # sid -> (user, expires, csrf)

    async def check_password(self, username: str, password: str) -> str:
        name = username.strip().lower()
        encoded = self._s.users.get(name)
        ok = await asyncio.to_thread(verify_password, password, encoded or _DUMMY_HASH)
        if not encoded or not ok or not password:
            raise LoginRejected("credentials", "Benutzername oder Passwort falsch.")
        audit("user_login", user=name)
        return name

    @property
    def _secure(self) -> bool:
        return self._s.public_base_url.startswith("https://")

    def _path(self, sub: str) -> str:
        return f"{self._s.base_path}{sub}"

    async def _client_name(self, client_id: str) -> str:
        client = await self._provider.get_client(client_id)
        if client is None:
            return "Eine unbekannte Anwendung"
        name = (client.client_name or "").strip()
        if name:
            return name
        return client_id if client_id.startswith("https://") else f"Anwendung {client_id[:8]}"

    # ------------------------------------------------------------------- login
    def _credentials_fields(self) -> str:
        return """
    <label for="username">Benutzername</label>
    <input id="username" name="username" type="text" required autocomplete="username" spellcheck="false" autocapitalize="none">
    <label for="password">Passwort</label>
    <input id="password" name="password" type="password" required autocomplete="current-password">"""

    def _login_form(self, *, request_id: str, client_name: str, scopes: list[str], csrf: str, error: str | None = None, revoke_others: bool = False) -> HTMLResponse:
        items = "".join(f"<li>{html.escape(SCOPE_TEXT.get(s, s))}</li>" for s in scopes) or "<li>Keine</li>"
        sites = "".join(f"<li>{html.escape(site.label)}</li>" for site in self._s.sites.values())
        err = f'<div class="error">{html.escape(error)}</div>' if error else ""
        account_url = html.escape(f"{self._s.public_base_url}/account")
        body = f"""
<div class="card">
  <h1>{html.escape(self._s.service_name)}</h1>
  <p><span class="client">{html.escape(client_name)}</span> möchte auf die WordPress-Seiten dieses Gateways zugreifen:</p>
  <ul>{sites}</ul>
  <p class="muted">Die Verbindung erhält folgende Rechte:</p>
  <ul>{items}</ul>
  {err}
  <form method="post" action="{html.escape(self._path('/login'))}" autocomplete="off">
    <input type="hidden" name="req" value="{html.escape(request_id)}">
    <input type="hidden" name="csrf" value="{html.escape(csrf)}">
    {self._credentials_fields()}
    <label class="check"><input type="checkbox" name="revoke_others" value="1" {"checked" if revoke_others else ""}> Andere Verbindungen trennen</label>
    <p class="muted">Trennt alle bisher verbundenen KI-Anwendungen dieses Benutzers.
    Verbindungen verwaltest du unter <a href="{account_url}">{account_url}</a>.</p>
    <div class="row">
      <button type="submit" name="action" value="allow">Verbinden</button>
      <button type="submit" name="action" value="deny" class="secondary" formnovalidate>Abbrechen</button>
    </div>
  </form>
  <p class="muted">Die Zugangsdaten der WordPress-Seiten bleiben auf dem Gateway und werden nie an die KI-Anwendung weitergegeben.</p>
</div>"""
        return _page(f"{self._s.service_name} - Anmeldung", body, 200 if not error else 401)

    async def login_get(self, request: Request) -> Response:
        request_id = request.query_params.get("req", "")
        pending = await self._provider.load_pending_request(request_id) if request_id else None
        if pending is None:
            return simple_page("Anfrage abgelaufen", "Diese Anmeldeanfrage ist ungültig oder abgelaufen. Bitte starte die Verbindung in deiner App erneut.")
        client_id, params = pending
        csrf = secrets.token_urlsafe(24)
        response = self._login_form(request_id=request_id, client_name=await self._client_name(client_id), scopes=params["scopes"], csrf=csrf)
        response.set_cookie(CSRF_COOKIE, csrf, max_age=self._s.auth_request_ttl, httponly=True, secure=self._secure, samesite="lax", path=self._path("/login"))
        return response

    async def login_post(self, request: Request) -> Response:
        form = await request.form()
        request_id = str(form.get("req") or "")
        csrf = str(form.get("csrf") or "")
        action = str(form.get("action") or "allow")
        username = str(form.get("username") or "")
        password = str(form.get("password") or "")
        revoke_others = str(form.get("revoke_others") or "") == "1"
        ip = client_ip(request)

        pending = await self._provider.load_pending_request(request_id) if request_id else None
        if pending is None:
            return simple_page("Anfrage abgelaufen", "Diese Anmeldeanfrage ist ungültig oder abgelaufen. Bitte starte die Verbindung in deiner App erneut.")
        client_id, params = pending
        cookie = request.cookies.get(CSRF_COOKIE, "")
        if not csrf or not cookie or not secrets.compare_digest(csrf, cookie):
            return simple_page("Ungültige Anfrage", "Das Formular konnte nicht geprüft werden. Bitte lade die Seite neu.")

        if action == "deny":
            audit("login_denied", ip=ip, client=client_id)
            return RedirectResponse(await self._provider.deny_login(request_id, params), status_code=302, headers={"Cache-Control": "no-store"})

        client_name = await self._client_name(client_id)

        def failure(message: str) -> Response:
            return self._login_form(request_id=request_id, client_name=client_name, scopes=params["scopes"], csrf=csrf, error=message, revoke_others=revoke_others)

        try:
            self._limiter.check_login(ip)
        except RateLimited:
            audit("login_rate_limited", ip=ip, client=client_id)
            return failure("Zu viele Fehlversuche. Bitte warte einige Minuten.")
        try:
            user = await self.check_password(username, password)
        except LoginRejected as exc:
            self._limiter.record_login_failure(ip)
            audit("login_failed", ip=ip, reason=exc.reason, client=client_id)
            return failure(exc.message)

        redirect = await self._provider.complete_login(request_id, client_id, params, user, revoke_others=revoke_others)
        response = RedirectResponse(redirect, status_code=302, headers={"Cache-Control": "no-store"})
        response.delete_cookie(CSRF_COOKIE, path=self._path("/login"))
        return response

    # ----------------------------------------------------------------- account
    def _session(self, request: Request) -> tuple[str, str, str] | None:
        sid = request.cookies.get(SESSION_COOKIE, "")
        entry = self._sessions.get(sid)
        if not entry:
            return None
        user, expires, csrf = entry
        if expires < time.time() or user not in self._s.users:
            self._sessions.pop(sid, None)
            return None
        return sid, user, csrf

    def _account_login_form(self, error: str | None = None, notice: str | None = None) -> HTMLResponse:
        err = f'<div class="error">{html.escape(error)}</div>' if error else ""
        note = f'<div class="notice">{html.escape(notice)}</div>' if notice else ""
        body = f"""
<div class="card">
  <h1>{html.escape(self._s.service_name)} - Konto</h1>
  <p class="muted">Anmelden, um verbundene Anwendungen zu sehen und zu trennen.</p>
  {err}{note}
  <form method="post" action="{html.escape(self._path('/account/login'))}" autocomplete="off">
    {self._credentials_fields()}
    <div class="row"><button type="submit">Anmelden</button></div>
  </form>
</div>"""
        return _page(f"{self._s.service_name} - Konto", body, 401 if error else 200)

    async def account_get(self, request: Request) -> Response:
        session = self._session(request)
        if session is None:
            return self._account_login_form()
        _, user, csrf = session
        names = await self._store.client_names()
        rows = []
        for conn in await self._store.connections(user):
            label = names.get(conn["client_id"]) or conn["client_id"][:40]
            rows.append(
                f"<tr><td>{html.escape(label)}</td><td>{_fmt(conn['created'])}</td><td>{_fmt(conn['last_used'] or None)}</td>"
                f'<td><form class="inline" method="post" action="{html.escape(self._path("/account/disconnect"))}">'
                f'<input type="hidden" name="csrf" value="{html.escape(csrf)}"><input type="hidden" name="family" value="{html.escape(conn["family_id"])}">'
                '<button class="small secondary" type="submit">Trennen</button></form></td></tr>'
            )
        table = (
            "<table><tr><th>Anwendung</th><th>Verbunden</th><th>Zuletzt genutzt</th><th></th></tr>" + "".join(rows) + "</table>"
            if rows
            else '<p class="muted">Keine Anwendung verbunden.</p>'
        )
        notice = request.query_params.get("done")
        note = '<div class="notice">Erledigt.</div>' if notice else ""
        body = f"""
<div class="card">
  <h1>{html.escape(self._s.service_name)} - Konto</h1>
  <p>Angemeldet als <b>{html.escape(user)}</b>.</p>
  {note}
  {table}
  <div class="row">
    <form class="inline" method="post" action="{html.escape(self._path('/account/disconnect'))}" style="flex:1;display:flex">
      <input type="hidden" name="csrf" value="{html.escape(csrf)}"><input type="hidden" name="family" value="*">
      <button class="danger" type="submit">Alle trennen</button></form>
    <form class="inline" method="post" action="{html.escape(self._path('/account/logout'))}" style="flex:1;display:flex">
      <input type="hidden" name="csrf" value="{html.escape(csrf)}">
      <button class="secondary" type="submit">Abmelden</button></form>
  </div>
</div>"""
        return _page(f"{self._s.service_name} - Konto", body)

    async def account_login(self, request: Request) -> Response:
        form = await request.form()
        ip = client_ip(request)
        try:
            self._limiter.check_login(ip)
        except RateLimited:
            return self._account_login_form("Zu viele Fehlversuche. Bitte warte einige Minuten.")
        try:
            user = await self.check_password(str(form.get("username") or ""), str(form.get("password") or ""))
        except LoginRejected as exc:
            self._limiter.record_login_failure(ip)
            audit("account_login_failed", ip=ip, reason=exc.reason)
            return self._account_login_form(exc.message)
        now = time.time()
        for sid in [s for s, v in self._sessions.items() if v[1] < now]:
            self._sessions.pop(sid, None)
        sid = secrets.token_urlsafe(32)
        self._sessions[sid] = (user, now + self._s.account_session_ttl, secrets.token_urlsafe(24))
        response = RedirectResponse(self._path("/account"), status_code=303)
        response.set_cookie(SESSION_COOKIE, sid, max_age=self._s.account_session_ttl, httponly=True, secure=self._secure, samesite="strict", path=self._path("/account"))
        return response

    async def _checked(self, request: Request) -> tuple[str, str, dict] | None:
        session = self._session(request)
        if session is None:
            return None
        form = dict(await request.form())
        if not secrets.compare_digest(str(form.get("csrf") or ""), session[2]):
            return None
        return session[0], session[1], form

    async def account_logout(self, request: Request) -> Response:
        checked = await self._checked(request)
        if checked:
            self._sessions.pop(checked[0], None)
        response = RedirectResponse(self._path("/account"), status_code=303)
        response.delete_cookie(SESSION_COOKIE, path=self._path("/account"))
        return response

    async def account_disconnect(self, request: Request) -> Response:
        checked = await self._checked(request)
        if checked is None:
            return RedirectResponse(self._path("/account"), status_code=303)
        _, user, form = checked
        family = str(form.get("family") or "")
        if family == "*":
            revoked = await self._store.revoke_user(user)
        else:
            owned = {c["family_id"] for c in await self._store.connections(user)}
            revoked = await self._store.revoke_family(family) if family in owned else 0
        audit("tokens_revoked", user=user, tokens_revoked=revoked, source="account_page")
        return RedirectResponse(self._path("/account?done=1"), status_code=303)
