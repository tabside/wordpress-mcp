"""OAuth login, tool forwarding to the plugin, confirm, audit log."""

from __future__ import annotations

import base64
import json
import logging

from conftest import BASE, call, connect, token


def test_discovery(gateway):
    client, _, _ = gateway
    r = client.get("/.well-known/oauth-protected-resource/mcp")
    assert r.status_code == 200 and r.json()["resource"] == f"{BASE}/mcp"
    assert r.json()["scopes_supported"] == ["wordpress:read", "wordpress:write"]
    r = client.get("/.well-known/oauth-authorization-server")
    assert r.status_code == 200 and r.json()["issuer"].rstrip("/") == BASE
    r = client.post("/mcp", json={})
    assert r.status_code == 401 and "resource_metadata" in r.headers.get("www-authenticate", "")
    assert client.get("/healthz").json()["status"] == "ok"


def test_login_page_and_wrong_password(gateway):
    client, _, _ = gateway
    r, _, _, page = connect(client, password="wrong password")
    assert "Kunde AG" in page.text and "Claude" in page.text
    assert r.status_code == 401 and "falsch" in r.text
    r, _, _, _ = connect(client, username="unknown")
    assert r.status_code == 401


def test_credentials_never_leak(gateway, access):
    client, _, services = gateway
    out = call(client, access, "list_sites")["structuredContent"]
    assert out["sites"][0]["id"] == "kunde" and out["sites"][0]["label"] == "Kunde AG"
    assert "abcd efgh" not in json.dumps(out)
    raw = open(services.settings.database_path, "rb").read()
    assert b"abcd efgh" not in raw and access.encode() not in raw  # tokens only as hash


def test_list_sites_check_and_version(gateway, access):
    client, _, _ = gateway
    out = call(client, access, "list_sites", {"check": True})["structuredContent"]
    assert out["sites"][0]["status"] == "ok" and out["sites"][0]["plugin_version"] == "1.0.0"
    v = call(client, access, "get_version", {"site": "kunde"})["structuredContent"]
    assert v["service"] == "wordpress-mcp" and v["plugin"]["mcp_adapter"] == "0.7.1"


def test_unknown_site(gateway, access):
    client, _, _ = gateway
    res = call(client, access, "post_list", {"site": "gibtsnicht"})
    assert res["isError"] is True and "kunde" in res["content"][0]["text"]


def test_plain_permalinks_keep_rest_route():
    import asyncio

    import httpx

    from wordpressmcp.config import SiteConfig
    from wordpressmcp.wordpress import SiteClient

    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    site = SiteConfig("k", "K", "https://kunde.example.com", "https://kunde.example.com/?rest_route=", "claude-mcp", "pw")
    client = SiteClient(site, timeout=5, transport=httpx.MockTransport(handler))
    asyncio.run(client.call("post_list", {"type": "page"}))
    asyncio.run(client.call("post_create", {"title": "x"}))
    get, post = seen
    assert get.method == "GET" and get.url.params["rest_route"] == "/wp-abilities/v1/abilities/tabside/post-list/run"
    assert get.url.params["input[type]"] == "page"
    assert post.method == "POST" and post.url.params["rest_route"] == "/wp-abilities/v1/abilities/tabside/post-create/run"


def test_read_is_get_with_query_write_is_post(gateway, access):
    client, fake, _ = gateway
    call(client, access, "post_list", {"site": "kunde", "search": "Ä b", "limit": 5})
    req = fake.requests[-1]
    assert req.method == "GET" and req.url.path == "/wp-json/wp-abilities/v1/abilities/tabside/post-list/run"
    assert dict(req.url.params.multi_items())["input[search]"] == "Ä b" and dict(req.url.params.multi_items())["input[limit]"] == "5"
    call(client, access, "post_create", {"site": "kunde", "title": "x", "tags": ["a", "b"]})
    req = fake.requests[-1]
    assert req.method == "POST" and json.loads(req.content)["input"]["tags"] == ["a", "b"]


