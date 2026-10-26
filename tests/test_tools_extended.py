"""Tools added in 1.1: all post types, Elementor, navigation/settings, administration.

Schemas, forwarding to the plugin abilities (GET for read-only, POST for writes),
error messages and the response size limit. WordPress itself is faked here;
tests/test_integration_wordpress.py runs the same tools against a real site.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pytest

from conftest import call
from wordpressmcp.wordpress import READ_ONLY

PLUGIN = Path(__file__).resolve().parent.parent / "plugin" / "tabside-mcp" / "includes"
GATEWAY_ONLY = {"list_sites", "docx_to_content"}


def tools(client, access) -> dict[str, dict]:
    r = client.post(
        "/mcp",
        headers={"Authorization": f"Bearer {access}", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    return {t["name"]: t for t in r.json()["result"]["tools"]}


def plugin_abilities() -> set[str]:
    """Ability slugs defined in the plugin's definitions() arrays."""
    names: set[str] = set()
    for path in PLUGIN.glob("class-tabside-mcp-*.php"):
        names |= set(re.findall(r"^\t{2,4}'([a-z]+(?:-[a-z]+)+|[a-z]+-[a-z]+)'\s*=>\s*array\(\s*\n\s*'label'", path.read_text(), re.M))
    return names


def test_every_plugin_ability_has_a_tool_and_the_right_method(gateway, access):
    client, _, _ = gateway
    listed = tools(client, access)
    abilities = {name.replace("-", "_") for name in plugin_abilities()}
    assert len(abilities) == 68
    assert abilities == set(listed) - GATEWAY_ONLY
    for name, tool in listed.items():
        if name in GATEWAY_ONLY:
            continue
        read_only = bool(tool["annotations"]["readOnlyHint"])
        assert read_only == (name in READ_ONLY), name


def test_object_parameters_are_described(gateway, access):
    client, _, _ = gateway
    for name, tool in tools(client, access).items():
        for prop, schema in tool["inputSchema"]["properties"].items():
            variants = schema.get("anyOf", [schema])
            if any(v.get("type") == "object" for v in variants):
                assert schema.get("description"), f"{name}.{prop} has no description"
            assert variants != [{}], f"{name}.{prop} has no type"


def test_write_tools_mention_preview(gateway, access):
    client, _, _ = gateway
    for name, tool in tools(client, access).items():
        if not tool["annotations"]["readOnlyHint"]:
            assert "confirm=true" in tool["description"], name


FORWARD = [
    ("post_type_list", {}, {}),
    ("post_list", {"type": "service", "meta_key": "_elementor_template_type", "meta_value": "popup", "parent": 0},
     {"type": "service", "meta_key": "_elementor_template_type", "meta_value": "popup", "parent": "0"}),
    ("term_list", {"taxonomy": "category"}, {"taxonomy": "category"}),
    ("term_create", {"taxonomy": "category", "name": "Neu"}, {"taxonomy": "category", "name": "Neu", "confirm": False}),
    ("term_delete", {"taxonomy": "category", "term_id": 4, "confirm": True}, {"taxonomy": "category", "term_id": 4, "confirm": True}),
    ("post_update", {"id": 5, "template": "elementor_canvas", "terms": {"genre": ["a", 2]}}, {"id": 5, "template": "elementor_canvas", "terms": {"genre": ["a", 2]}}),
    ("post_duplicate", {"id": 5, "conditions": []}, {"id": 5, "status": "draft", "conditions": [], "confirm": False}),
    ("elementor_info", {}, {}),
    ("elementor_get", {"post_id": 8, "full": True}, {"post_id": "8", "full": "true"}),
    ("elementor_find", {"search": "Alter Satz"}, {"search": "Alter Satz"}),
    ("elementor_replace_text", {"search": "a", "replace": "b", "expected_count": 2, "post_ids": [1, 2]},
     {"search": "a", "replace": "b", "expected_count": 2, "post_ids": [1, 2]}),
    ("elementor_update_element", {"post_id": 8, "element_id": "b1000002", "settings": {"title": "X", "header_size": None}},
     {"post_id": 8, "element_id": "b1000002", "settings": {"title": "X", "header_size": None}}),
    ("elementor_insert_element", {"post_id": 8, "element": {"elType": "widget", "widgetType": "heading"}, "index": 0},
     {"post_id": 8, "element": {"elType": "widget", "widgetType": "heading"}, "index": 0}),
    ("elementor_copy_layout", {"source_post_id": 8, "target_post_id": 9, "replace_popup_ids": {"5": 10}},
     {"source_post_id": 8, "target_post_id": 9, "replace_popup_ids": {"5": 10}, "copy_page_settings": True}),
    ("elementor_set_conditions", {"post_id": 5, "conditions": ["include/general"]}, {"post_id": 5, "conditions": ["include/general"]}),
    ("menu_get", {"menu_id": 3}, {"menu_id": "3"}),
    ("menu_item_create", {"menu_id": 3, "type": "custom", "url": "https://kunde.example/", "title": "X"},
     {"menu_id": 3, "type": "custom", "url": "https://kunde.example/", "title": "X"}),
    ("menu_locations_set", {"locations": {"primary": 3}}, {"locations": {"primary": 3}}),
    ("option_get", {"names": ["blogname"]}, {"names": ["blogname"]}),
    ("option_update", {"values": {"blogname": "Neu", "posts_per_page": 7}}, {"values": {"blogname": "Neu", "posts_per_page": 7}}),
    ("custom_css_update", {"css": "a{}"}, {"css": "a{}"}),
    ("widget_update", {"widget_id": "text-2", "settings": {"title": "X"}}, {"widget_id": "text-2", "settings": {"title": "X"}}),
    ("redirect_create", {"source": "/alt/", "target": "/neu/"}, {"source": "/alt/", "target": "/neu/", "code": 301, "regex": False}),
    ("plugin_list", {"refresh": True}, {"refresh": "true"}),
    ("plugin_install", {"slug": "redirection", "activate": True}, {"slug": "redirection", "activate": True}),
    ("plugin_deactivate", {"plugin": "redirection"}, {"plugin": "redirection"}),
    ("theme_activate", {"theme": "twentytwentyfive"}, {"theme": "twentytwentyfive"}),
    ("core_update_check", {}, {"refresh": "false"}),
    ("site_health", {}, {}),
    ("cache_flush", {"post_id": 8, "confirm": True}, {"post_id": 8, "confirm": True}),
    ("user_update", {"user_id": 3, "role": "author"}, {"user_id": 3, "role": "author"}),
    ("application_password_list", {}, {}),
    ("audit_log", {"limit": 5}, {"limit": "5"}),
]


