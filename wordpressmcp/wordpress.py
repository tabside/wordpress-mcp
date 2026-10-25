"""MCP client for the tabside-mcp plugin (WordPress MCP Adapter, HTTP transport).

Protocol revision 2025-11-25 with the adapter's session lifecycle: initialize
returns an Mcp-Session-Id, every later request carries it. Sessions are cached
per site and re-created once when the site no longer knows them.

Authentication: HTTP Basic with the site's user and Application Password.
Neither is ever logged or returned to the client.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from . import __version__
from .config import SiteConfig

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2025-11-25"
TOOL_PREFIX = "tabside-"


class WordPressError(Exception):
    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


class _SessionExpired(Exception):
    pass


def tool_name(name: str) -> str:
    """post_list -> tabside-post-list (ability tabside/post-list)."""
    return TOOL_PREFIX + name.replace("_", "-")


class SiteClient:
    def __init__(self, site: SiteConfig, *, timeout: float, transport: httpx.AsyncBaseTransport | None = None):
        self.site = site
        self._timeout = timeout
        self._transport = transport
        self._session_id: str | None = None
        self._lock = asyncio.Lock()
        self._next_id = 1

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self._timeout,
            transport=self._transport,
            follow_redirects=False,
            auth=httpx.BasicAuth(self.site.username, self.site.app_password),
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "User-Agent": f"wordpress-mcp-gateway/{__version__}",
            },
        )

    def _id(self) -> int:
        self._next_id += 1
        return self._next_id

    async def _post(self, client: httpx.AsyncClient, payload: dict[str, Any], session_id: str | None) -> httpx.Response:
        headers = {}
        if session_id:
            headers["Mcp-Session-Id"] = session_id
            headers["MCP-Protocol-Version"] = PROTOCOL_VERSION
        try:
            return await client.post(self.site.endpoint, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise WordPressError(f"{self.site.label} antwortet nicht (Timeout).", status=504) from exc
        except httpx.HTTPError as exc:
            raise WordPressError(f"{self.site.label} ist nicht erreichbar ({exc.__class__.__name__}).", status=502) from exc

    def _check_http(self, response: httpx.Response) -> None:
        status = response.status_code
        if status in (401, 403):
            logger.warning("site %s rejected the login (HTTP %s)", self.site.id, status)
            raise WordPressError(
                f"{self.site.label} lehnt die Anmeldung ab (HTTP {status}). Benutzer, Anwendungspasswort und Plugin tabside-mcp prüfen.",
                status=status,
            )
        if status in (301, 302, 307, 308):
            raise WordPressError(f"{self.site.label} leitet den MCP-Endpunkt um (HTTP {status}). WP_SITE_..._URL bzw. _ENDPOINT prüfen.", status=status)
        if status == 404 and "rest_no_route" in response.text:
            raise WordPressError(
                f"MCP-Endpunkt auf {self.site.label} nicht gefunden. Sind die Plugins MCP Adapter und tabside-mcp aktiv?", status=404
            )

    @staticmethod
    def _body(response: httpx.Response) -> dict[str, Any] | None:
        if not response.content:
            return None
        ctype = response.headers.get("content-type", "")
        text = response.text
        if "text/event-stream" in ctype:
            data_lines = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
            text = data_lines[-1] if data_lines else ""
        try:
            data = json.loads(text)
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    async def _initialize(self, client: httpx.AsyncClient) -> str:
        response = await self._post(
            client,
            {
                "jsonrpc": "2.0",
                "id": self._id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "wordpress-mcp-gateway", "version": __version__},
                },
            },
            None,
        )
        self._check_http(response)
        body = self._body(response)
        session_id = response.headers.get("mcp-session-id")
        if response.status_code != 200 or body is None or "result" not in body or not session_id:
            logger.warning("initialize on site %s failed: HTTP %s", self.site.id, response.status_code)
            raise WordPressError(f"MCP-Initialisierung auf {self.site.label} fehlgeschlagen (HTTP {response.status_code}).", status=502)
        await self._post(client, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)
        return session_id

    async def _call_once(self, client: httpx.AsyncClient, session_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        response = await self._post(
            client,
            {"jsonrpc": "2.0", "id": self._id(), "method": "tools/call", "params": {"name": tool_name(name), "arguments": arguments}},
            session_id,
        )
        self._check_http(response)
        body = self._body(response)
        if response.status_code == 404 or (response.status_code == 400 and body and "session" in json.dumps(body.get("error") or {}).lower()):
            raise _SessionExpired()
        if body is None:
            raise WordPressError(f"Unerwartete Antwort von {self.site.label} (HTTP {response.status_code}).", status=502)
        if "error" in body:
            message = str((body.get("error") or {}).get("message") or "")
            if "session" in message.lower():
                raise _SessionExpired()
            logger.warning("tools/call %s on site %s: JSON-RPC error %s", name, self.site.id, (body.get("error") or {}).get("code"))
            raise WordPressError(f"{self.site.label}: {message[:500] or 'Fehler'}", status=response.status_code)
        result = body.get("result") or {}
        if result.get("isError"):
            raise WordPressError(f"{self.site.label}: {_result_text(result)[:1000] or 'Fehler'}", status=422)
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        text = _result_text(result)
        try:
            parsed = json.loads(text)
        except ValueError:
            return {"result": text}
        return parsed if isinstance(parsed, dict) else {"result": parsed}

    async def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = {k: v for k, v in (arguments or {}).items() if v is not None}
        async with self._client() as client:
            for attempt in (1, 2):
                async with self._lock:
                    if self._session_id is None:
                        self._session_id = await self._initialize(client)
                    session_id = self._session_id
                try:
                    return await self._call_once(client, session_id, name, arguments)
                except _SessionExpired:
                    async with self._lock:
                        if self._session_id == session_id:
                            self._session_id = None
                    if attempt == 2:
                        raise WordPressError(f"MCP-Sitzung auf {self.site.label} konnte nicht aufgebaut werden.", status=502)
        raise AssertionError("unreachable")


def _result_text(result: dict[str, Any]) -> str:
    parts = [c.get("text", "") for c in result.get("content") or [] if isinstance(c, dict) and c.get("type") == "text"]
    return "\n".join(p for p in parts if p)


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