def test_create_preview_then_confirm_and_audit(gateway, access, caplog):
    client, fake, _ = gateway
    caplog.set_level(logging.INFO, logger="wordpressmcp.audit")
    prev = call(client, access, "post_create", {"site": "kunde", "title": "Test", "status": "publish", "date": "2026-12-01 09:00", "categories": ["Recht", 3]})
    assert prev["structuredContent"]["confirmed"] is False
    name, args = fake.calls[-1]
    assert name == "tabside-post-create" and args["confirm"] is False and args["categories"] == ["Recht", 3]
    assert "slug" not in args  # None is not forwarded
    done = call(client, access, "post_create", {"site": "kunde", "title": "Test", "confirm": True})["structuredContent"]
    assert done["confirmed"] is True and done["post"]["id"] == 42 and done["site"] == "kunde"
    events = [json.loads(r.message) for r in caplog.records if r.name == "wordpressmcp.audit" and '"tool_write"' in r.message]
    assert events[-1]["post_id"] == 42 and events[-1]["executed"] is True and events[-1]["user"] == "kim" and events[-1]["site"] == "kunde"
    assert all("abcd" not in r.message for r in caplog.records)


def test_plugin_error_becomes_tool_error(gateway, access):
    client, _, _ = gateway
    res = call(client, access, "post_get", {"site": "kunde", "id": 404})
    assert res["isError"] is True and "nicht gefunden" in res["content"][0]["text"]


def test_site_rejects_login(gateway, access):
    client, fake, _ = gateway
    fake.reject_auth = True
    res = call(client, access, "post_list", {"site": "kunde"})
    assert res["isError"] is True and "Anwendungspasswort" in res["content"][0]["text"]
    assert "abcd" not in res["content"][0]["text"]


def test_media_upload_base64(gateway, access):
    client, fake, _ = gateway
    pdf = b"%PDF-1.4 test"
    res = call(client, access, "media_upload", {"site": "kunde", "data_base64": base64.b64encode(pdf).decode(), "filename": "merkblatt.pdf", "confirm": True})
    out = res["structuredContent"]
    assert out["media"]["url"].endswith("merkblatt.pdf") and out["media"]["size"] == len(pdf)
    res = call(client, access, "media_upload", {"site": "kunde", "data_base64": base64.b64encode(pdf).decode()})
    assert res["isError"] is True and "filename" in res["content"][0]["text"]
    res = call(client, access, "media_upload", {"site": "kunde", "data_base64": "%%%", "filename": "a.pdf"})
    assert res["isError"] is True


def test_read_only_scope_cannot_write(gateway):
    client, fake, _ = gateway
    r, cid, ver, _ = connect(client, scope="wordpress:read")
    access = token(client, cid, ver, r)["access_token"]
    assert call(client, access, "post_list", {"site": "kunde"})["structuredContent"]["total"] == 1
    res = call(client, access, "post_create", {"site": "kunde", "title": "x", "confirm": True})
    assert res["isError"] is True and "wordpress:write" in res["content"][0]["text"]
    assert not [c for c in fake.calls if c[0] == "tabside-post-create"]


def test_refresh_rotation_and_user_removed(gateway, base_env):
    client, _, services = gateway
    r, cid, ver, _ = connect(client)
    tokens = token(client, cid, ver, r)
    r1 = client.post("/token", data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": cid})
    assert r1.status_code == 200
    r2 = client.post("/token", data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": cid})
    assert r2.status_code == 400  # reuse detected, family revoked
    res = client.post("/mcp", headers={"Authorization": f"Bearer {r1.json()['access_token']}", "Accept": "application/json, text/event-stream"}, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert res.status_code == 401


def test_tools_list(gateway, access):
    client, _, _ = gateway
    r = client.post("/mcp", headers={"Authorization": f"Bearer {access}", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert {
        "get_version", "list_sites", "post_list", "post_get", "category_list", "tag_list", "media_list",
        "post_create", "post_update", "media_upload", "post_trash", "post_rollback", "docx_to_content",
    } <= names
    assert len(names) == 70


def test_account_page_disconnect(gateway, access):
    client, _, _ = gateway
    assert client.get("/account").status_code == 200
    assert client.post("/account/login", data={"username": "kim", "password": "nope"}).status_code == 401
    r = client.post("/account/login", data={"username": "kim", "password": "correct horse battery"}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/account")
    assert "Claude" in page.text
    import re

    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    client.post("/account/disconnect", data={"csrf": csrf, "family": "*"})
    res = client.post("/mcp", headers={"Authorization": f"Bearer {access}", "Accept": "application/json, text/event-stream"}, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert res.status_code == 401
