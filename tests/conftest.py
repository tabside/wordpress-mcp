"""Shared fixtures: settings from env, a fake WordPress (core abilities REST endpoint), OAuth helpers."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from starlette.testclient import TestClient

from wordpressmcp.config import Settings
from wordpressmcp.crypto import hash_password
from wordpressmcp.server import build_app, build_services

BASE = "http://localhost"
PASSWORD = "correct horse battery"
APP_PASSWORD = "abcd efgh ijkl mnop qrst uvwx"
REDIRECT = "https://claude.ai/api/mcp/auth_callback"


class FakeWordPress:
    """Core REST endpoint /wp-json/wp-abilities/v1/abilities/tabside/<name>/run with the plugin's abilities."""

    READ_ONLY = {"get-version", "post-list", "post-get", "category-list", "tag-list", "media-list"}

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.requests: list[httpx.Request] = []
        self.reject_auth = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        auth = request.headers.get("authorization", "")
        user, _, pw = base64.b64decode(auth.split(" ", 1)[1]).decode().partition(":") if auth.startswith("Basic ") else ("", "", "")
        if self.reject_auth or user != "claude-mcp" or pw != APP_PASSWORD:
            return httpx.Response(401, json={"code": "incorrect_password", "message": "The provided password is an invalid application password.", "data": {"status": 401}})
        prefix = "/wp-json/wp-abilities/v1/abilities/tabside/"
        if request.url.host != "kunde.example.com" or not request.url.path.startswith(prefix) or not request.url.path.endswith("/run"):
            return httpx.Response(404, json={"code": "rest_no_route", "message": "No route was found matching the URL and request method.", "data": {"status": 404}})
        slug = request.url.path[len(prefix):-len("/run")]
        expected = "GET" if slug in self.READ_ONLY else "POST"
        if request.method != expected:
            return httpx.Response(405, json={"code": "rest_ability_invalid_method", "message": "wrong method", "data": {"status": 405}})
        if expected == "GET":
            args = _parse_php_query(request.url.params.multi_items())
        else:
            args = json.loads(request.content).get("input") or {}
        name = "tabside-" + slug
        self.calls.append((name, args))
        result = self.tool(name, args)
        if isinstance(result, str):
            return httpx.Response(422, json={"code": "tabside_mcp_error", "message": result, "data": {"status": 422}})
        return httpx.Response(200, json=result)

    def tool(self, name: str, args: dict):
        if name == "tabside-get-version":
            return {"plugin": "tabside-mcp", "version": "1.0.0", "commit": "abc", "wordpress": "7.1.3", "mcp_adapter": "0.7.1"}
        if name == "tabside-post-create":
            if not args.get("confirm"):
                return {"confirmed": False, "preview": {"title": args["title"], "status": args.get("status", "draft")}, "notes": []}
            return {"confirmed": True, "post": {"id": 42, "title": args["title"], "status": args.get("status", "draft")}}
        if name == "tabside-post-update":
            return {"confirmed": bool(args.get("confirm")), "backup_id": "20261025-120000-abcdef" if args.get("confirm") else None, "post": {"id": args["id"]}}
        if name == "tabside-media-upload":
            data = base64.b64decode(args["data_base64"])
            if not args.get("confirm"):
                return {"confirmed": False, "preview": {"filename": args["filename"], "size": len(data)}}
            return {"confirmed": True, "media": {"id": 7, "url": f"https://kunde.example.com/wp-content/uploads/{args['filename']}", "size": len(data)}}
        if name == "tabside-post-get":
            if int(args["id"]) == 404:
                return "Beitrag/Seite 404 nicht gefunden."
            return {"id": int(args["id"]), "title": "Hallo", "content": "<p>x</p>", "backups": []}
        if name == "tabside-post-list":
            return {"total": 1, "page": 1, "pages": 1, "posts": [{"id": 1, "title": "Hallo"}]}
        return f"unknown tool {name}"


def _parse_php_query(items) -> dict:
    """input[limit]=5&input[tags][]=a -> {"limit": "5", "tags": ["a"]} (like PHP)."""
    out: dict = {}
    for key, value in items:
        parts = re.findall(r"\[([^\]]*)\]", key)
        if not key.startswith("input[") or not parts:
            continue
        if len(parts) == 2 and parts[1] == "":
            out.setdefault(parts[0], []).append(value)
        else:
            out[parts[0]] = value
    return out


def connect(client: TestClient, username: str = "kim", password: str = PASSWORD, scope: str | None = None):
    reg = client.post("/register", json={"redirect_uris": [REDIRECT], "client_name": "Claude", "token_endpoint_auth_method": "none"})
    assert reg.status_code == 201, reg.text
    client_id = reg.json()["client_id"]
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params = {
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT, "code_challenge": challenge,
        "code_challenge_method": "S256", "state": "st", "resource": f"{BASE}/mcp",
    }
    if scope:
        params["scope"] = scope
    r = client.get("/authorize", params=params, follow_redirects=False)
    assert r.status_code == 302, r.text
    login_url = r.headers["location"]
    page = client.get(login_url.replace(BASE, ""))
    assert page.status_code == 200
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    req = parse_qs(urlparse(login_url).query)["req"][0]
    r = client.post("/login", data={"req": req, "csrf": csrf, "username": username, "password": password, "action": "allow"}, follow_redirects=False)
    return r, client_id, verifier, page


def token(client: TestClient, client_id: str, verifier: str, login_response) -> dict:
    code = parse_qs(urlparse(login_response.headers["location"]).query)["code"][0]
    r = client.post("/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT, "client_id": client_id, "code_verifier": verifier, "resource": f"{BASE}/mcp"})
    assert r.status_code == 200, r.text
    return r.json()


def call(client: TestClient, access: str, name: str, args: dict | None = None) -> dict:
    r = client.post(
        "/mcp",
        headers={"Authorization": f"Bearer {access}", "Accept": "application/json, text/event-stream", "Content-Type": "application/json", "MCP-Protocol-Version": "2025-06-18"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args or {}}},
    )
    assert r.status_code == 200, r.text
    return r.json()["result"]


@pytest.fixture()
def base_env(monkeypatch, tmp_path):
    for key in list(__import__("os").environ):
        if key.startswith("WP_SITE_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("PUBLIC_BASE_URL", BASE)
    monkeypatch.setenv("GATEWAY_USERS", f"kim={hash_password(PASSWORD, iterations=1000)},anna={hash_password('another secret pw', iterations=1000)}")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("WP_SITE_KUNDE_URL", "https://kunde.example.com")
    monkeypatch.setenv("WP_SITE_KUNDE_APP_PASSWORD", APP_PASSWORD)
    monkeypatch.setenv("WP_SITE_KUNDE_LABEL", "Kunde AG")
    return monkeypatch


@pytest.fixture()
def gateway(base_env):
    fake = FakeWordPress()
    services = build_services(Settings.load(), wp_transport=httpx.MockTransport(fake.handler))
    with TestClient(build_app(services), base_url=BASE) as client:
        yield client, fake, services


@pytest.fixture()
def access(gateway):
    client, _, _ = gateway
    r, cid, ver, _ = connect(client)
    assert r.status_code == 302, r.text
    return token(client, cid, ver, r)["access_token"]
