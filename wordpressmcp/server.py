"""Starlette application: MCP endpoint, OAuth, discovery, login and account pages.

Layout for PUBLIC_BASE_URL=https://wordpress-mcp.example.com (own subdomain, no path):

    /.well-known/oauth-authorization-server     AS metadata (RFC 8414)
    /.well-known/openid-configuration           same document (fallback)
    /.well-known/oauth-protected-resource/mcp   protected resource metadata (RFC 9728)
    /authorize /token /register /revoke         OAuth (MCP SDK)
    /login                                      login with a gateway user (GATEWAY_USERS)
    /account                                    connected applications of a user
    /mcp                                        MCP Streamable HTTP endpoint (bearer token)
    /healthz  /readyz                           operations

With a path in PUBLIC_BASE_URL (https://mcp.example.com/wordpress) everything
moves below that path and the well-known documents get it as suffix.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from mcp.server.auth.handlers.metadata import MetadataHandler, ProtectedResourceMetadataHandler
from mcp.server.auth.routes import build_metadata, cors_middleware
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.auth import ProtectedResourceMetadata

from . import GIT_SHA, __version__
from .auth.pages import Pages
from .auth.provider import GatewayAuthProvider
from .config import Settings
from .limits import MemoryLimiter
from .store import Store
from .tools import ToolRunner, register_tools
from .wordpress import SitePool

logger = logging.getLogger(__name__)

INSTRUCTIONS = (
    "Dieses Gateway bearbeitet Beiträge, Seiten und Medien auf WordPress-Seiten von Kunden über das Plugin tabside-mcp. "
    "Zuerst list_sites aufrufen und bei jedem weiteren Tool die id als site übergeben. Schreibende Tools (post_create, "
    "post_update, media_upload, post_trash, post_rollback) liefern ohne confirm=true nur eine Vorschau; confirm=true erst "
    "setzen, wenn der Benutzer die Vorschau bestätigt hat. Ablauf für einen Blogbeitrag aus Word: docx_to_content, "
    "PDF mit media_upload hochladen und media.url im Inhalt verlinken, dann post_create mit status, date, categories. "
    "publish mit Datum in der Zukunft wird automatisch future (geplant). Vor jedem post_update wird der alte Stand "
    "gesichert, zurückholen mit post_rollback. Gelöscht wird nie endgültig, post_trash verschiebt in den Papierkorb."
)


@dataclass
class Services:
    settings: Settings
    store: Store
    pool: SitePool
    provider: GatewayAuthProvider
    limiter: MemoryLimiter
    mcp: MCPServer


def build_services(
    settings: Settings,
    *,
    store: Store | None = None,
    wp_transport: Any | None = None,
    cimd_transport: Any | None = None,
    fetch_options: dict[str, Any] | None = None,
) -> Services:
    store = store or Store(settings.database_path)
    pool = SitePool(settings.sites, timeout=settings.wp_timeout, transport=wp_transport)
    limiter = MemoryLimiter(settings)
    provider = GatewayAuthProvider(settings, store, cimd_transport=cimd_transport)
    auth_settings = AuthSettings(
        issuer_url=AnyHttpUrl(settings.issuer_url),
        resource_server_url=AnyHttpUrl(settings.resource_url),
        client_registration_options=ClientRegistrationOptions(
            enabled=True, valid_scopes=list(settings.valid_scopes), default_scopes=list(settings.valid_scopes)
        ),
        revocation_options=RevocationOptions(enabled=True),
        required_scopes=["wordpress:read"],
        validate_token_resource=True,
    )
    mcp = MCPServer(
        "wordpress-mcp",
        title=settings.service_name,
        instructions=INSTRUCTIONS,
        version=__version__,
        auth_server_provider=provider,
        auth=auth_settings,
    )
    register_tools(mcp, ToolRunner(settings, pool, limiter, fetch_options=fetch_options), settings)
    return Services(settings, store, pool, provider, limiter, mcp)


def build_app(services: Services) -> Starlette:
    settings = services.settings
    mcp = services.mcp
    pages = Pages(settings, services.provider, services.store, services.limiter)

    mcp.custom_route("/login", methods=["GET"])(pages.login_get)
    mcp.custom_route("/login", methods=["POST"])(pages.login_post)
    mcp.custom_route("/account", methods=["GET"])(pages.account_get)
    mcp.custom_route("/account/login", methods=["POST"])(pages.account_login)
    mcp.custom_route("/account/logout", methods=["POST"])(pages.account_logout)
    mcp.custom_route("/account/disconnect", methods=["POST"])(pages.account_disconnect)

    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request) -> Response:
        return JSONResponse({"status": "ok", "version": __version__, "commit": GIT_SHA, "time": int(time.time())})

    @mcp.custom_route("/readyz", methods=["GET"])
    async def readyz(request: Request) -> Response:
        try:
            ok = await services.store.ping()
        except Exception:  # noqa: BLE001
            ok = False
        return JSONResponse({"status": "ok" if ok else "degraded", "checks": {"database": ok}}, status_code=200 if ok else 503)

    @mcp.custom_route("/", methods=["GET"])
    async def index(request: Request) -> Response:
        return JSONResponse({"service": settings.service_name, "mcp_endpoint": settings.resource_url, "account_page": f"{settings.public_base_url}/account", "version": __version__})

    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[settings.public_host, "127.0.0.1:*", "localhost:*"],
        allowed_origins=[f"https://{settings.public_host}", "http://127.0.0.1:*", "http://localhost:*"],
    )
    inner = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        transport_security=transport_security,
        host=settings.host,
    )

    assert mcp.settings.auth is not None
    metadata = build_metadata(
        mcp.settings.auth.issuer_url,
        None,
        mcp.settings.auth.client_registration_options or ClientRegistrationOptions(),
        mcp.settings.auth.revocation_options or RevocationOptions(),
    )
    metadata.client_id_metadata_document_supported = True
    metadata.authorization_response_iss_parameter_supported = True
    metadata_endpoint = cors_middleware(MetadataHandler(metadata).handle, ["GET", "OPTIONS"])

    prm = ProtectedResourceMetadata(
        resource=AnyHttpUrl(settings.resource_url),
        authorization_servers=[AnyHttpUrl(settings.issuer_url)],
        scopes_supported=list(settings.valid_scopes),
        resource_name=settings.service_name,
    )
    prm_endpoint = cors_middleware(ProtectedResourceMetadataHandler(prm).handle, ["GET", "OPTIONS"])

    inner_routes = list(inner.router.routes)
    for position, route in enumerate(inner_routes):
        if isinstance(route, Route) and route.path == "/.well-known/oauth-authorization-server":
            inner_routes[position] = Route(route.path, endpoint=metadata_endpoint, methods=["GET", "OPTIONS"])
    inner_routes.insert(0, Route("/.well-known/openid-configuration", endpoint=metadata_endpoint, methods=["GET", "OPTIONS"]))
    inner.router.routes[:] = inner_routes

    base = settings.base_path
    well_known: list[Route | Mount] = [
        Route(f"/.well-known/oauth-authorization-server{base}", endpoint=metadata_endpoint, methods=["GET", "OPTIONS"]),
        Route(f"/.well-known/openid-configuration{base}", endpoint=metadata_endpoint, methods=["GET", "OPTIONS"]),
        Route(f"/.well-known/oauth-protected-resource{base}/mcp", endpoint=prm_endpoint, methods=["GET", "OPTIONS"]),
    ]

    async def cleanup_loop() -> None:
        while True:
            try:
                await services.store.cleanup()
            except Exception:  # noqa: BLE001
                logger.exception("cleanup failed")
            await asyncio.sleep(3600)

    @asynccontextmanager
    async def lifespan(app: Starlette):
        task = asyncio.create_task(cleanup_loop())
        try:
            async with inner.router.lifespan_context(inner):
                yield
        finally:
            task.cancel()

    if not base:
        return Starlette(routes=[*well_known, Mount("", app=inner)], lifespan=lifespan)
    return Starlette(routes=[*well_known, Mount(base, app=inner)], lifespan=lifespan)


def run_api(settings: Settings) -> None:
    import uvicorn

    logger.info(
        "wordpress-mcp %s (%s) on %s:%s, public URL %s, sites %s, users %s",
        __version__, GIT_SHA[:12], settings.host, settings.port, settings.public_base_url, ",".join(settings.sites), len(settings.users),
    )
    if not settings.sites:
        logger.warning("no WordPress site configured (WP_SITES), only list_sites and docx_to_content are useful")
    uvicorn.run(
        build_app(build_services(settings)),
        host=settings.host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips=settings.trusted_proxies,
        log_level="info",
        log_config=None,
    )
