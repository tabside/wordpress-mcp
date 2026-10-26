"""Configuration from environment variables.

No defaults for secrets, hostnames or sites: the service refuses to start when a
required variable is missing and names it in the log.

Sites as one JSON variable (what docker-compose.yml passes through, convenient in Portainer):

    WP_SITES=[{"id": "kunde", "url": "https://www.example.com", "app_password": "abcd efgh ...",
               "user": "claude-mcp", "label": "Kunde AG", "rest_url": "..."}]

    (or WP_SITES_FILE=/run/secrets/wp_sites; user, label and rest_url are optional)

and/or one block of variables per site (KEY = A-Z, 0-9, _):

    WP_SITE_<KEY>_URL                 https://www.example.com   (required)
    WP_SITE_<KEY>_APP_PASSWORD        Application Password      (required, or _APP_PASSWORD_FILE)
    WP_SITE_<KEY>_USER                WordPress user            (default claude-mcp)
    WP_SITE_<KEY>_LABEL               display name              (default: the host)
    WP_SITE_<KEY>_REST_URL            REST API root             (default <URL>/wp-json; plain permalinks <URL>/?rest_route=)

The site id used in the tools is KEY in lower case with "-" instead of "_".
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

VALID_SCOPES = ["wordpress:read", "wordpress:write"]
DEFAULT_WP_USER = "claude-mcp"

_SITE_URL = re.compile(r"^WP_SITE_([A-Z0-9_]+)_URL$")
_USER_NAME = re.compile(r"^[a-z0-9._@-]{1,64}$")


class ConfigError(RuntimeError):
    pass


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _is_local(host: str | None) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


@dataclass(frozen=True)
class SiteConfig:
    id: str
    label: str
    url: str
    rest_url: str
    username: str
    app_password: str = field(repr=False)


def _read_secret(name: str) -> str | None:
    value = _env(name)
    if value is not None:
        return value
    path = _env(f"{name}_FILE")
    if path is None:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError as exc:
        raise ConfigError(f"{name}_FILE cannot be read: {exc.strerror}") from exc


_SITE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")


def _make_site(source: str, site_id: str, url: str, password: str | None, user: str | None, label: str | None, rest_url: str | None) -> SiteConfig:
    if not _SITE_ID.fullmatch(site_id):
        raise ConfigError(f"{source}: site id {site_id!r} may only contain a-z, 0-9 and -")
    url = (url or "").strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise ConfigError(f"{source}: url must be an absolute URL, e.g. https://www.example.com")
    if parsed.scheme == "http" and not _is_local(parsed.hostname):
        raise ConfigError(f"{source}: url must use https (Application Passwords must not travel in clear text)")
    if not password:
        raise ConfigError(f"{source}: app_password is missing")
    rest_url = (rest_url or f"{url}/wp-json").strip().rstrip("/")
    ep = urlparse(rest_url)
    if ep.scheme not in ("https", "http") or not ep.hostname or (ep.scheme == "http" and not _is_local(ep.hostname)):
        raise ConfigError(f"{source}: rest_url must be an https URL")
    return SiteConfig(
        id=site_id,
        label=(label or "").strip() or parsed.hostname,
        url=url,
        rest_url=rest_url,
        username=(user or "").strip() or DEFAULT_WP_USER,
        app_password=password.strip(),
    )


def _sites_from_json() -> list[SiteConfig]:
    raw = _read_secret("WP_SITES")
    if raw is None:
        return []
    try:
        items = json.loads(raw)
    except ValueError as exc:
        raise ConfigError(f"WP_SITES is not valid JSON ({exc.msg} at position {exc.pos})") from exc
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        raise ConfigError("WP_SITES must be a JSON list of objects")
    out = []
    for n, item in enumerate(items, 1):
        unknown = set(item) - {"id", "url", "app_password", "user", "label", "rest_url"}
        if unknown:
            raise ConfigError(f"WP_SITES entry {n}: unknown field(s) {', '.join(sorted(unknown))}")
        values = {k: item.get(k) for k in ("id", "url", "app_password", "user", "label", "rest_url")}
        if not all(v is None or isinstance(v, str) for v in values.values()):
            raise ConfigError(f"WP_SITES entry {n}: all values must be strings")
        out.append(
            _make_site(
                f"WP_SITES entry {n}", (values["id"] or "").strip().lower(), values["url"] or "", values["app_password"],
                values["user"], values["label"], values["rest_url"],
            )
        )
    return out


def load_sites() -> dict[str, SiteConfig]:
    sites: dict[str, SiteConfig] = {}
    for site in _sites_from_json():
        if site.id in sites:
            raise ConfigError(f"site id {site.id!r} is configured twice")
        sites[site.id] = site
    for name in sorted(os.environ):
        match = _SITE_URL.match(name)
        if not match:
            continue
        key = match.group(1)
        if key.endswith("_REST") and f"WP_SITE_{key[:-5]}_URL" in os.environ:
            continue  # WP_SITE_<KEY>_REST_URL belongs to site <KEY>
        prefix = f"WP_SITE_{key}_"
        site = _make_site(
            prefix + "*", key.lower().replace("_", "-"), _env(name) or "", _read_secret(prefix + "APP_PASSWORD"),
            _env(prefix + "USER"), _env(prefix + "LABEL"), _env(prefix + "REST_URL"),
        )
        if site.id in sites:
            raise ConfigError(f"site id {site.id!r} is configured twice")
        sites[site.id] = site
    return sites


def load_users(raw: str | None) -> dict[str, str]:
    """GATEWAY_USERS=name=<hash>,name2=<hash> (hashes from `wordpressmcp hash-password`)."""
    from .crypto import validate_password_hash

    users: dict[str, str] = {}
    for item in (raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        name, sep, encoded = item.partition("=")
        name = name.strip().lower()
        if not sep or not _USER_NAME.fullmatch(name):
            raise ConfigError(f"GATEWAY_USERS entry {name or item[:20]!r}: expected name=<hash>")
        try:
            validate_password_hash(encoded.strip())
        except ValueError as exc:
            raise ConfigError(f"GATEWAY_USERS entry {name!r}: {exc}") from exc
        users[name] = encoded.strip()
    return users


@dataclass(frozen=True)
class Settings:
    public_base_url: str  # https://mcp.example.com/wordpress
    base_path: str  # "/wordpress" or ""
    public_host: str
    service_name: str
    database_path: str
    users: dict[str, str]  # login name -> password hash
    sites: dict[str, SiteConfig]
    host: str
    port: int
    trusted_proxies: str
    access_token_ttl: int
    refresh_token_ttl: int
    auth_request_ttl: int
    auth_code_ttl: int
    account_session_ttl: int
    login_failures_per_ip: int
    login_failure_window: int
    tool_calls_per_minute: int
    wp_timeout: float
    max_file_bytes: int

    @property
    def resource_url(self) -> str:
        return f"{self.public_base_url}/mcp"

    @property
    def issuer_url(self) -> str:
        return self.public_base_url

    @property
    def valid_scopes(self) -> list[str]:
        return list(VALID_SCOPES)

    @staticmethod
    def load() -> "Settings":
        missing: list[str] = []

        def req(name: str) -> str:
            value = _env(name)
            if value is None:
                missing.append(name)
                return ""
            return value

        public_base_url = req("PUBLIC_BASE_URL").rstrip("/")
        users_raw = req("GATEWAY_USERS")
        if missing:
            raise ConfigError("missing required environment variable(s): " + ", ".join(missing))

        parsed = urlparse(public_base_url)
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            raise ConfigError("PUBLIC_BASE_URL must be an absolute URL, e.g. https://wordpress-mcp.example.com")
        if parsed.scheme == "http" and not _is_local(parsed.hostname):
            raise ConfigError("PUBLIC_BASE_URL must use https (http only for localhost)")
        base_path = parsed.path.rstrip("/")
        if base_path and not base_path.startswith("/"):
            base_path = "/" + base_path

        users = load_users(users_raw)
        if not users:
            raise ConfigError("GATEWAY_USERS contains no user")
        # Without sites the gateway still starts (login, list_sites, docx_to_content); run_api warns.
        sites = load_sites()

        return Settings(
            public_base_url=public_base_url,
            base_path=base_path,
            public_host=parsed.netloc,
            service_name=_env("SERVICE_NAME", "WordPress MCP") or "WordPress MCP",
            database_path=_env("DATABASE_PATH", "/data/wordpressmcp.sqlite3") or "/data/wordpressmcp.sqlite3",
            users=users,
            sites=sites,
            host=_env("MCP_HOST", "0.0.0.0") or "0.0.0.0",
            port=_env_int("MCP_PORT", 8000),
            trusted_proxies=_env("TRUSTED_PROXIES", "*") or "*",
            access_token_ttl=_env_int("ACCESS_TOKEN_TTL", 3600),
            refresh_token_ttl=_env_int("REFRESH_TOKEN_TTL", 30 * 86400),
            auth_request_ttl=_env_int("AUTH_REQUEST_TTL", 900),
            auth_code_ttl=_env_int("AUTH_CODE_TTL", 300),
            account_session_ttl=_env_int("ACCOUNT_SESSION_TTL", 900),
            login_failures_per_ip=_env_int("LOGIN_FAILURES_PER_IP", 10),
            login_failure_window=_env_int("LOGIN_FAILURE_WINDOW", 900),
            tool_calls_per_minute=_env_int("TOOL_CALLS_PER_MINUTE", 120),
            wp_timeout=float(_env_int("WP_TIMEOUT", 60)),
            max_file_bytes=_env_int("MAX_FILE_MB", 20) * 1024 * 1024,
        )
