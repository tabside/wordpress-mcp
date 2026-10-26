"""End-to-end against a real WordPress with only tabside-mcp installed (no MCP Adapter).

Skipped unless WP_TEST_URL is set. CI starts a WordPress with SQLite via
plugin/tests/setup-wordpress.sh; locally:

    plugin/tests/setup-wordpress.sh /tmp/wp 8871 wordpress-7.1.3.zip
    WP_TEST_URL=http://127.0.0.1:8871 WP_TEST_APP_PASSWORD=... WP_TEST_OTHER_APP_PASSWORD=... pytest tests/test_integration_wordpress.py

Chain: OAuth login at the gateway -> gateway tool -> plugin ability -> WordPress.
"""

from __future__ import annotations

import base64
import os
import re
import struct
import zlib
from datetime import datetime, timedelta

import pytest
from starlette.testclient import TestClient

from conftest import BASE, call, connect, token
from test_config_fetch_docx import sample_docx
from wordpressmcp.config import Settings
from wordpressmcp.server import build_app, build_services

WP_URL = os.environ.get("WP_TEST_URL")
pytestmark = pytest.mark.skipif(not WP_URL, reason="WP_TEST_URL not set (needs a running WordPress)")


def tiny_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"\x00\xff\x00\x00"  # one red pixel
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def minimal_pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


@pytest.fixture()
def wp(base_env):
    for key in ("WP_SITE_KUNDE_URL", "WP_SITE_KUNDE_APP_PASSWORD", "WP_SITE_KUNDE_LABEL"):
        base_env.delenv(key)
    base_env.setenv("WP_SITE_TEST_URL", WP_URL)
    base_env.setenv("WP_SITE_TEST_REST_URL", f"{WP_URL}/?rest_route=")
    base_env.setenv("WP_SITE_TEST_APP_PASSWORD", os.environ["WP_TEST_APP_PASSWORD"])
    base_env.setenv("WP_SITE_TEST_USER", "claude-mcp")
    base_env.setenv("WP_SITE_OTHER_URL", WP_URL)
    base_env.setenv("WP_SITE_OTHER_REST_URL", f"{WP_URL}/?rest_route=")
    base_env.setenv("WP_SITE_OTHER_USER", "other")
    base_env.setenv("WP_SITE_OTHER_APP_PASSWORD", os.environ["WP_TEST_OTHER_APP_PASSWORD"])
    base_env.setenv("WP_SITE_READER_URL", WP_URL)
    base_env.setenv("WP_SITE_READER_REST_URL", f"{WP_URL}/?rest_route=")
    base_env.setenv("WP_SITE_READER_USER", "leser")
    base_env.setenv("WP_SITE_READER_APP_PASSWORD", os.environ["WP_TEST_READER_APP_PASSWORD"])
    services = build_services(Settings.load())
    with TestClient(build_app(services), base_url=BASE) as client:
        r, cid, ver, _ = connect(client)
        yield client, token(client, cid, ver, r)["access_token"]


def ok(result: dict) -> dict:
    assert result.get("isError") is not True, result["content"][0]["text"]
    return result["structuredContent"]


def err(result: dict) -> str:
    assert result.get("isError") is True, result
    return result["content"][0]["text"]


def test_version_and_sites(wp):
    client, access = wp
    sites = ok(call(client, access, "list_sites", {"check": True}))["sites"]
    by_id = {s["id"]: s for s in sites}
    assert by_id["test"]["status"] == "ok" and by_id["test"]["plugin_version"]
    assert by_id["other"]["status"] == "ok"  # any editor with an Application Password
    assert by_id["reader"]["status"] == "error"  # a subscriber lacks the capabilities
    v = ok(call(client, access, "get_version", {"site": "test"}))
    assert v["plugin"]["wordpress"] and v["plugin"]["user"] == "claude-mcp" and v["plugin"]["allowed_user"] is None


