"""Command line: wordpressmcp api | hash-password | sites | connections | revoke <user>"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import sys
from datetime import datetime, timezone

from . import __version__
from .config import ConfigError, Settings


def _setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stdout)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _ts(value: int | None) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if value else "-"


def _hash_password() -> None:
    from .crypto import hash_password

    if sys.stdin.isatty():
        first = getpass.getpass("Passwort: ")
        if first != getpass.getpass("Passwort wiederholen: "):
            print("Die Eingaben stimmen nicht überein.", file=sys.stderr)
            sys.exit(1)
    else:
        first = sys.stdin.readline().rstrip("\n")
    if len(first) < 12:
        print("Das Passwort muss mindestens 12 Zeichen haben.", file=sys.stderr)
        sys.exit(1)
    print(hash_password(first))


async def _connections(settings: Settings) -> None:
    from .store import Store

    store = Store(settings.database_path)
    names = await store.client_names()
    for user in sorted(settings.users):
        conns = await store.connections(user)
        print(f"{user}\t{len(conns)} Verbindung(en)")
        for c in conns:
            print(f"\t{names.get(c['client_id']) or c['client_id']}\tseit {_ts(c['created'])}\tzuletzt {_ts(c['last_used'] or None)}")


async def _revoke(settings: Settings, user: str) -> None:
    from .store import Store

    store = Store(settings.database_path)
    revoked = await store.revoke_user(user.strip().lower())
    print(f"{revoked} Token von {user} widerrufen")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="wordpressmcp", description=f"wordpress-mcp {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("api", help="MCP/OAuth-Server starten")
    sub.add_parser("hash-password", help="Passwort-Hash für GATEWAY_USERS erzeugen (Passwort über stdin oder Eingabe)")
    sub.add_parser("sites", help="konfigurierte Seiten anzeigen (ohne Passwörter)")
    sub.add_parser("connections", help="verbundene Anwendungen pro Benutzer")
    p = sub.add_parser("revoke", help="alle Verbindungen eines Benutzers trennen")
    p.add_argument("user")
    args = parser.parse_args(argv)

    if args.cmd == "hash-password":
        _hash_password()
        return

    _setup_logging()
    try:
        settings = Settings.load()
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        sys.exit(2)

    if args.cmd == "api":
        from .server import run_api

        run_api(settings)
    elif args.cmd == "sites":
        for site in settings.sites.values():
            print(f"{site.id}\t{site.label}\t{site.endpoint}\tUser {site.username}")
    elif args.cmd == "connections":
        asyncio.run(_connections(settings))
    else:
        asyncio.run(_revoke(settings, args.user))


if __name__ == "__main__":
    main()
