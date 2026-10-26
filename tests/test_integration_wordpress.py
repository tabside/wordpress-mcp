"""End-to-end against a real WordPress with tabside-mcp, Elementor and Redirection (no MCP Adapter).

Skipped unless WP_TEST_URL is set. CI starts a WordPress with SQLite via
plugin/tests/setup-wordpress.sh (which also creates the Elementor test content); locally:

    plugin/tests/setup-wordpress.sh /tmp/wp 8871 6.9 > /tmp/wp.txt
    php -S 127.0.0.1:8871 -t /tmp/wp &
    WP_TEST_URL=http://127.0.0.1:8871 WP_TEST_APP_PASSWORD=... WP_TEST_OTHER_APP_PASSWORD=... \
    WP_TEST_READER_APP_PASSWORD=... WP_TEST_ADMIN_APP_PASSWORD=... pytest tests/test_integration_wordpress.py

Sites in the gateway: test (editor claude-mcp), other (editor), reader (subscriber), admin (administrator).
Chain: OAuth login at the gateway -> gateway tool -> plugin ability -> WordPress.
"""

from __future__ import annotations

import base64
import os
import re
import struct
import zlib
from datetime import datetime, timedelta

import httpx
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
    base_env.setenv("WP_SITE_ADMIN_URL", WP_URL)
    base_env.setenv("WP_SITE_ADMIN_REST_URL", f"{WP_URL}/?rest_route=")
    base_env.setenv("WP_SITE_ADMIN_USER", "admin")
    base_env.setenv("WP_SITE_ADMIN_APP_PASSWORD", os.environ["WP_TEST_ADMIN_APP_PASSWORD"])
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
    assert by_id["test"]["elementor_version"] and by_id["test"]["admin_tools"] == "disabled"  # editor
    assert by_id["admin"]["admin_tools"] == "enabled" and v["plugin"]["redirect_plugin"] == "redirection"


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
    assert "beim Beitragstyp page nicht" in err(call(client, access, "post_create", {"site": "test", "title": "x", "type": "page", "categories": ["Recht"]}))
    assert "Unbekannter Beitragstyp" in err(call(client, access, "post_create", {"site": "test", "title": "x", "type": "gibtsnicht"}))
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


def test_hide_featured_on_single(wp):
    client, access = wp
    post = ok(call(client, access, "post_create", {"site": "test", "title": "Bild ausblenden", "hide_featured_on_single": True, "confirm": True}))["post"]
    assert post["hide_featured_on_single"] is True and post["meta"]["blockchain_hide_single_featured"] == "1"
    prev = ok(call(client, access, "post_update", {"site": "test", "id": post["id"], "hide_featured_on_single": False}))
    assert prev["preview"]["changes"]["hide_featured_on_single"] == {"old": True, "new": False}
    upd = ok(call(client, access, "post_update", {"site": "test", "id": post["id"], "hide_featured_on_single": False, "confirm": True}))["post"]
    assert upd["hide_featured_on_single"] is False and "blockchain_hide_single_featured" not in upd["meta"]
    rb = ok(call(client, access, "post_rollback", {"site": "test", "id": post["id"], "confirm": True}))["post"]
    assert rb["hide_featured_on_single"] is True
    ok(call(client, access, "post_trash", {"site": "test", "id": post["id"], "confirm": True}))


# ---------------------------------------------------------------------- Elementor, post types, administration

def by_title(client, access, site: str, type_: str, title: str, **filters) -> dict:
    posts = ok(call(client, access, "post_list", {"site": site, "type": type_, "search": title, "limit": 100, **filters}))["posts"]
    matches = [p for p in posts if p["title"] == title]
    assert matches, f"{type_} {title!r} not found"
    return matches[0]


def fixtures(client, access, site: str = "test") -> dict[str, int]:
    """IDs of the content created by plugin/tests/elementor-fixture.php."""
    popup = {"meta_key": "_elementor_template_type", "meta_value": "popup"}
    return {
        "page": by_title(client, access, site, "page", "Vorlage Leistung")["id"],
        "popup1": by_title(client, access, site, "elementor_library", "Popup Eins", **popup)["id"],
        "popup2": by_title(client, access, site, "elementor_library", "Popup Zwei", **popup)["id"],
        "section": by_title(client, access, site, "elementor_library", "Kontakt-Abschnitt")["id"],
        "service": by_title(client, access, site, "service", "Leistung Neu")["id"],
    }