def test_spec_run_draft_upload_link_update_rollback_trash(wp):
    client, access = wp
    future = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d") + " 08:00"

    # PDF upload: preview first, then for real
    pdf_b64 = base64.b64encode(minimal_pdf()).decode()
    prev = ok(call(client, access, "media_upload", {"site": "test", "data_base64": pdf_b64, "filename": "Merkblatt Test.pdf"}))
    assert prev["confirmed"] is False and prev["preview"]["mime_type"] == "application/pdf"
    pdf = ok(call(client, access, "media_upload", {"site": "test", "data_base64": pdf_b64, "filename": "Merkblatt Test.pdf", "title": "Merkblatt", "confirm": True}))["media"]
    assert pdf["url"].endswith(".pdf") and pdf["mime_type"] == "application/pdf"

    img = ok(call(client, access, "media_upload", {"site": "test", "data_base64": base64.b64encode(tiny_png()).decode(), "filename": "bild.png", "alt_text": "Rot", "confirm": True}))["media"]
    assert img["mime_type"] == "image/png" and img["alt_text"] == "Rot"

    # Word -> blocks, PDF link appended
    conv = ok(call(client, access, "docx_to_content", {"data_base64": base64.b64encode(sample_docx()).decode()}))
    content = conv["content"] + f'\n\n<!-- wp:paragraph -->\n<p><a href="{pdf["url"]}">Merkblatt (PDF)</a> \\ "Zitat" &amp; \'x\'</p>\n<!-- /wp:paragraph -->'

    args = {"site": "test", "title": conv["title"], "content": content, "status": "draft", "date": future, "categories": ["Gemeinden"], "tags": ["Test-Schlagwort"], "featured_media": img["id"], "excerpt": "Kurz"}
    prev = ok(call(client, access, "post_create", args))
    assert prev["confirmed"] is False and prev["preview"]["status"] == "draft" and prev["preview"]["categories"] == ["Gemeinden"]
    assert ok(call(client, access, "post_list", {"site": "test", "search": conv["title"]}))["total"] == 0  # preview changed nothing

    post = ok(call(client, access, "post_create", {**args, "confirm": True}))["post"]
    pid = post["id"]
    assert post["status"] == "draft" and post["date"] == future + ":00"
    assert post["content"] == content  # stored byte for byte (slashes, quotes)
    assert post["format"] == "blocks" and pdf["url"] in post["content"]
    assert [c["name"] for c in post["categories"]] == ["Gemeinden"] and [t["name"] for t in post["tags"]] == ["Test-Schlagwort"]
    assert post["featured_media"]["id"] == img["id"] and post["excerpt"] == "Kurz"

    # Update with backup
    prev = ok(call(client, access, "post_update", {"site": "test", "id": pid, "title": "Neuer Titel"}))
    assert prev["confirmed"] is False and prev["preview"]["changes"]["title"] == {"old": conv["title"], "new": "Neuer Titel"}
    upd = ok(call(client, access, "post_update", {"site": "test", "id": pid, "title": "Neuer Titel", "content": "<p>neu</p>", "featured_media": 0, "confirm": True}))
    assert upd["post"]["title"] == "Neuer Titel" and upd["post"]["featured_media"] is None and upd["backup_id"]
    got = ok(call(client, access, "post_get", {"site": "test", "id": pid}))
    assert got["backups"][0]["id"] == upd["backup_id"] and got["backups"][0]["title"] == conv["title"]

    # Rollback restores title, content, thumbnail and keeps a safety backup
    prev = ok(call(client, access, "post_rollback", {"site": "test", "id": pid}))
    assert prev["confirmed"] is False and set(prev["preview"]["changes"]) >= {"title", "content", "featured_media"}
    rb = ok(call(client, access, "post_rollback", {"site": "test", "id": pid, "confirm": True}))
    assert rb["post"]["title"] == conv["title"] and rb["post"]["content"] == content and rb["post"]["featured_media"]["id"] == img["id"]
    assert rb["post"]["date"] == future + ":00" and rb["post"]["status"] == "draft"
    assert len(rb["post"]["backups"]) == 2 and rb["post"]["backups"][0]["reason"] == "rollback"

    # Schedule: publish with a future date becomes future
    sched = ok(call(client, access, "post_update", {"site": "test", "id": pid, "status": "publish", "confirm": True}))
    assert sched["post"]["status"] == "future" and any("future" in n for n in sched["notes"])

    # Trash
    prev = ok(call(client, access, "post_trash", {"site": "test", "id": pid}))
    assert prev["confirmed"] is False
    assert ok(call(client, access, "post_get", {"site": "test", "id": pid}))["status"] == "future"
    trashed = ok(call(client, access, "post_trash", {"site": "test", "id": pid, "confirm": True}))
    assert trashed["post"]["status"] == "trash"
    assert "Papierkorb" in err(call(client, access, "post_trash", {"site": "test", "id": pid, "confirm": True}))


