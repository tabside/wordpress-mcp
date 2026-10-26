"""Client for the tabside-mcp abilities over the WordPress core REST API (6.9+):

    GET|POST <rest_url>/wp-abilities/v1/abilities/tabside/<name>/run

Read-only abilities require GET with the input as query parameters
(input[key]=value), all others POST with {"input": {...}}. No MCP Adapter is
needed on the site.

Authentication: HTTP Basic with the site's user and Application Password.
Neither is ever logged or returned to the client.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from . import __version__
from .config import SiteConfig

logger = logging.getLogger(__name__)

ABILITY_PREFIX = "tabside/"
# Abilities annotated readonly: the core endpoint only accepts GET for them.
READ_ONLY = {"get_version", "post_list", "post_get", "category_list", "tag_list", "media_list"}
LOGIN_ERRORS = {"incorrect_password", "invalid_username", "invalid_email", "application_passwords_disabled", "rest_not_logged_in"}


class WordPressError(Exception):
    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


def ability_name(name: str) -> str:
    """post_list -> tabside/post-list."""
    return ABILITY_PREFIX + name.replace("_", "-")


def run_url(rest_url: str, name: str) -> str:
    # Also works for plain permalinks: rest_url https://example.com/?rest_route=
    return rest_url.rstrip("/") + f"/wp-abilities/v1/abilities/{ability_name(name)}/run"


def query_params(value: Any, prefix: str = "input") -> list[tuple[str, str]]:
    """{"limit": 5, "tags": ["a"]} -> input[limit]=5, input[tags][]=a (PHP array syntax)."""
    out: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            out.extend(query_params(item, f"{prefix}[{key}]"))
    elif isinstance(value, (list, tuple)):
        for item in value:
            out.extend(query_params(item, f"{prefix}[]"))
    elif isinstance(value, bool):
        out.append((prefix, "true" if value else "false"))
    elif value is not None:
        out.append((prefix, str(value)))
    return out


class SiteClient:
    def __init__(self, site: SiteConfig, *, timeout: float, transport: httpx.AsyncBaseTransport | None = None):
        self.site = site
        self._timeout = timeout
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self._timeout,
            transport=self._transport,
            follow_redirects=False,
            trust_env=False,
            auth=httpx.BasicAuth(self.site.username, self.site.app_password),
            headers={"Accept": "application/json", "User-Agent": f"wordpress-mcp-gateway/{__version__}"},
        )

    async def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = {k: v for k, v in (arguments or {}).items() if v is not None}
        url = run_url(self.site.rest_url, name)
        label = self.site.label
        try:
            async with self._client() as client:
                if name in READ_ONLY:
                    # httpx replaces an existing query string (?rest_route=...) with params, so merge by hand.
                    parsed = httpx.URL(url)
                    params = list(parsed.params.multi_items()) + query_params(arguments)
                    response = await client.get(parsed.copy_with(query=None), params=params)
                else:
                    response = await client.post(url, json={"input": arguments})
        except httpx.TimeoutException as exc:
            raise WordPressError(f"{label} antwortet nicht (Timeout).", status=504) from exc
        except httpx.HTTPError as exc:
            raise WordPressError(f"{label} ist nicht erreichbar ({exc.__class__.__name__}).", status=502) from exc

        status = response.status_code
        try:
            body = response.json()
        except ValueError:
            body = None
        if status in (301, 302, 307, 308):
            raise WordPressError(f"{label} leitet die REST-API um (HTTP {status}). url bzw. rest_url der Seite prüfen.", status=status)
        if 200 <= status < 300 and isinstance(body, dict):
            return body
        if 200 <= status < 300:
            return {"result": body}

        code = body.get("code") if isinstance(body, dict) else None
        message = str(body.get("message") or "") if isinstance(body, dict) else ""
        logger.warning("site %s ability %s: HTTP %s %s", self.site.id, name, status, code)
        if code == "rest_no_route":
            raise WordPressError(f"{label}: REST-Endpunkt der Abilities nicht gefunden. Ist WordPress mindestens 6.9?", status=404)
        if code == "rest_ability_not_found":
            raise WordPressError(f"{label}: Plugin tabside-mcp ist nicht aktiv.", status=404)
        if code in LOGIN_ERRORS or (status == 401 and not (code or "").startswith("tabside_mcp")):
            raise WordPressError(f"{label} lehnt die Anmeldung ab (HTTP {status}). Benutzer und Anwendungspasswort prüfen.", status=status)
        if not isinstance(body, dict):
            raise WordPressError(f"Unerwartete Antwort von {label} (HTTP {status}).", status=502)
        # Plugin and validation errors: the message is meant for the user.
        message = message.replace("Ability \"" + ability_name(name) + "\" has invalid input. Reason: ", "Ungültige Eingabe: ")
        raise WordPressError(f"{label}: {message[:1000] or json.dumps(body)[:300]}", status=status)


class SitePool:
    def __init__(self, sites: dict[str, SiteConfig], *, timeout: float, transport: httpx.AsyncBaseTransport | None = None):
        self._clients = {site_id: SiteClient(site, timeout=timeout, transport=transport) for site_id, site in sites.items()}

    def get(self, site_id: str) -> SiteClient:
        client = self._clients.get((site_id or "").strip().lower())
        if client is None:
            known = ", ".join(sorted(self._clients)) or "keine"
            raise WordPressError(f"Unbekannte Seite {site_id!r}. Konfiguriert: {known} (siehe list_sites).", status=404)
        return client

    def all(self) -> list[SiteClient]:
        return list(self._clients.values())