def tree(client, access, post_id: int, site: str = "test") -> list:
    return ok(call(client, access, "elementor_get", {"site": site, "post_id": post_id, "full": True}))["elements"]


def strip(nodes: list) -> list:
    """Tree without element IDs and paths (they change when copying)."""
    out = []
    for node in nodes:
        node = {k: v for k, v in node.items() if k not in ("id", "path")}
        if "elements" in node:
            node["elements"] = strip(node["elements"])
        out.append(node)
    return out


def walk(nodes: list):
    for node in nodes:
        yield node
        yield from walk(node.get("elements", []))


def page_html(url: str) -> str:
    r = httpx.get(url, follow_redirects=True, timeout=60)
    assert r.status_code == 200, (url, r.status_code)
    for marker in ("Fatal error", "Warning:", "Parse error", "critical error"):
        assert marker not in r.text, f"{marker} on {url}"
    return r.text


def test_elementor_duplicate_page_and_popup_without_data_loss(wp):
    client, access = wp
    ids = fixtures(client, access)
    original = tree(client, access, ids["page"])
    texts = [n["settings"].get("editor") for n in walk(original) if n.get("widgetType") == "text-editor"]
    assert texts and '"Zitat"' in texts[0] and "\\" in texts[0] and "ä" in texts[0] and "</script>" in texts[0]

    prev = ok(call(client, access, "post_duplicate", {"site": "test", "id": ids["page"]}))
    assert prev["confirmed"] is False and prev["preview"]["elementor"]["elements"] == 5
    copy = ok(call(client, access, "post_duplicate", {"site": "test", "id": ids["page"], "title": "Kopie Leistung", "status": "publish", "confirm": True}))
    assert copy["verify"] == {"meta_complete": True, "elementor_equal": True, "elementor_new_ids": True}
    assert copy["post"]["template"] == "elementor_header_footer" and copy["post"]["elementor_info"]["template_type"] == "wp-page"
    copied = tree(client, access, copy["post"]["id"])
    assert strip(copied) == strip(original)  # same structure and settings, escapes intact
    assert not {n["id"] for n in walk(copied)} & {n["id"] for n in walk(original)}  # new element IDs
    css = copy["cache"]["elementor_css"][str(copy["post"]["id"])]
    assert css["status"] == "file" and httpx.get(css["url"], timeout=30).status_code == 200

    html = page_html(copy["post"]["link"])
    # The template widget renders only with Elementor Pro, so "Kontakt Vorlage" is not checked here.
    assert "Willkommen bei Kunde" in html and "Umlaut ä" in html and "Beratung" in html

    popup = ok(call(client, access, "post_duplicate", {"site": "test", "id": ids["popup1"], "title": "Popup Eins B", "confirm": True}))
    assert popup["verify"]["elementor_equal"] is True and popup["post"]["template_type"] == "popup"
    assert popup["post"]["elementor_info"]["conditions"] == []  # the copy does not show up anywhere
    assert ok(call(client, access, "post_get", {"site": "test", "id": ids["popup1"]}))["elementor_info"]["conditions"] == ["include/general"]
    assert "Pro" in err(call(client, access, "post_duplicate", {"site": "test", "id": ids["popup1"], "conditions": ["include/general"]}))