def test_validation_errors(wp):
    client, access = wp
    assert "Kategorie nicht gefunden" in err(call(client, access, "post_create", {"site": "test", "title": "x", "categories": ["Gibt es nicht"]}))
    assert "nicht in der Zukunft" in err(call(client, access, "post_create", {"site": "test", "title": "x", "status": "future", "date": "2020-01-01 10:00"}))
    assert "nicht lesbar" in err(call(client, access, "post_create", {"site": "test", "title": "x", "date": "22.09.2026"}))
    assert "nur bei Beiträgen" in err(call(client, access, "post_create", {"site": "test", "title": "x", "type": "page", "categories": ["Recht"]}))
    assert "nicht gefunden" in err(call(client, access, "post_get", {"site": "test", "id": 999999}))
    assert "Keine Felder" in err(call(client, access, "post_update", {"site": "test", "id": 1, "confirm": True}))
    assert "nicht erlaubt" in err(call(client, access, "media_upload", {"site": "test", "data_base64": "eA==", "filename": "x.php", "confirm": True}))
    assert "Berechtigung" in err(call(client, access, "post_list", {"site": "reader"}))


def test_past_date_publishes_backdated_and_page(wp):
    client, access = wp
    post = ok(call(client, access, "post_create", {"site": "test", "title": "Rückdatiert", "status": "publish", "date": "2026-09-22 08:00", "confirm": True}))["post"]
    assert post["status"] == "publish" and post["date"] == "2026-09-22 08:00:00"
    page = ok(call(client, access, "post_create", {"site": "test", "title": "Seite", "type": "page", "confirm": True}))["post"]
    assert page["type"] == "page" and page["status"] == "draft"
    listed = ok(call(client, access, "post_list", {"site": "test", "type": "page"}))
    assert any(p["id"] == page["id"] for p in listed["posts"])
    cats = ok(call(client, access, "category_list", {"site": "test"}))["terms"]
    assert {"Recht", "Gemeinden"} <= {c["name"] for c in cats}
    media = ok(call(client, access, "media_list", {"site": "test", "mime_type": "application/pdf"}))
    assert all(m["mime_type"] == "application/pdf" for m in media["media"])
    for pid in (post["id"], page["id"]):
        ok(call(client, access, "post_trash", {"site": "test", "id": pid, "confirm": True}))


def test_block_markup_survives_saving(wp):
    """Block comments must not be stripped by WordPress (kses) when saving converted content."""
    client, access = wp
    conv = ok(call(client, access, "docx_to_content", {"data_base64": base64.b64encode(sample_docx()).decode()}))
    post = ok(call(client, access, "post_create", {"site": "test", "title": "Blocktest", "content": conv["content"], "confirm": True}))["post"]
    names = re.findall(r"<!-- wp:([a-z-]+)", post["content"])
    assert set(names) == {"paragraph", "heading", "list", "list-item", "table"}
    ok(call(client, access, "post_trash", {"site": "test", "id": post["id"], "confirm": True}))
