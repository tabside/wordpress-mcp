"""OAuthAuthorizationServerProvider backed by the SQLite store.

The MCP SDK serves /authorize, /token, /register, /revoke and the metadata
and verifies PKCE; this class supplies storage and policy. The login itself
happens on this service's own page (auth/pages.py) with a gateway user
name and password (GATEWAY_USERS).
"""

from __future__ import annotations

import logging
import secrets
import time
from typing import Any

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from ..config import Settings
from ..crypto import new_token
from ..limits import audit
from ..store import Store
from . import cimd

logger = logging.getLogger(__name__)


class UserAccessToken(AccessToken):
    user_id: str = ""


class UserRefreshToken(RefreshToken):
    user_id: str = ""
    token_hash: str = ""
    family_id: str = ""


class UserAuthorizationCode(AuthorizationCode):
    user_id: str = ""
    code_hash: str = ""
    revoke_others: bool = False


class GatewayAuthProvider:
    def __init__(self, settings: Settings, store: Store, *, cimd_transport: Any | None = None):
        self._settings = settings
        self._store = store
        self._cimd_transport = cimd_transport

    # ------------------------------------------------------------------ clients
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        cached = await self._store.get_client(client_id)
        if cimd.is_cimd_client_id(client_id):
            if cached is not None and time.time() - cached[2] < cimd.CACHE_TTL:
                return OAuthClientInformationFull.model_validate(cached[1])
            try:
                record = await cimd.fetch_document(
                    client_id, valid_scopes=self._settings.valid_scopes, transport=self._cimd_transport
                )
            except cimd.CimdError as exc:
                logger.warning("client metadata document rejected for %s: %s", client_id, exc)
                if cached is not None and time.time() - cached[2] < cimd.CACHE_TTL * 24:
                    return OAuthClientInformationFull.model_validate(cached[1])
                return None
            await self._store.save_client(client_id, "cimd", record)
            audit("client_metadata_fetched", client=client_id, client_name=record.get("client_name"))
            return OAuthClientInformationFull.model_validate(record)
        if cached is None:
            return None
        return OAuthClientInformationFull.model_validate(cached[1])

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.redirect_uris:
            raise RegistrationError("invalid_redirect_uri", "redirect_uris is required")
        for uri in client_info.redirect_uris:
            try:
                cimd.validate_redirect_uri(str(uri))
            except cimd.CimdError as exc:
                raise RegistrationError("invalid_redirect_uri", str(exc)) from exc
        if not client_info.scope:
            client_info.scope = " ".join(self._settings.valid_scopes)
        await self._store.save_client(client_info.client_id, "dcr", client_info.model_dump(mode="json", exclude_none=True))
        audit("client_registered", client=client_info.client_id, client_name=client_info.client_name)

    # ---------------------------------------------------------------- authorize
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        resource = self._validate_resource(params.resource)
        scopes = params.scopes or list(self._settings.valid_scopes)
        request_id = secrets.token_urlsafe(24)
        await self._store.save_auth_request(
            request_id,
            client.client_id,
            {
                "state": params.state,
                "scopes": scopes,
                "code_challenge": params.code_challenge,
                "redirect_uri": str(params.redirect_uri),
                "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
                "resource": resource,
            },
            self._settings.auth_request_ttl,
        )
        return f"{self._settings.public_base_url}/login?req={request_id}"

    def _validate_resource(self, resource: str | None) -> str:
        canonical = self._settings.resource_url
        if resource is None:
            return canonical
        if resource.rstrip("/").lower() != canonical.rstrip("/").lower():
            raise AuthorizeError("invalid_target", f"This authorization server only issues tokens for {canonical}")
        return canonical

    async def load_pending_request(self, request_id: str) -> tuple[str, dict[str, Any]] | None:
        return await self._store.get_auth_request(request_id)

    async def complete_login(
        self, request_id: str, client_id: str, params: dict[str, Any], user_id: str, *, revoke_others: bool = False
    ) -> str:
        code = new_token()
        await self._store.save_auth_code(
            code,
            client_id=client_id,
            user_id=user_id,
            scopes=params["scopes"],
            code_challenge=params["code_challenge"],
            redirect_uri=params["redirect_uri"],
            redirect_uri_explicit=params["redirect_uri_provided_explicitly"],
            resource=params.get("resource"),
            ttl=self._settings.auth_code_ttl,
            revoke_others=revoke_others,
        )
        await self._store.delete_auth_request(request_id)
        return construct_redirect_uri(params["redirect_uri"], code=code, state=params.get("state"), iss=self._settings.issuer_url)

    async def deny_login(self, request_id: str, params: dict[str, Any]) -> str:
        await self._store.delete_auth_request(request_id)
        return construct_redirect_uri(
            params["redirect_uri"],
            error="access_denied",
            error_description="The user cancelled the authorization",
            state=params.get("state"),
            iss=self._settings.issuer_url,
        )

    # --------------------------------------------------------------------- codes
    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> UserAuthorizationCode | None:
        row = await self._store.get_auth_code(authorization_code)
        if row is None or row.client_id != client.client_id or row.used:
            return None
        return UserAuthorizationCode(
            code=authorization_code,
            scopes=row.scopes,
            expires_at=row.expires_at,
            client_id=row.client_id,
            code_challenge=row.code_challenge,
            redirect_uri=row.redirect_uri,  # type: ignore[arg-type]
            redirect_uri_provided_explicitly=row.redirect_uri_explicit,
            resource=row.resource,
            subject=row.user_id,
            user_id=row.user_id,
            code_hash=row.code_hash,
            revoke_others=row.revoke_others,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: UserAuthorizationCode
    ) -> OAuthToken:
        if not await self._store.consume_auth_code(authorization_code.code_hash):
            raise TokenError("invalid_grant", "authorization code already used")
        family_id = secrets.token_urlsafe(16)
        token = await self._issue(
            client_id=client.client_id,
            user_id=authorization_code.user_id,
            scopes=authorization_code.scopes,
            resource=authorization_code.resource or self._settings.resource_url,
            family_id=family_id,
        )
        audit("token_issued", user=authorization_code.user_id, client=client.client_id, grant="authorization_code")
        if authorization_code.revoke_others:
            revoked = await self._store.revoke_user(authorization_code.user_id, except_family=family_id)
            audit("tokens_revoked", user=authorization_code.user_id, tokens_revoked=revoked, source="login_checkbox")
        return token

    async def _issue(self, *, client_id: str, user_id: str, scopes: list[str], resource: str, family_id: str) -> OAuthToken:
        access = new_token()
        refresh = new_token()
        common = dict(client_id=client_id, user_id=user_id, scopes=scopes, resource=resource, family_id=family_id)
        await self._store.save_token(access, kind="access", ttl=self._settings.access_token_ttl, **common)
        await self._store.save_token(refresh, kind="refresh", ttl=self._settings.refresh_token_ttl, **common)
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=self._settings.access_token_ttl,
            scope=" ".join(scopes),
            refresh_token=refresh,
        )

    # ------------------------------------------------------------ refresh tokens
    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> UserRefreshToken | None:
        row = await self._store.get_token(refresh_token, "refresh")
        if row is None or row.client_id != client.client_id or row.revoked:
            return None
        if row.rotated:
            # reuse of a rotated refresh token: the whole family is compromised (OAuth 2.1 4.3.1)
            revoked = await self._store.revoke_family(row.family_id)
            audit("refresh_token_reuse", user=row.user_id, client=client.client_id, tokens_revoked=revoked)
            return None
        return UserRefreshToken(
            token=refresh_token,
            client_id=row.client_id,
            scopes=row.scopes,
            expires_at=row.expires_at,
            resource=row.resource,
            subject=row.user_id,
            user_id=row.user_id,
            token_hash=row.token_hash,
            family_id=row.family_id,
        )

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: UserRefreshToken, scopes: list[str]
    ) -> OAuthToken:
        if refresh_token.user_id not in self._settings.users:
            await self._store.revoke_family(refresh_token.family_id)
            raise TokenError("invalid_grant", "user is no longer configured")
        if not await self._store.mark_rotated(refresh_token.token_hash):
            raise TokenError("invalid_grant", "refresh token already used")
        token = await self._issue(
            client_id=client.client_id,
            user_id=refresh_token.user_id,
            scopes=scopes or refresh_token.scopes,
            resource=refresh_token.resource or self._settings.resource_url,
            family_id=refresh_token.family_id,
        )
        audit("token_issued", user=refresh_token.user_id, client=client.client_id, grant="refresh_token")
        return token

    # ------------------------------------------------------------- access tokens
    async def load_access_token(self, token: str) -> UserAccessToken | None:
        row = await self._store.get_token(token, "access")
        if row is None or row.revoked or row.expires_at < int(time.time()):
            return None
        if row.user_id not in self._settings.users:
            return None
        await self._store.touch_token(row.token_hash)
        return UserAccessToken(
            token=token,
            client_id=row.client_id,
            scopes=row.scopes,
            expires_at=row.expires_at,
            resource=row.resource,
            subject=row.user_id,
            user_id=row.user_id,
        )

    async def revoke_token(self, token: UserAccessToken | UserRefreshToken) -> None:
        kind = "refresh" if isinstance(token, RefreshToken) else "access"
        row = await self._store.get_token(token.token, kind)
        if row is None:
            return
        revoked = await self._store.revoke_family(row.family_id)
        audit("tokens_revoked", user=row.user_id, client=row.client_id, tokens_revoked=revoked, source="client")

    async def exchange_identity_assertion(self, client: OAuthClientInformationFull, params: Any) -> OAuthToken:
        raise TokenError("unsupported_grant_type", "The JWT bearer grant is not supported")