def test_elementor_copy_layout_to_service_with_popup_map(wp):
    client, access = wp
    ids = fixtures(client, access)
    target = ok(call(client, access, "post_create", {"site": "test", "type": "service", "title": "Leistung Kopie", "status": "publish", "confirm": True}))["post"]
    popup = ok(call(client, access, "post_duplicate", {"site": "test", "id": ids["popup1"], "title": "Popup Eins Service", "status": "publish", "confirm": True}))["post"]

    bad = err(call(client, access, "elementor_copy_layout", {"site": "test", "source_post_id": ids["page"], "target_post_id": target["id"], "replace_popup_ids": {str(ids["popup1"]): 999999}}))
    assert "999999" in bad
    prev = ok(call(client, access, "elementor_copy_layout", {"site": "test", "source_post_id": ids["page"], "target_post_id": target["id"], "replace_popup_ids": {str(ids["popup1"]): popup["id"]}}))
    assert prev["confirmed"] is False and prev["preview"]["elements_after"] == 5 and any("Vorlage" in n for n in prev["notes"])
    done = ok(call(client, access, "elementor_copy_layout", {"site": "test", "source_post_id": ids["page"], "target_post_id": target["id"], "replace_popup_ids": {str(ids["popup1"]): popup["id"]}, "confirm": True}))
    assert done["verify"]["equal"] is True and done["verify"]["page_settings"] is True and done["backup_id"]
    assert done["cache"]["elementor_css"][str(target["id"])]["status"] == "file"

    icon = [n for n in walk(tree(client, access, target["id"])) if n.get("widgetType") == "icon-box"][0]
    assert icon["popups"] == [popup["id"]]
    original_icon = [n for n in walk(tree(client, access, ids["page"])) if n.get("widgetType") == "icon-box"][0]
    assert original_icon["popups"] == [ids["popup1"]]  # the source keeps its popup
    used = ok(call(client, access, "elementor_references", {"site": "test", "post_id": popup["id"]}))["used_in"]
    assert [(u["post_id"], u["kind"]) for u in used] == [(target["id"], "popup_link")]
    assert ok(call(client, access, "post_get", {"site": "test", "id": target["id"]}))["template"] == "elementor_header_footer"

    html = page_html(target["link"])
    assert "Willkommen bei Kunde" in html and "Beratung" in html


def test_elementor_replace_text_expected_count_and_exact_rollback(wp):
    client, access = wp
    ids = fixtures(client, access)
    page = ok(call(client, access, "post_duplicate", {"site": "test", "id": ids["page"], "title": "Ersetzen Test", "status": "publish", "confirm": True}))["post"]
    before = tree(client, access, page["id"])

    found = ok(call(client, access, "elementor_find", {"site": "test", "post_id": page["id"], "search": "Alter Satz."}))
    assert found["count"] == 2 and {h["field"] for h in found["hits"]} == {"editor", "description_text"}
    wrong = err(call(client, access, "elementor_replace_text", {"site": "test", "post_id": page["id"], "search": "Alter Satz.", "replace": "x", "expected_count": 3, "confirm": True}))
    assert "gefunden 2" in wrong and "Fundstellen" in wrong
    assert tree(client, access, page["id"]) == before  # nothing changed

    new = 'Neuer "Satz" \\ mit ü.'
    prev = ok(call(client, access, "elementor_replace_text", {"site": "test", "post_id": page["id"], "search": "Alter Satz.", "replace": new, "expected_count": 2}))
    assert prev["confirmed"] is False and prev["preview"]["total"] == 2
    done = ok(call(client, access, "elementor_replace_text", {"site": "test", "post_id": page["id"], "search": "Alter Satz.", "replace": new, "expected_count": 2, "confirm": True}))
    assert done["total"] == 2 and done["results"][0]["verify"]["equal"] is True and len(done["backup_ids"]) == 1
    assert ok(call(client, access, "elementor_find", {"site": "test", "post_id": page["id"], "search": new, "case_sensitive": True}))["count"] == 2
    assert "Neuer &quot;Satz&quot;" in page_html(page["link"]) or 'Neuer "Satz"' in page_html(page["link"])

    rb = ok(call(client, access, "post_rollback", {"site": "test", "id": page["id"], "backup_id": done["backup_ids"][0], "confirm": True}))
    assert rb["verify"]["elementor_exact"] is True
    assert tree(client, access, page["id"]) == before