@pytest.mark.parametrize("tool,args,expected", FORWARD, ids=[f[0] for f in FORWARD])
def test_forwarding(gateway, access, tool, args, expected):
    client, fake, _ = gateway
    res = call(client, access, tool, {"site": "kunde", **args})
    assert res.get("isError") is not True, res["content"][0]["text"]
    name, sent = fake.calls[-1]
    assert name == "tabside-" + tool.replace("_", "-")
    assert fake.requests[-1].method == ("GET" if tool in READ_ONLY else "POST")
    for key, value in expected.items():
        assert sent.get(key) == value, (key, sent)
    assert "site" not in sent and None not in sent.values()


def test_replace_text_mismatch_reports_hits(gateway, access):
    client, fake, _ = gateway
    hits = [{"post_id": 8, "element_id": "b1000003", "field": "editor", "occurrences": 1, "context": "… Alter Satz."}]
    fake.results["tabside-elementor-replace-text"] = (
        409,
        {"code": "tabside_mcp_count_mismatch", "message": "Erwartet 3 Treffer, gefunden 1. Nichts geändert.", "data": {"status": 409, "hits": hits}},
    )
    res = call(client, access, "elementor_replace_text", {"site": "kunde", "search": "Alter Satz.", "replace": "x", "expected_count": 3, "post_id": 8, "confirm": True})
    text = res["content"][0]["text"]
    assert res["isError"] is True and "gefunden 1" in text and "b1000003" in text and "Fundstellen" in text


def test_missing_abilities_explain_why(gateway, access):
    client, fake, _ = gateway
    fake.missing |= {"elementor-get", "redirect-list", "plugin-list", "post-get"}
    assert "Elementor ist auf dieser Seite nicht aktiv" in call(client, access, "elementor_get", {"site": "kunde", "post_id": 1})["content"][0]["text"]
    assert "Redirection" in call(client, access, "redirect_list", {"site": "kunde"})["content"][0]["text"]
    assert "älter als 2.0" in call(client, access, "plugin_list", {"site": "kunde"})["content"][0]["text"]
    assert "Plugin tabside-mcp ist nicht aktiv" in call(client, access, "post_get", {"site": "kunde", "id": 1})["content"][0]["text"]


def test_list_sites_check_reports_elementor_and_admin_tools(gateway, access):
    client, fake, _ = gateway
    fake.results["tabside-get-version"] = {"version": "2.0.0", "wordpress": "6.9", "elementor": "4.3.5", "elementor_pro": None, "admin_tools": "enabled"}
    site = call(client, access, "list_sites", {"check": True})["structuredContent"]["sites"][0]
    assert site["elementor_version"] == "4.3.5" and site["admin_tools"] == "enabled" and site["elementor_pro_version"] is None


def test_response_size_limit(gateway, access):
    client, fake, services = gateway
    fake.results["tabside-elementor-get"] = {"elements": [{"id": "a", "settings": {"html": "x" * (services.settings.max_response_chars + 10)}}]}
    res = call(client, access, "elementor_get", {"site": "kunde", "post_id": 8, "full": True})
    assert res["isError"] is True and "zu gross" in res["content"][0]["text"] and "element_id" in res["content"][0]["text"]


def test_audit_log_of_multi_page_write(gateway, access, caplog):
    client, fake, _ = gateway
    caplog.set_level(logging.INFO, logger="wordpressmcp.audit")
    fake.results["tabside-elementor-replace-text"] = {"confirmed": True, "total": 2, "backup_ids": ["b1", "b2"], "affected_posts": [8, 9]}
    call(client, access, "elementor_replace_text", {"site": "kunde", "search": "a", "replace": "b", "expected_count": 2, "post_ids": [8, 9], "confirm": True})
    event = [json.loads(r.message) for r in caplog.records if r.name == "wordpressmcp.audit" and '"tool_write"' in r.message][-1]
    assert event["tool"] == "elementor_replace_text" and event["affected_posts"] == [8, 9] and event["backup_ids"] == ["b1", "b2"]
    assert event["executed"] is True and event["user"] == "kim"


def test_read_scope_cannot_use_admin_writes(gateway):
    from conftest import connect, token

    client, fake, _ = gateway
    r, cid, ver, _ = connect(client, scope="wordpress:read")
    access = token(client, cid, ver, r)["access_token"]
    assert call(client, access, "plugin_list", {"site": "kunde"}).get("isError") is not True
    res = call(client, access, "plugin_install", {"site": "kunde", "slug": "redirection", "confirm": True})
    assert res["isError"] is True and "wordpress:write" in res["content"][0]["text"]
    assert not [c for c in fake.calls if c[0] == "tabside-plugin-install"]
