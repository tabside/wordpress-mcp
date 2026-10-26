"""MCP tools of the gateway. Each site tool forwards to the tabside-mcp plugin of
the chosen site; the plugin enforces confirm=true for every write and backs up
the old content before updates. The gateway adds login, scopes, rate limits,
the audit log of writes and the Word conversion.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from . import GIT_SHA, __version__
from .config import Settings
from .docx_convert import DocxError, docx_to_content as convert_docx
from .fetch import FetchError, fetch_url
from .limits import MemoryLimiter, RateLimited, audit
from .wordpress import SitePool, WordPressError

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
TRASH = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)

READ = "wordpress:read"
WRITE_SCOPE = "wordpress:write"

PostType = Annotated[str, Field(description="Beitragstyp aus post_type_list, z.B. post, page, elementor_library oder ein eigener Typ wie service.")]
Status = Literal["draft", "pending", "publish", "future", "private"]
TermList = list[int | str]
TermMap = Annotated[
    dict[str, list[int | str]] | None,
    Field(description='Begriffe weiterer Taxonomien: {"taxonomie": [ID, Slug oder Name]}. Müssen existieren (term_create). Ersetzt die bisherigen dieser Taxonomie.'),
]

SITE_DOC = "Seite aus list_sites (id)."
CONFIRM_DOC = " Ohne confirm=true wird nichts geändert, es kommt nur eine Vorschau. confirm=true erst setzen, wenn der Benutzer die Vorschau bestätigt hat."
ADMIN_DOC = " Admin-Tool: Vorschau zuerst dem Benutzer zeigen und nur nach ausdrücklicher Bestätigung mit confirm=true ausführen."


@dataclass
class Ctx:
    user: str
    client_id: str


class ToolRunner:
    def __init__(self, settings: Settings, pool: SitePool, limiter: MemoryLimiter, *, fetch_options: dict[str, Any] | None = None):
        self.settings = settings
        self.pool = pool
        self._limiter = limiter
        self._fetch_options = fetch_options or {}

    def context(self, need_scope: str) -> Ctx:
        token = get_access_token()
        if token is None:
            raise ToolError("Nicht angemeldet.")
        user = getattr(token, "user_id", None) or token.subject
        if not user or user not in self.settings.users:
            raise ToolError("Nicht angemeldet.")
        if need_scope not in token.scopes:
            raise ToolError(f"Für diese Aktion fehlt die Berechtigung {need_scope}. Bitte die Verbindung mit diesem Recht neu herstellen.")
        try:
            self._limiter.check_tool_call(user)
        except RateLimited as exc:
            raise ToolError(f"Zu viele Aufrufe, bitte in {exc.retry_after} Sekunden erneut versuchen.")
        return Ctx(user=user, client_id=token.client_id)

    async def read(self, site: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        self.context(READ)
        try:
            result = await self.pool.get(site).call(tool, args)
        except WordPressError as exc:
            raise ToolError(exc.message)
        return self._limited({"site": site, **result})

    def _limited(self, result: dict[str, Any]) -> dict[str, Any]:
        """Never hand a response to the client that is larger than the configured limit."""
        size = len(json.dumps(result, ensure_ascii=False))
        limit = self.settings.max_response_chars
        if size > limit:
            raise ToolError(
                f"Antwort zu gross ({size // 1024} KB, erlaubt {limit // 1024} KB). Bitte eingrenzen, "
                "z.B. mit element_id, full=false, limit, page oder search."
            )
        return result

    def site(self, site: str) -> None:
        try:
            self.pool.get(site)
        except WordPressError as exc:
            raise ToolError(exc.message)

    async def write(self, site: str, tool: str, args: dict[str, Any], ctx: Ctx | None = None) -> dict[str, Any]:
        ctx = ctx or self.context(WRITE_SCOPE)
        confirmed = bool(args.get("confirm"))
        log: dict[str, Any] = {"site": site, "tool": tool, "confirm": confirmed, "user": ctx.user, "client": ctx.client_id}
        if args.get("id"):
            log["post_id"] = args["id"]
        try:
            result = await self.pool.get(site).call(tool, args)
        except WordPressError as exc:
            audit("tool_write", **log, ok=False, error_status=exc.status)
            if confirmed and exc.status in (502, 504):
                raise ToolError(exc.message + " Die Änderung kann trotzdem ausgeführt worden sein: vor einem neuen Versuch mit dem passenden Lese-Tool oder audit_log prüfen.")
            raise ToolError(exc.message)
        post = result.get("post") if isinstance(result.get("post"), dict) else None
        if post and post.get("id"):
            log["post_id"] = post["id"]
        for key in ("post_id", "target_post_id", "element_id", "plugin", "slug", "theme", "user_id", "menu_id", "item_id", "widget_id", "term_id", "redirect_id"):
            if args.get(key) and key not in log:
                log[key] = args[key]
        if isinstance(result.get("affected_posts"), list):
            log["affected_posts"] = result["affected_posts"]
        if isinstance(result.get("media"), dict):
            log["media_id"] = result["media"].get("id")
        for key in ("backup_id", "safety_backup_id", "backup_ids"):
            if result.get(key):
                log[key] = result[key]
        audit("tool_write", **log, ok=True, executed=bool(result.get("confirmed")))
        return self._limited({"site": site, **result})

    async def load_file(self, url: str | None, data_base64: str | None) -> tuple[bytes, str | None]:
        if bool(url) == bool(data_base64):
            raise ToolError("Genau eines von url oder data_base64 angeben.")
        limit = self.settings.max_file_bytes
        if url:
            try:
                downloaded = await fetch_url(url, max_bytes=limit, **self._fetch_options)
            except FetchError as exc:
                raise ToolError(f"Download fehlgeschlagen: {exc}")
            return downloaded.data, downloaded.filename
        raw = data_base64 or ""
        if raw.startswith("data:") and "," in raw:
            raw = raw.split(",", 1)[1]
        raw = "".join(raw.split())
        if len(raw) * 3 // 4 > limit:
            raise ToolError(f"Datei ist grösser als {limit // 1048576} MB.")
        try:
            return base64.b64decode(raw, validate=True), None
        except (binascii.Error, ValueError):
            raise ToolError("data_base64 ist kein gültiges Base64.")


def _site_entry(site: Any) -> dict[str, Any]:
    return {"id": site.id, "label": site.label, "url": site.url, "rest_url": site.rest_url, "wordpress_user": site.username}


def register_tools(mcp: MCPServer, runner: ToolRunner, settings: Settings) -> None:
    @mcp.tool(
        description="Version und Commit des Gateways. Mit site zusätzlich Version und Commit des Plugins tabside-mcp, WordPress-, Elementor- und PHP-Version, erkannte Cache- und Weiterleitungs-Plugins und admin_tools dieser Seite.",
        annotations=READ_ONLY,
    )
    async def get_version(site: str | None = None) -> dict[str, Any]:
        runner.context(READ)
        out: dict[str, Any] = {"service": "wordpress-mcp", "version": __version__, "commit": GIT_SHA}
        if site:
            try:
                out["plugin"] = await runner.pool.get(site).call("get_version")
            except WordPressError as exc:
                raise ToolError(exc.message)
        return out

    @mcp.tool(
        description=(
            "Zeigt die konfigurierten WordPress-Seiten (id für den Parameter site, Name, URL). Mit check=true wird jede Seite angefragt: "
            "Plugin-, WordPress- und Elementor-Version, admin_tools (enabled = Plugins, Themes, Einstellungen, Benutzer verfügbar) bzw. der Fehler."
        ),
        annotations=READ_ONLY,
    )
    async def list_sites(check: bool = False) -> dict[str, Any]:
        runner.context(READ)
        entries = [_site_entry(client.site) for client in runner.pool.all()]
        if check:

            async def probe(entry: dict[str, Any]) -> None:
                try:
                    info = await runner.pool.get(entry["id"]).call("get_version")
                    entry["status"] = "ok"
                    entry["plugin_version"] = info.get("version")
                    entry["wordpress_version"] = info.get("wordpress")
                    entry["mcp_adapter_version"] = info.get("mcp_adapter")
                    entry["elementor_version"] = info.get("elementor")
                    entry["elementor_pro_version"] = info.get("elementor_pro")
                    entry["admin_tools"] = info.get("admin_tools")
                except WordPressError as exc:
                    entry["status"] = "error"
                    entry["error"] = exc.message

            await asyncio.gather(*(probe(e) for e in entries))
        return {"sites": entries}

    @mcp.tool(
        description="Alle Beitragstypen der Seite mit Verwaltungsoberfläche: Slug (für type), Bezeichnung, URL-Präfix (rewrite_slug), Taxonomien, ob Elementor ihn bearbeitet, Anzahl.",
        annotations=READ_ONLY,
    )
    async def post_type_list(site: str) -> dict[str, Any]:
        return await runner.read(site, "post_type_list", {})

    @mcp.tool(
        description=(
            "Listet Beiträge eines Beitragstyps (type aus post_type_list, z.B. post, page, elementor_library, service; any = alle), neueste zuerst. "
            "Filter: status (Standard any = alles ausser Papierkorb), search, category (ID oder Slug), parent, meta_key/meta_value "
            "(nur _elementor_edit_mode, _elementor_template_type, _wp_page_template; z.B. Popups: type=elementor_library, meta_key=_elementor_template_type, meta_value=popup). Max. 100 pro Seite."
        ),
        annotations=READ_ONLY,
    )
    async def post_list(
        site: str,
        type: str = "post",
        status: Literal["draft", "pending", "publish", "future", "private", "trash", "any"] = "any",
        search: str | None = None,
        category: int | str | None = None,
        parent: int | None = None,
        meta_key: Literal["_elementor_edit_mode", "_elementor_template_type", "_wp_page_template"] | None = None,
        meta_value: str | None = None,
        orderby: Literal["date", "modified", "title", "menu_order", "ID"] = "date",
        order: Literal["ASC", "DESC"] = "DESC",
        limit: int = 20,
        page: int = 1,
    ) -> dict[str, Any]:
        args = {
            "type": type, "status": status, "search": search, "category": category, "parent": parent, "meta_key": meta_key,
            "meta_value": meta_value, "orderby": orderby, "order": order, "limit": limit, "page": page,
        }
        return await runner.read(site, "post_list", args)

    @mcp.tool(
        description=(
            "Ein Beitrag beliebigen Typs: Inhalt (roh, HTML oder Blöcke), Datum, Status, Begriffe, Beitragsbild, Template, Eltern-Seite, Reihenfolge, "
            "Elementor-Angaben (elementor_info: Vorlagentyp, Bedingungen, Version), Zusatzfelder, Vorschau-Link und die Sicherungen (backups) für post_rollback. "
            "Den Elementor-Aufbau liefert elementor_get."
        ),
        annotations=READ_ONLY,
    )
    async def post_get(site: str, id: int) -> dict[str, Any]:
        return await runner.read(site, "post_get", {"id": id})

    @mcp.tool(description="Kategorien der Seite mit ID, Name, Slug, Eltern-ID und Anzahl Beiträge.", annotations=READ_ONLY)
    async def category_list(site: str, search: str | None = None, limit: int = 100) -> dict[str, Any]:
        return await runner.read(site, "category_list", {"search": search, "limit": limit})

    @mcp.tool(description="Schlagwörter der Seite mit ID, Name, Slug und Anzahl Beiträge.", annotations=READ_ONLY)
    async def tag_list(site: str, search: str | None = None, limit: int = 100) -> dict[str, Any]:
        return await runner.read(site, "tag_list", {"search": search, "limit": limit})

    @mcp.tool(
        description="Begriffe einer beliebigen Taxonomie (category, post_tag oder eigene) mit ID, Name, Slug, Beschreibung, Eltern-ID und Anzahl. Ohne taxonomy: Liste der Taxonomien.",
        annotations=READ_ONLY,
    )
    async def term_list(site: str, taxonomy: str | None = None, search: str | None = None, parent: int | None = None, limit: int = 100, page: int = 1) -> dict[str, Any]:
        return await runner.read(site, "term_list", {"taxonomy": taxonomy, "search": search, "parent": parent, "limit": limit, "page": page})

    @mcp.tool(description="Legt einen Begriff in einer Taxonomie an (Kategorie, Schlagwort oder eigene)." + CONFIRM_DOC, annotations=WRITE)
    async def term_create(
        site: str, taxonomy: str, name: str, slug: str | None = None, description: str | None = None, parent: int | None = None, confirm: bool = False
    ) -> dict[str, Any]:
        return await runner.write(site, "term_create", {"taxonomy": taxonomy, "name": name, "slug": slug, "description": description, "parent": parent, "confirm": confirm})

    @mcp.tool(description="Ändert Name, Slug, Beschreibung oder Eltern-Begriff eines Begriffs. Alter Stand wird gesichert." + CONFIRM_DOC, annotations=WRITE)
    async def term_update(
        site: str,
        taxonomy: str,
        term_id: int,
        name: str | None = None,
        slug: str | None = None,
        description: str | None = None,
        parent: int | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        args = {"taxonomy": taxonomy, "term_id": term_id, "name": name, "slug": slug, "description": description, "parent": parent, "confirm": confirm}
        return await runner.write(site, "term_update", args)

    @mcp.tool(
        description="Löscht einen Begriff, aber nur, wenn ihm keine Beiträge zugeordnet sind. Name, Slug, Beschreibung und Zusatzfelder werden vorher gesichert." + CONFIRM_DOC,
        annotations=TRASH,
    )
    async def term_delete(site: str, taxonomy: str, term_id: int, confirm: bool = False) -> dict[str, Any]:
        return await runner.write(site, "term_delete", {"taxonomy": taxonomy, "term_id": term_id, "confirm": confirm})

    @mcp.tool(
        description="Dateien der Mediathek, neueste zuerst, mit URL zum Verlinken. mime_type z.B. application/pdf oder image.",
        annotations=READ_ONLY,
    )
    async def media_list(site: str, search: str | None = None, mime_type: str | None = None, limit: int = 20, page: int = 1) -> dict[str, Any]:
        return await runner.read(site, "media_list", {"search": search, "mime_type": mime_type, "limit": limit, "page": page})

    @mcp.tool(
        description=(
            "Legt einen Beitrag beliebigen Typs an (type aus post_type_list, Standard post). content als HTML oder Gutenberg-Blöcke (z.B. aus docx_to_content). "
            "status: draft (Standard), pending, publish, future, private; publish mit Datum in der Zukunft wird automatisch future (geplant). "
            "date: YYYY-MM-DD HH:MM in der Zeitzone der Seite oder ISO 8601. categories als ID, Slug oder Name (müssen existieren), "
            "tags als ID oder Name (fehlende werden angelegt), featured_media = Bild-ID aus der Mediathek, "
            "hide_featured_on_single=true blendet das Beitragsbild auf der Beitragsseite aus (Theme-Option, z.B. Blockchain). "
            "terms für weitere Taxonomien, parent/menu_order/template/comment_status wie im wp-admin." + CONFIRM_DOC
        ),
        annotations=WRITE,
    )
    async def post_create(
        site: str,
        title: str,
        content: str = "",
        type: PostType = "post",
        status: Status = "draft",
        date: str | None = None,
        categories: TermList | None = None,
        tags: TermList | None = None,
        featured_media: int | None = None,
        excerpt: str | None = None,
        slug: str | None = None,
        hide_featured_on_single: bool | None = None,
        terms: TermMap = None,
        parent: int | None = None,
        menu_order: int | None = None,
        template: str | None = None,
        comment_status: Literal["open", "closed"] | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        args = {
            "type": type, "title": title, "content": content, "status": status, "date": date, "categories": categories,
            "tags": tags, "featured_media": featured_media, "excerpt": excerpt, "slug": slug,
            "hide_featured_on_single": hide_featured_on_single, "terms": terms, "parent": parent, "menu_order": menu_order,
            "template": template, "comment_status": comment_status, "confirm": confirm,
        }
        return await runner.write(site, "post_create", args)

    @mcp.tool(
        description=(
            "Ändert einen Beitrag beliebigen Typs, nur die übergebenen Felder. Vor dem Ändern sichert das Plugin den alten Stand "
            "(Rückgabe backup_id, zurückholen mit post_rollback). categories, tags und terms ersetzen die bisherigen, featured_media=0 entfernt das Beitragsbild. "
            "template z.B. default, elementor_canvas, elementor_header_footer. Elementor-Inhalte mit den elementor_*-Tools ändern." + CONFIRM_DOC
        ),
        annotations=WRITE,
    )
    async def post_update(
        site: str,
        id: int,
        title: str | None = None,
        content: str | None = None,
        status: Status | None = None,
        date: str | None = None,
        categories: TermList | None = None,
        tags: TermList | None = None,
        featured_media: int | None = None,
        excerpt: str | None = None,
        slug: str | None = None,
        hide_featured_on_single: bool | None = None,
        terms: TermMap = None,
        parent: int | None = None,
        menu_order: int | None = None,
        template: str | None = None,
        comment_status: Literal["open", "closed"] | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        args = {
            "id": id, "title": title, "content": content, "status": status, "date": date, "categories": categories,
            "tags": tags, "featured_media": featured_media, "excerpt": excerpt, "slug": slug,
            "hide_featured_on_single": hide_featured_on_single, "terms": terms, "parent": parent, "menu_order": menu_order,
            "template": template, "comment_status": comment_status, "confirm": confirm,
        }
        return await runner.write(site, "post_update", args)

    @mcp.tool(
        description=(
            "Dupliziert einen Beitrag beliebigen Typs (auch Elementor-Seiten, -Vorlagen und -Popups) mit allen Zusatzfeldern, Begriffen und Beitragsbild. "
            "Elementor-Element-IDs werden neu vergeben, die Daten bleiben byte-genau (verify zeigt die Kontrolle). Status Standard draft. "
            "Popups und Theme-Vorlagen erhalten keine Anzeigebedingungen, ausser conditions wird übergeben (nur Elementor Pro)." + CONFIRM_DOC
        ),
        annotations=WRITE,
    )
    async def post_duplicate(
        site: str,
        id: int,
        title: str | None = None,
        slug: str | None = None,
        status: Literal["draft", "pending", "publish", "private"] = "draft",
        conditions: Annotated[list[str] | None, Field(description='Elementor-Anzeigebedingungen der Kopie, z.B. ["include/singular/page/12"].')] = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        return await runner.write(site, "post_duplicate", {"id": id, "title": title, "slug": slug, "status": status, "conditions": conditions, "confirm": confirm})

    @mcp.tool(
        description=(
            "Lädt eine Datei (z.B. PDF oder Bild) in die Mediathek der Seite. Quelle: url (öffentlich erreichbar) oder data_base64. "
            "Rückgabe media.url zum Verlinken im Beitrag, media.id als featured_media für Bilder. post_id ordnet die Datei einem Beitrag zu." + CONFIRM_DOC
        ),
        annotations=WRITE,
    )
    async def media_upload(
        site: str,
        url: str | None = None,
        data_base64: str | None = None,
        filename: str | None = None,
        title: str | None = None,
        alt_text: str | None = None,
        caption: str | None = None,
        description: str | None = None,
        post_id: int | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        ctx = runner.context(WRITE_SCOPE)
        runner.site(site)
        data, detected = await runner.load_file(url, data_base64)
        name = (filename or detected or "").strip()
        if not name or "." not in name:
            raise ToolError("filename mit Endung angeben (z.B. merkblatt.pdf).")
        args = {
            "filename": name, "data_base64": base64.b64encode(data).decode(), "title": title, "alt_text": alt_text,
            "caption": caption, "description": description, "post_id": post_id, "confirm": confirm,
        }
        return await runner.write(site, "media_upload", args, ctx)

    @mcp.tool(
        description="Verschiebt einen Beitrag beliebigen Typs in den Papierkorb (kein endgültiges Löschen, in WordPress wiederherstellbar)." + CONFIRM_DOC,
        annotations=TRASH,
    )
    async def post_trash(site: str, id: int, confirm: bool = False) -> dict[str, Any]:
        return await runner.write(site, "post_trash", {"id": id, "confirm": confirm})

    @mcp.tool(
        description=(
            "Stellt einen Beitrag aus einer Sicherung wieder her (backup_id aus post_get, leer = neueste Sicherung), auch die Elementor-Daten exakt "
            "(nach elementor_*-Änderungen). Der aktuelle Stand wird vorher ebenfalls gesichert, der Rollback ist also selbst umkehrbar." + CONFIRM_DOC
        ),
        annotations=WRITE,
    )
    async def post_rollback(site: str, id: int, backup_id: str | None = None, confirm: bool = False) -> dict[str, Any]:
        return await runner.write(site, "post_rollback", {"id": id, "backup_id": backup_id, "confirm": confirm})

    @mcp.tool(
        description=(
            "Wandelt ein Word-Dokument (.docx, per url oder data_base64) in Inhalt für post_create um: output=blocks (Gutenberg, Standard) "
            "oder html. Übernimmt Überschriften, Listen, Fett/Kursiv, Links und Tabellen, entfernt Schriftarten, Farben, leere Absätze "
            "und eingebettete Bilder. Die erste Überschrift wird als title zurückgegeben (extract_title), die übrigen Überschriften "
            "beginnen bei H2 (normalize_headings). Ändert nichts auf einer Seite."
        ),
        annotations=READ_ONLY,
    )
    async def docx_to_content(
        url: str | None = None,
        data_base64: str | None = None,
        output: Literal["blocks", "html"] = "blocks",
        extract_title: bool = True,
        normalize_headings: bool = True,
    ) -> dict[str, Any]:
        runner.context(READ)
        data, filename = await runner.load_file(url, data_base64)
        try:
            result = await asyncio.to_thread(convert_docx, data, output=output, extract_title=extract_title, normalize_headings=normalize_headings)
        except DocxError as exc:
            raise ToolError(str(exc))
        if filename:
            result["source_filename"] = filename
        return result

    # The other tool groups import the shared annotations from this module.
    from .tools_admin import register_admin_tools
    from .tools_elementor import register_elementor_tools
    from .tools_site import register_site_tools

    register_elementor_tools(mcp, runner)
    register_site_tools(mcp, runner)
    register_admin_tools(mcp, runner)