def test_elementor_element_operations(wp):
    client, access = wp
    ids = fixtures(client, access)
    page = ok(call(client, access, "post_duplicate", {"site": "test", "id": ids["page"], "title": "Elemente Test", "confirm": True}))["post"]
    nodes = tree(client, access, page["id"])
    container = nodes[0]["id"]
    heading = [n for n in walk(nodes) if n.get("widgetType") == "heading"][0]["id"]

    prev = ok(call(client, access, "elementor_update_element", {"site": "test", "post_id": page["id"], "element_id": heading, "settings": {"title": "Neu", "header_size": "h1"}}))
    assert prev["preview"]["changes"]["title"] == {"old": "Willkommen bei Kunde", "new": "Neu"}
    ok(call(client, access, "elementor_update_element", {"site": "test", "post_id": page["id"], "element_id": heading, "settings": {"title": "Neu", "header_size": "h1"}, "confirm": True}))
    assert [n for n in walk(tree(client, access, page["id"])) if n["id"] == heading][0]["settings"]["header_size"] == "h1"

    ins = ok(call(client, access, "elementor_insert_element", {"site": "test", "post_id": page["id"], "parent_id": container, "index": 0, "element": {"elType": "widget", "widgetType": "heading", "settings": {"title": "Ganz oben"}}, "confirm": True}))
    assert tree(client, access, page["id"])[0]["elements"][0]["id"] == ins["element_id"]
    copied = ok(call(client, access, "elementor_insert_element", {"site": "test", "post_id": page["id"], "source_post_id": ids["popup2"], "source_element_id": "a2000001", "confirm": True}))
    assert copied["element_id"] != "a2000001" and len(tree(client, access, page["id"])) == 2
    assert "nicht registriert" in err(call(client, access, "elementor_insert_element", {"site": "test", "post_id": page["id"], "parent_id": container, "element": {"elType": "widget", "widgetType": "gibtsnicht"}, "confirm": True}))

    ok(call(client, access, "elementor_move_element", {"site": "test", "post_id": page["id"], "element_id": ins["element_id"], "parent_id": copied["element_id"], "index": 1, "confirm": True}))
    assert tree(client, access, page["id"])[1]["elements"][1]["id"] == ins["element_id"]
    assert "sich selbst" in err(call(client, access, "elementor_move_element", {"site": "test", "post_id": page["id"], "element_id": container, "parent_id": heading}))

    ok(call(client, access, "elementor_remove_element", {"site": "test", "post_id": page["id"], "element_id": copied["element_id"], "confirm": True}))
    assert len(tree(client, access, page["id"])) == 1

    ps = ok(call(client, access, "elementor_page_settings_update", {"site": "test", "post_id": page["id"], "settings": {"hide_title": None, "padding": {"unit": "px", "top": "5"}}, "confirm": True}))
    assert ps["verify"]["page_settings"] is True and "hide_title" not in ps["page_settings"]
    assert "Pro" in err(call(client, access, "elementor_set_conditions", {"site": "test", "post_id": ids["popup1"], "conditions": ["include/general"]}))

    # Booleans of read-only tools travel as query strings ("false") and must still count as false.
    summary = ok(call(client, access, "elementor_get", {"site": "test", "post_id": ids["page"], "full": False}))["elements"]
    assert "settings" not in summary[0] and "content" in summary[0]["elements"][0]
    assert ok(call(client, access, "elementor_find", {"site": "test", "post_id": ids["page"], "search": "alter satz.", "case_sensitive": False}))["count"] == 2
    assert ok(call(client, access, "elementor_find", {"site": "test", "post_id": ids["page"], "search": "alter satz.", "case_sensitive": True}))["count"] == 0

    templates = ok(call(client, access, "elementor_template_list", {"site": "test", "template_type": "popup"}))["templates"]
    assert {"Popup Eins", "Popup Zwei"} <= {t["title"] for t in templates}
    info = ok(call(client, access, "elementor_info", {"site": "test"}))
    assert info["elementor"] and "service" in info["post_types"] and info["breakpoints"]


def test_custom_post_type_service(wp):
    client, access = wp
    types = {t["name"]: t for t in ok(call(client, access, "post_type_list", {"site": "test"}))["post_types"]}
    assert types["service"]["rewrite_slug"] == "service" and types["service"]["elementor"] is True
    assert types["elementor_library"]["elementor"] is True
    post = ok(call(client, access, "post_create", {"site": "test", "type": "service", "title": "Neue Leistung", "status": "publish", "confirm": True}))["post"]
    assert post["type"] == "service" and "service" in post["link"]
    assert any(p["id"] == post["id"] for p in ok(call(client, access, "post_list", {"site": "test", "type": "service"}))["posts"])
    upd = ok(call(client, access, "post_update", {"site": "test", "id": post["id"], "title": "Leistung umbenannt", "confirm": True}))
    assert upd["post"]["title"] == "Leistung umbenannt" and upd["backup_id"]
    ok(call(client, access, "post_trash", {"site": "test", "id": post["id"], "confirm": True}))


