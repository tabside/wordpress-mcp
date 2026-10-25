# WordPress MCP

Beiträge, Seiten und Medien auf WordPress-Seiten von Kunden über Claude (claude.ai, Cowork, Mobile-App, Claude Code) anlegen und bearbeiten. Zwei Teile:

1. **Plugin `tabside-mcp`** (`plugin/tabside-mcp`, auf jeder Kundenseite): registriert Abilities der Kategorie `tabside` über die Abilities API (WordPress-Core ab 6.9) und stellt sie über den offiziellen [MCP Adapter](https://github.com/WordPress/mcp-adapter) als eigenen MCP-Server bereit: `/wp-json/mcp/tabside`. Ausführen darf nur der Benutzer `claude-mcp` (Rolle Redakteur) mit Anwendungspasswort.
2. **Gateway `wordpress-mcp`** (dieses Repo, Docker): Remote-MCP-Server mit OAuth-Login, der in claude.ai als eigener Connector eingetragen wird. Er hält die Anwendungspasswörter der Seiten und leitet die Tool-Aufrufe an das Plugin der gewählten Seite weiter. claude.ai-Connectors können keine Anwendungspasswörter pro Seite mitschicken, darum der Umweg.

```
claude.ai ──OAuth──▶ Gateway ──Basic Auth (claude-mcp + Anwendungspasswort)──▶ https://kunde/wp-json/mcp/tabside ──▶ Abilities
```

## Tools

Jedes Tool ausser `get_version`, `list_sites` und `docx_to_content` hat den Parameter `site` (id aus `list_sites`).

| Tool | Art | Beschreibung |
| --- | --- | --- |
| `list_sites` | lesen | Konfigurierte Seiten; mit `check=true` wird jede Seite angefragt (Plugin-, WordPress- und Adapter-Version oder Fehler) |
| `get_version` | lesen | Version und Commit des Gateways, mit `site` auch des Plugins |
| `post_list` | lesen | Beiträge oder Seiten: `type` (post/page/any), `status`, `search`, `category`, `limit`, `page` |
| `post_get` | lesen | Inhalt (roh), Datum, Status, Kategorien, Schlagwörter, Beitragsbild, Vorschau-Link, Sicherungen |
| `category_list`, `tag_list` | lesen | ID, Name, Slug, Anzahl |
| `media_list` | lesen | Mediathek mit URL, Filter `mime_type` (z.B. `application/pdf`) |
| `docx_to_content` | lesen | Word (.docx per `url` oder `data_base64`) in Gutenberg-Blöcke oder HTML umwandeln, siehe unten |
| `post_create` | schreiben | Titel, Inhalt (HTML oder Blöcke), Status draft/pending/publish/future/private, Datum, Kategorien, Schlagwörter, Beitragsbild, Auszug, Slug |
| `post_update` | schreiben | Gleiche Felder, nur was übergeben wird. Sichert vorher den alten Stand |
| `media_upload` | schreiben | Datei per `url` oder `data_base64` in die Mediathek, Rückgabe `media.url` zum Verlinken |
| `post_trash` | schreiben | In den Papierkorb (kein endgültiges Löschen) |
| `post_rollback` | schreiben | Sicherung zurückholen (Standard: neueste), der aktuelle Stand wird vorher ebenfalls gesichert |

**Alle schreibenden Tools ändern nur mit `confirm=true` etwas.** Ohne `confirm` liefert das Plugin eine Vorschau (Felder, aufgelöste Kategorien, neue Schlagwörter, effektiver Status, bei Updates alt/neu pro Feld). Das confirm-Gate sitzt im Plugin selbst, gilt also auch für einen direkten Zugriff auf den MCP-Endpunkt der Seite.

Details:

* **Datum:** `YYYY-MM-DD HH:MM[:SS]` in der Zeitzone der Seite (Einstellungen > Allgemein) oder ISO 8601 mit Zeitzone. Ohne Uhrzeit gilt 00:00, die Vorschau weist darauf hin. Andere Formate (z.B. `22.09.2026`) werden abgelehnt.
* **Status:** `publish` mit Datum in der Zukunft wird `future` (geplant), `future` mit Datum in der Vergangenheit ist ein Fehler, `publish` mit Datum in der Vergangenheit veröffentlicht rückdatiert. Ein Entwurf (`draft`) behält ein gesetztes Datum.
* **Kategorien** als ID, Slug oder Name, sie müssen existieren. **Schlagwörter** als ID oder Name, fehlende Namen werden angelegt (in der Vorschau mit "(neu)"). Beides ersetzt die bisherige Zuordnung und gibt es nur bei Beiträgen.
* **Inhalt** wird unverändert gespeichert (Backslashes, Anführungszeichen und Block-Kommentare bleiben erhalten, im Integrationstest geprüft).
* **Sicherungen:** Vor jedem `post_update` und `post_rollback` speichert das Plugin Titel, Inhalt, Auszug, Status, Datum, Slug, Kategorien, Schlagwörter und Beitragsbild im Post-Meta `_tabside_mcp_backups` (die letzten 20, Filter `tabside_mcp_max_backups`). Das ist unabhängig von den WordPress-Revisionen, die manche Hostings abschalten.
* **Uploads:** Erlaubt sind die Dateitypen, die WordPress auf der Seite erlaubt, bis zur maximalen Upload-Grösse der Seite (`get_version` zeigt `max_upload_mb`) und `MAX_FILE_MB` des Gateways. Downloads per `url` laufen über das Gateway (nur öffentliche Adressen, siehe Sicherheit), die Kundenseite lädt nie selbst eine URL.

## Word zu Beitrag (`docx_to_content`)

Überschriften, Absätze, Listen (auch verschachtelt und nummeriert), Fett, Kursiv, Links, Tabellen und Zitate werden übernommen; Schriftarten, Farben, Grössen, leere Absätze, Word-Textmarken und geschützte Leerzeichen werden entfernt, eingebettete Bilder ebenfalls (mit Hinweis, Bilder separat hochladen). Links nur mit `http`, `https`, `mailto`, `tel` oder `#`.

* `output=blocks` (Standard) erzeugt Gutenberg-Blöcke (`core/paragraph`, `core/heading`, `core/list`, `core/list-item`, `core/table`, `core/quote`) mit genau dem Markup, das der Block-Editor speichert. Im Editor von WordPress 6.9 und 7.1.3 als gültig geprüft (keine "unerwarteter Inhalt"-Meldung). `output=html` liefert sauberes HTML.
* `extract_title=true`: steht am Anfang eine Überschrift, wird sie als `title` zurückgegeben und aus dem Inhalt entfernt.
* `normalize_headings=true`: die übrigen Überschriften werden so verschoben, dass die oberste H2 ist (H1 ist im Beitrag der Titel).
* Word-Formatvorlagen: Überschrift 1-6 / Heading 1-6, Titel / Title, Zitat / Quote. Unbekannte Formatvorlagen werden als normaler Absatz übernommen und in `warnings` gemeldet.

Typischer Ablauf für einen Blogbeitrag aus Word plus PDF:

1. `docx_to_content` mit der Word-Datei
2. `media_upload` mit dem PDF, `media.url` im Inhalt verlinken
3. `post_create` mit `title`, `content`, `status=publish` (oder `draft`), `date`, `categories`, zuerst ohne `confirm` (Vorschau), dann mit `confirm=true`

## Plugin auf einer Kundenseite installieren

Voraussetzungen: WordPress **6.9 oder neuer** (Abilities API im Core), HTTPS (sonst bietet WordPress keine Anwendungspasswörter an), Pretty Permalinks oder ein eigener `endpoint` mit `?rest_route=`.

1. Plugin **MCP Adapter** installieren und aktivieren: ZIP von <https://github.com/WordPress/mcp-adapter/releases/latest> über Plugins > Installieren > Plugin hochladen.
2. Plugin **tabside-mcp** genauso installieren: ZIP aus den [Releases](../../releases) dieses Repos (`tabside-mcp-<version>.zip`).
3. Benutzer `claude-mcp` mit der Rolle **Redakteur** anlegen (kein Admin). Unter Benutzer > Profil > Anwendungspasswörter ein Passwort "wordpress-mcp" erzeugen und sofort notieren, WordPress zeigt es nur einmal.
4. Seite im Gateway eintragen (`WP_SITES`, siehe unten) und mit `list_sites` (`check=true`) prüfen.

Bei WordPress unter 6.9 bleibt das Plugin inaktiv und zeigt Administratoren einen Hinweis; ebenso, wenn der MCP Adapter fehlt oder der Benutzer `claude-mcp` nicht existiert. Ein anderer Benutzername lässt sich mit `define( 'TABSIDE_MCP_USER', '...' );` in der `wp-config.php` oder dem Filter `tabside_mcp_allowed_user` setzen.

Ein ZIP entsteht bei jedem Tag `plugin-v<Version>` (muss zur Version im Plugin-Header passen) als GitHub-Release, bei jedem Push auf `main` zusätzlich als Actions-Artefakt. Der Commit-Hash steht danach in `get_version`.

## Gateway betreiben

Das Image wird bei jedem Push auf `main` von GitHub Actions gebaut (Lint, Tests, Plugin-Integrationstest gegen WordPress 6.9 und die aktuelle Version, Smoke-Test) und nach `ghcr.io/tabside/wordpress-mcp` veröffentlicht (`latest`, Commit-SHA, Version). Einmalig nach dem ersten Push das Package auf GitHub unter Packages > Package settings auf **Public** stellen, sonst kann Portainer nicht ohne Zugangsdaten pullen.

1. Login-Benutzer anlegen: `docker run --rm -i ghcr.io/tabside/wordpress-mcp wordpressmcp hash-password` (Passwort mindestens 12 Zeichen eingeben), Ausgabe als `GATEWAY_USERS=kim=<hash>` eintragen. Mehrere Benutzer mit Komma trennen.
2. In Portainer **Stacks > Add stack > Build method: Repository**, dieses Repo, Branch `main`, Compose-Pfad `docker-compose.yml`. Unter Environment variables die Werte aus `.env.example` setzen. Die Anwendungspasswörter stehen nur dort in `WP_SITES`, nie im Repo.
3. DNS-Eintrag für die Subdomain und Proxy-Host im Nginx Proxy Manager auf `<Host-IP>:8440` (bzw. `MCP_HOST_PORT`) mit TLS-Zertifikat, `MCP_BIND_ADDR` auf die Host-IP setzen, über die NPM den Container erreicht.
4. Prüfen:

```bash
curl -s https://wordpress-mcp.example.com/healthz
curl -s https://wordpress-mcp.example.com/.well-known/oauth-protected-resource/mcp
curl -s https://wordpress-mcp.example.com/.well-known/oauth-authorization-server
curl -si -X POST https://wordpress-mcp.example.com/mcp   # 401 mit WWW-Authenticate: Bearer resource_metadata=...
```

### Variablen

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `PUBLIC_BASE_URL` | – | Öffentliche URL, z.B. `https://wordpress-mcp.example.com` |
| `GATEWAY_USERS` | – | `name=<hash>`, kommagetrennt (`wordpressmcp hash-password`) |
| `WP_SITES` | – | JSON-Liste der Seiten, siehe unten. Alternativ `WP_SITES_FILE` (Pfad, z.B. Docker-Secret) oder pro Seite `WP_SITE_<KEY>_URL`, `_APP_PASSWORD` (bzw. `_APP_PASSWORD_FILE`), `_USER`, `_LABEL`, `_ENDPOINT` |
| `SERVICE_NAME` | `WordPress MCP` | Name auf Login- und Kontoseite |
| `ACCESS_TOKEN_TTL` / `REFRESH_TOKEN_TTL` | 3600 / 2592000 | Gültigkeit in Sekunden |
| `TOOL_CALLS_PER_MINUTE` | 120 | pro Benutzer |
| `LOGIN_FAILURES_PER_IP` / `LOGIN_FAILURE_WINDOW` | 10 / 900 | Sperre nach Fehlversuchen |
| `WP_TIMEOUT` | 60 | Sekunden pro Anfrage an eine Seite |
| `MAX_FILE_MB` | 20 | Maximale Grösse für `media_upload` und `docx_to_content` |
| `MCP_BIND_ADDR` / `MCP_HOST_PORT` | 127.0.0.1 / 8440 | veröffentlichter Port (Compose) |
| `TRUSTED_PROXIES` | `*` | Proxies, deren `X-Forwarded-*` übernommen wird |

`WP_SITES` (eine Zeile):

```json
[{"id":"kunde","url":"https://www.example.com","app_password":"xxxx xxxx xxxx xxxx xxxx xxxx","label":"Kunde AG"},
 {"id":"zweite","url":"https://www.example.org","app_password":"...","user":"claude-mcp","endpoint":"https://www.example.org/?rest_route=/mcp/tabside"}]
```

`id` (a-z, 0-9, -) ist der Wert für `site`. `user` ist standardmässig `claude-mcp`, `endpoint` standardmässig `<url>/wp-json/mcp/tabside`. Nur https (http nur für localhost).

### In Claude verbinden

**claude.ai, Cowork, Desktop, Mobile:** Einstellungen > Connectors > Eigenen Connector hinzufügen, URL `https://wordpress-mcp.example.com/mcp`, speichern, Verbinden, auf der Anmeldeseite mit Gateway-Benutzer und Passwort anmelden.

**Claude Code:** `claude mcp add --transport http wordpress https://wordpress-mcp.example.com/mcp`

Danach `list_sites` mit `check=true` aufrufen.

**Kontoseite** `https://wordpress-mcp.example.com/account`: verbundene Anwendungen eines Benutzers sehen und trennen.

### Verwaltung

```bash
docker exec <container> wordpressmcp sites          # konfigurierte Seiten (ohne Passwörter)
docker exec <container> wordpressmcp connections    # verbundene Anwendungen pro Benutzer
docker exec <container> wordpressmcp revoke kim     # alle Verbindungen eines Benutzers trennen
```

Einen Benutzer dauerhaft entfernen: aus `GATEWAY_USERS` streichen und den Stack neu deployen, seine Tokens sind dann sofort ungültig. Eine Seite sperren: Anwendungspasswort in WordPress widerrufen oder den Eintrag aus `WP_SITES` entfernen.

## Sicherheit

**Plugin**

* Nur der Benutzer `claude-mcp` darf die Abilities ausführen (Prüfung in jedem `permission_callback` und im Transport des MCP-Servers `tabside`), zusätzlich mit der passenden Capability (`edit_posts`, `edit_post`, `publish_posts`, `delete_post`, `upload_files`). Redakteursrechte genügen.
* Über die REST-API nur mit **Anwendungspasswort**, nicht mit einer Browser-Sitzung des Benutzers (abschaltbar mit dem Filter `tabside_mcp_require_application_password`).
* Nur Beiträge und Seiten. Keine Abilities für Plugins, Benutzer, Einstellungen oder Dateisystem; kein endgültiges Löschen.
* Die Abilities sind `meta.public` und damit auch über den Standard-Server des Adapters (`mcp-adapter-default-server`) sichtbar; ausführen darf sie auch dort nur `claude-mcp` (getestet).
* Schreiben nur mit `confirm=true`, vorher automatisch Sicherung.

**Gateway**

* Autorisierung nach der MCP-Spezifikation: OAuth 2.1 mit PKCE, dynamische Client-Registrierung und Client-ID-Metadata-Documents, Protected Resource Metadata, Audience-Prüfung (RFC 8707). Scopes `wordpress:read` und `wordpress:write`.
* Login mit Benutzer und Passwort aus `GATEWAY_USERS` (PBKDF2-SHA256, 600 000 Iterationen). Fehlversuche pro IP begrenzt, CSRF-Schutz, `no-store`, CSP, `X-Frame-Options: DENY`.
* Tokens und Codes nur als SHA-256-Hash in SQLite, Refresh-Token-Rotation mit Erkennung von Wiederverwendung, Access-Tokens 1 Stunde.
* Die Anwendungspasswörter der Seiten kommen nur aus der Umgebung, werden nie gespeichert, geloggt oder an Claude zurückgegeben. Verbindungen zu den Seiten nur über https.
* **Audit-Log** als JSON-Zeilen im Container-Log (`wordpressmcp.audit`): jeder Aufruf eines schreibenden Tools mit Seite, Tool, Post-ID bzw. Medien-ID, Sicherungs-ID, confirm, Ergebnis, Benutzer, Client und Zeitpunkt; dazu Logins, Fehlversuche, ausgegebene und widerrufene Tokens. Keine Passwörter, Tokens oder Inhalte.
* URL-Downloads (`media_upload`, `docx_to_content`): nur http/https ohne Zugangsdaten, alle aufgelösten Adressen müssen öffentlich sein, die Verbindung wird an die geprüfte Adresse gebunden (Host-Header und TLS-SNI bleiben der Originalname, Zertifikat wird dagegen geprüft), jede Weiterleitung wird neu geprüft, Grössenlimit beim Streamen.
* Word-Dateien: ZIP-Prüfung und Limit für die entpackte Grösse, Konvertierung ohne Ausführen von Inhalten.
* Container als uid 1000, read-only Root-Dateisystem.

## Entwicklung und Tests

```bash
pip install -r requirements.txt -e ".[dev]"
python -m pyflakes wordpressmcp tests
python -m pytest -q
```

Die Unit-Tests spielen OAuth, Weiterleitung an ein simuliertes Plugin, Sitzungserneuerung, confirm, Audit-Log, Konfiguration, Downloads und die Word-Konvertierung durch.

Der Integrationstest prüft die ganze Kette gegen ein echtes WordPress mit SQLite, MCP Adapter und dem Plugin (Entwurf mit Datum in der Zukunft, PDF- und Bild-Upload, Verlinkung, Update mit Sicherung, Rollback, Planen, Papierkorb, Fehlerfälle, fremder Benutzer):

```bash
plugin/tests/setup-wordpress.sh /tmp/wp 8871 6.9        # oder latest
PHP_CLI_SERVER_WORKERS=4 php -S 127.0.0.1:8871 -t /tmp/wp &
WP_TEST_URL=http://127.0.0.1:8871 WP_TEST_APP_PASSWORD=<APP> WP_TEST_OTHER_APP_PASSWORD=<OTHERAPP> \
  python -m pytest -q tests/test_integration_wordpress.py
```