def test_security_rules(wp):
    client, access = wp
    # Editors: content yes, administration no.
    for tool, args in (("plugin_list", {}), ("option_get", {}), ("theme_list", {}), ("user_list", {}), ("core_update_check", {}), ("plugin_install", {"slug": "hello-dolly"})):
        assert "Berechtigung" in err(call(client, access, tool, {"site": "test", **args})), tool
    assert "Berechtigung" in err(call(client, access, "user_update", {"site": "test", "user_id": 1, "display_name": "x"}))
    # Administrators: whitelist and hard rules still apply.
    assert "nicht freigegeben" in err(call(client, access, "option_update", {"site": "admin", "values": {"siteurl": "https://kunde.example"}}))
    assert "nicht freigegeben" in err(call(client, access, "option_get", {"site": "admin", "names": ["admin_email"]}))
    assert "nicht deaktivieren" in err(call(client, access, "plugin_deactivate", {"site": "admin", "plugin": "tabside-mcp", "confirm": True}))
    me = [u for u in ok(call(client, access, "user_list", {"site": "admin", "role": "administrator"}))["users"] if u["login"] == "admin"][0]
    assert "eigene Rolle" in err(call(client, access, "user_update", {"site": "admin", "user_id": me["id"], "role": "editor", "confirm": True}))
    assert ok(call(client, access, "application_password_list", {"site": "admin"}))["application_passwords"][0]["name"] == "gateway"


def test_admin_settings_menus_css_widgets_redirects(wp):
    client, access = wp
    a = {"site": "admin"}
    # Options with backup and rollback
    upd = ok(call(client, access, "option_update", {**a, "values": {"blogname": "Neuer Name", "posts_per_page": 7}, "confirm": True}))
    assert upd["verify"] == {"blogname": True, "posts_per_page": True}
    assert ok(call(client, access, "option_get", {**a, "names": ["blogname"]}))["values"]["blogname"] == "Neuer Name"
    rb = ok(call(client, access, "option_rollback", {**a, "backup_id": upd["backup_id"], "confirm": True}))
    assert rb["values"]["blogname"] == "Testseite"

    # Customizer CSS
    css = ok(call(client, access, "custom_css_update", {**a, "css": "body{color:#1B4D46}", "confirm": True}))
    assert css["verify"]["css"] is True and css["diff"]["added"] == ["body{color:#1B4D46}"]
    assert ok(call(client, access, "custom_css_get", a))["css"] == "body{color:#1B4D46}"
    ok(call(client, access, "custom_css_rollback", {**a, "backup_id": css["backup_id"], "confirm": True}))
    assert ok(call(client, access, "custom_css_get", a))["css"] == ""

    # Widgets (classic sidebar of the test mu-plugin)
    sidebar = [s for s in ok(call(client, access, "widget_list", a))["sidebars"] if s["id"] == "test-sidebar"][0]
    widget = sidebar["widgets"][0]
    w = ok(call(client, access, "widget_update", {**a, "widget_id": widget["id"], "settings": {"text": "Neuer Hinweistext"}, "confirm": True}))
    assert w["verify"]["settings"] is True and w["widget"]["settings"]["text"] == "Neuer Hinweistext"
    ok(call(client, access, "widget_rollback", {**a, "backup_id": w["backup_id"], "confirm": True}))
    assert [s for s in ok(call(client, access, "widget_list", a))["sidebars"] if s["id"] == "test-sidebar"][0]["widgets"][0]["settings"]["text"] == "Alter Hinweistext"

    # Redirects (Redirection)
    r = ok(call(client, access, "redirect_create", {**a, "source": "/alt-test/", "target": "/neu-test/", "confirm": True}))["redirect"]
    assert r["enabled"] is True and r["code"] == 301
    off = ok(call(client, access, "redirect_update", {**a, "redirect_id": r["id"], "enabled": False, "confirm": True}))["redirect"]
    assert off["enabled"] is False
    assert any(x["id"] == r["id"] for x in ok(call(client, access, "redirect_list", {**a, "search": "alt-test"}))["redirects"])


def test_admin_menus(wp):
    client, access = wp
    a = {"site": "admin"}
    page = by_title(client, access, "admin", "page", "Vorlage Leistung")
    menus = ok(call(client, access, "menu_list", a))
    assert {"location": "primary", "label": "Hauptmenü", "menu_id": 0} in menus["locations"]
    menu = [m for m in menus["menus"] if m["name"] == "Testmenü"]
    assert menu, "Testmenü fehlt (setup-wordpress.sh)"
    menu_id = menu[0]["id"]
    # Start from an empty menu, also when the test runs again on the same site.
    for item in ok(call(client, access, "menu_get", {**a, "menu_id": menu_id}))["items"]:
        ok(call(client, access, "menu_item_remove", {**a, "item_id": item["id"], "confirm": True}))
    for item in ok(call(client, access, "menu_get", {**a, "menu_id": menu_id}))["items"]:
        ok(call(client, access, "menu_item_remove", {**a, "item_id": item["id"], "confirm": True}))

    first = ok(call(client, access, "menu_item_create", {**a, "menu_id": menu_id, "type": "post_type", "object_id": page["id"], "confirm": True}))
    second = ok(call(client, access, "menu_item_create", {**a, "menu_id": menu_id, "type": "custom", "title": "Extern", "url": "https://kunde.example/", "target": "_blank", "confirm": True}))
    assert [i["title"] for i in second["items"]] == ["Vorlage Leistung", "Extern"]
    ok(call(client, access, "menu_item_move", {**a, "item_id": second["item"]["id"], "parent_id": first["item"]["id"], "position": 2, "confirm": True}))
    tree_ = ok(call(client, access, "menu_get", {**a, "menu_id": menu_id}))["items"]
    assert tree_[0]["children"][0]["title"] == "Extern"
    removed = ok(call(client, access, "menu_item_remove", {**a, "item_id": first["item"]["id"], "confirm": True}))
    assert [i["title"] for i in removed["items"]] == ["Extern"]  # child moved up
    restored = ok(call(client, access, "menu_rollback", {**a, "backup_id": removed["backup_id"], "confirm": True}))
    assert restored["items"][0]["title"] == "Vorlage Leistung" and restored["items"][0]["children"][0]["title"] == "Extern"

    loc = ok(call(client, access, "menu_locations_set", {**a, "locations": {"primary": menu_id}, "confirm": True}))
    assert loc["verify"]["locations"] is True
    ok(call(client, access, "menu_rollback", {**a, "backup_id": loc["backup_id"], "confirm": True}))
    assert {"location": "primary", "label": "Hauptmenü", "menu_id": 0} in ok(call(client, access, "menu_list", a))["locations"]


def test_admin_plugins_health_audit(wp):
    client, access = wp
    a = {"site": "admin"}
    plugins = {p["plugin"]: p for p in ok(call(client, access, "plugin_list", a))["plugins"]}
    assert plugins["tabside-mcp/tabside-mcp.php"]["active"] and plugins["elementor/elementor.php"]["active"]
    prev = ok(call(client, access, "plugin_deactivate", {**a, "plugin": "redirection"}))
    assert prev["confirmed"] is False
    off = ok(call(client, access, "plugin_deactivate", {**a, "plugin": "redirection", "confirm": True}))
    assert off["plugin"]["active"] is False
    on = ok(call(client, access, "plugin_activate", {**a, "plugin": "redirection/redirection.php", "confirm": True}))
    assert on["plugin"]["active"] is True
    install = ok(call(client, access, "plugin_install", {**a, "slug": "hello-dolly"}))
    assert install["confirmed"] is False and install["preview"]["name"] == "Hello Dolly"
    assert "nicht gefunden" in err(call(client, access, "plugin_install", {**a, "slug": "gibt-es-sicher-nicht-tabside-xyz"}))

    themes = ok(call(client, access, "theme_list", a))["themes"]
    assert sum(t["active"] for t in themes) == 1
    other = [t for t in themes if not t["active"]][0]
    prev = ok(call(client, access, "theme_activate", {**a, "theme": other["theme"]}))
    assert prev["confirmed"] is False and "ganze Seite" in prev["notes"][0]

    health = ok(call(client, access, "site_health", a))
    assert health["php"] and health["tests"] and set(health["summary"]) <= {"good", "recommended", "critical"}
    core = ok(call(client, access, "core_update_check", a))
    assert core["wordpress"]
    flushed = ok(call(client, access, "cache_flush", {**a, "confirm": True}))["cache"]
    assert flushed["scope"] == "site" and "object_cache" in flushed["flushed"]

    log = ok(call(client, access, "audit_log", {**a, "limit": 500}))["entries"]
    abilities = {e["ability"] for e in log}
    assert {"plugin-deactivate", "plugin-activate", "cache-flush"} <= abilities
    assert all("abcd" not in str(e) for e in log)
    own = ok(call(client, access, "audit_log", {"site": "test", "limit": 500}))["entries"]
    assert own and all(e["user"] == "claude-mcp" for e in own)  # editors only see their own entries
