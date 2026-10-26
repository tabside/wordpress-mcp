# WordPress MCP

WordPress-Seiten von Kunden über Claude (claude.ai, Cowork, Mobile-App, Claude Code) verwalten wie im wp-admin: Inhalte aller Beitragstypen, Medien, Elementor-Seiten, -Vorlagen und -Popups bis auf Widget-Ebene, Menüs, Einstellungen, Customizer-CSS, Widgets, Weiterleitungen und für Administratoren Plugins, Themes, WordPress-Updates und Benutzer. Zwei Teile:

1. **Plugin `tabside-mcp`** (`plugin/tabside-mcp`, auf jeder Kundenseite): registriert Abilities der Kategorie `tabside` über die Abilities API (WordPress-Core ab 6.9). Das Gateway ruft sie über den REST-Endpunkt des Kerns auf (`/wp-json/wp-abilities/v1/abilities/tabside/<name>/run`). Auf der Kundenseite ist nur dieses eine Plugin nötig. Ausführen darf jeder Benutzer mit den nötigen Rechten, der sich mit einem Anwendungspasswort anmeldet (z.B. der eigene Zugang); eine Browser-Anmeldung reicht nicht. Optional: Ist zusätzlich das Plugin [MCP Adapter](https://github.com/WordPress/mcp-adapter) aktiv, gibt es auch einen MCP-Server `/wp-json/mcp/tabside`; das Gateway braucht ihn nicht.
2. **Gateway `wordpress-mcp`** (dieses Repo, Docker): Remote-MCP-Server mit OAuth-Login, der in claude.ai als eigener Connector eingetragen wird. Er hält die Anwendungspasswörter der Seiten und leitet die Tool-Aufrufe an das Plugin der gewählten Seite weiter. claude.ai-Connectors können keine Anwendungspasswörter pro Seite mitschicken, darum der Umweg.

```
claude.ai ──OAuth──▶ Gateway ──Basic Auth (WordPress-Benutzer + Anwendungspasswort)──▶ https://kunde/wp-json/wp-abilities/v1/... ──▶ Abilities
```

## Tools

Jedes Tool ausser `get_version`, `list_sites` und `docx_to_content` hat den Parameter `site` (id aus `list_sites`). Die Rechte prüft das Plugin pro Ability mit der passenden WordPress-Capability: Inhalte, Elementor und Medien gehen ab Redakteur, Menüs/Widgets/CSS brauchen `edit_theme_options` bzw. `edit_css`, die Admin-Tools die Capabilities, die standardmässig nur Administratoren haben.

**Inhalte**

| Tool | Art | Beschreibung |
| --- | --- | --- |
| `list_sites` | lesen | Konfigurierte Seiten; mit `check=true` wird jede Seite angefragt (Plugin-, WordPress-, Elementor-Version, `admin_tools`, oder Fehler) |
| `get_version` | lesen | Version und Commit des Gateways, mit `site` auch des Plugins, dazu Elementor, Cache- und Weiterleitungs-Plugins, `admin_tools` |
| `post_type_list` | lesen | Alle Beitragstypen mit Verwaltungsoberfläche: Slug, URL-Präfix, Taxonomien, Elementor ja/nein, Anzahl |
| `post_list` | lesen | Beiträge eines Typs (`type` aus `post_type_list` oder `any`): `status`, `search`, `category`, `parent`, `meta_key`/`meta_value` (nur Elementor-Modus, Vorlagentyp, Template), `orderby`, `order` |
| `post_get` | lesen | Inhalt (roh), Datum, Status, Begriffe, Beitragsbild, Template, Eltern-Seite, Reihenfolge, Elementor-Angaben (Vorlagentyp, Bedingungen), Zusatzfelder, Sicherungen |
| `category_list`, `tag_list`, `term_list` | lesen | Begriffe (beliebige Taxonomie bei `term_list`), ohne `taxonomy` die Liste der Taxonomien |
| `media_list` | lesen | Mediathek mit URL, Filter `mime_type` (z.B. `application/pdf`) |
| `docx_to_content` | lesen | Word (.docx per `url` oder `data_base64`) in Gutenberg-Blöcke oder HTML umwandeln, siehe unten |
| `post_create` | schreiben | Beliebiger Beitragstyp: Titel, Inhalt (HTML oder Blöcke), Status, Datum, Kategorien, Schlagwörter, weitere Begriffe (`terms`), Beitragsbild, Auszug, Slug, Eltern, Reihenfolge, Template, Kommentare |
| `post_update` | schreiben | Gleiche Felder, nur was übergeben wird. Sichert vorher den alten Stand |
| `post_duplicate` | schreiben | Kopie mit allen Zusatzfeldern (Elementor-Daten mit neuen Element-IDs), Begriffen und Beitragsbild; Popups und Theme-Vorlagen ohne Anzeigebedingungen |
| `media_upload` | schreiben | Datei per `url` oder `data_base64` in die Mediathek, Rückgabe `media.url` zum Verlinken |
| `post_trash` | schreiben | In den Papierkorb (kein endgültiges Löschen) |
| `post_rollback` | schreiben | Sicherung zurückholen (Standard: neueste), auch Elementor-Daten exakt; der aktuelle Stand wird vorher ebenfalls gesichert |
| `term_create`, `term_update` | schreiben | Begriff anlegen bzw. Name, Slug, Beschreibung, Eltern ändern |
| `term_delete` | schreiben | Nur ohne zugeordnete Beiträge, vorher gesichert |

**Elementor** (nur wenn Elementor auf der Seite aktiv ist, sonst Meldung "Elementor ist nicht aktiv")

| Tool | Art | Beschreibung |
| --- | --- | --- |
| `elementor_info` | lesen | Elementor- und Pro-Version, Experimente (Container), Kit, globale Farben und Schriften, Breakpoints |
| `elementor_get` | lesen | Aufbau als Baum mit lesbarer Zusammenfassung; `full=true` alle Settings, `element_id` nur ein Teilbaum |
| `elementor_find` | lesen | Volltextsuche in einer Seite oder in allen Seiten, Vorlagen und Popups |
| `elementor_references` | lesen | Wo eine Vorlage oder ein Popup verwendet wird |
| `elementor_template_list` | lesen | Vorlagen nach Typ (popup, header, section, container …) mit Bedingungen und Anzahl Verwendungen |
| `elementor_update_element` | schreiben | Settings eines Elements setzen (Merge), Vorschau alt/neu pro Key |
| `elementor_replace_text` | schreiben | Text exakt ersetzen in Element, Seite oder mehreren Seiten, nur wenn die Trefferzahl `expected_count` stimmt |
| `elementor_insert_element` | schreiben | Element aus JSON oder als Kopie eines bestehenden Elements einfügen |
| `elementor_move_element`, `elementor_remove_element` | schreiben | Verschieben bzw. aus dem Aufbau entfernen |
| `elementor_copy_layout` | schreiben | Aufbau von Seite A in Seite B übernehmen, mit `replace_popup_ids` / `replace_template_ids` |
| `elementor_set_conditions` | schreiben | Anzeigebedingungen, bei Popups Auslöser und erweiterte Regeln (nur Elementor Pro) |
| `elementor_page_settings_update` | schreiben | Elementor-Seiteneinstellungen (`_elementor_page_settings`) |

**Navigation, Einstellungen, Erscheinungsbild**

| Tool | Art | Beschreibung |
| --- | --- | --- |
| `menu_list`, `menu_get` | lesen | Menüs, Positionen des Themes, Einträge als Baum |
| `menu_item_create`, `menu_item_update`, `menu_item_move`, `menu_item_remove` | schreiben | Menüeinträge (eigene URL, Seite/Beitrag, Kategorie); Entfernen = Papierkorb, Untereinträge rücken nach oben |
| `menu_locations_set` | schreiben | Menü-Positionen zuweisen |
| `menu_rollback` | schreiben | Menü oder Positionen aus Sicherung |
| `option_get`, `option_update`, `option_rollback` | lesen / schreiben | Einstellungen aus einer festen Whitelist (Allgemein, Lesen, Diskussion, Medien, Permalinks) |
| `custom_css_get`, `custom_css_update`, `custom_css_rollback` | lesen / schreiben | Zusätzliches CSS des aktiven Themes, Vorschau mit geänderten Zeilen |
| `widget_list`, `widget_update`, `widget_rollback` | lesen / schreiben | Klassische Widgets und Seitenleisten |
| `redirect_list`, `redirect_create`, `redirect_update` | lesen / schreiben | Weiterleitungen, nur wenn das Plugin Redirection aktiv ist; abschalten statt löschen |

**Administration** (Capabilities wie `activate_plugins`, `install_plugins`, `update_core`, `list_users`, standardmässig nur Administratoren)

| Tool | Art | Beschreibung |
| --- | --- | --- |
| `plugin_list` | lesen | Version, aktiv, Update verfügbar, Auto-Update |
| `plugin_activate`, `plugin_deactivate` | schreiben | Kein Löschen; `tabside-mcp` selbst lässt sich nicht deaktivieren |
| `plugin_update`, `plugin_auto_update_set` | schreiben | Aktualisieren (aktive Plugins bleiben aktiv), Auto-Update ein/aus |
| `plugin_install` | schreiben | Nur aus dem WordPress-Verzeichnis per Slug, nie aus URLs oder ZIPs |
| `theme_list`, `theme_activate`, `theme_update` | lesen / schreiben | Themes; die Vorschau von `theme_activate` warnt, dass sich die ganze Seite ändert |
| `core_update_check`, `core_update` | lesen / schreiben | WordPress-Updates, `core_update` nur Minor-Updates im gleichen Zweig |
| `site_health` | lesen | Direkte Website-Zustand-Tests, PHP, Speicher, Cron, Debug, Objekt-Cache |
| `cache_flush` | schreiben | Objekt-Cache, Elementor-CSS und erkannte Cache-Plugins |
| `user_list`, `user_get` | lesen | Benutzer mit Rolle, Anwendungspasswörtern (ohne Passwort) und letzter Nutzung |
| `user_update` | schreiben | Nur Anzeigename, Vor-/Nachname, Biografie, Rolle |
| `application_password_list` | lesen | Eigene Anwendungspasswörter (Name, erstellt, zuletzt benutzt) |
| `audit_log` | lesen | Protokoll der ausgeführten Änderungen auf der Seite (letzte 500) |

**Alle schreibenden Tools ändern nur mit `confirm=true` etwas.** Ohne `confirm` liefert das Plugin eine Vorschau (Felder, aufgelöste Kategorien, neue Schlagwörter, effektiver Status, bei Updates alt/neu pro Feld, bei CSS die geänderten Zeilen). Das confirm-Gate sitzt im Plugin selbst, gilt also auch für einen direkten Zugriff auf den MCP-Endpunkt der Seite. Nach jeder Änderung liest das Plugin den Stand neu und meldet die Kontrolle (`verify`), leert die betroffenen Caches (`cache`) und protokolliert die Änderung (`audit_log`).

Details:

* **Datum:** `YYYY-MM-DD HH:MM[:SS]` in der Zeitzone der Seite (Einstellungen > Allgemein) oder ISO 8601 mit Zeitzone. Ohne Uhrzeit gilt 00:00, die Vorschau weist darauf hin. Andere Formate (z.B. `22.09.2026`) werden abgelehnt.
* **Status:** `publish` mit Datum in der Zukunft wird `future` (geplant), `future` mit Datum in der Vergangenheit ist ein Fehler, `publish` mit Datum in der Vergangenheit veröffentlicht rückdatiert. Ein Entwurf (`draft`) behält ein gesetztes Datum.
* **Kategorien** als ID, Slug oder Name, sie müssen existieren. **Schlagwörter** als ID oder Name, fehlende Namen werden angelegt (in der Vorschau mit "(neu)"). Weitere Taxonomien über `terms` (`{"taxonomie": [...]}`), die Begriffe müssen existieren. Alles ersetzt die bisherige Zuordnung und geht nur bei Beitragstypen, die die Taxonomie haben.
* **Inhalt** wird unverändert gespeichert (Backslashes, Anführungszeichen und Block-Kommentare bleiben erhalten, im Integrationstest geprüft).
* **Sicherungen:** Vor jedem `post_update`, `post_rollback` und jeder Elementor-Änderung speichert das Plugin Titel, Inhalt, Auszug, Status, Datum, Slug, Eltern, Reihenfolge, Template, Begriffe, Beitragsbild und alle Elementor-Meta-Felder (`_elementor_data` als exakter JSON-String) im Post-Meta (Liste `_tabside_mcp_backups`, Daten pro Sicherung in `_tabside_mcp_backup_<id>`, die letzten 20, Filter `tabside_mcp_max_backups`). Menüs, Einstellungen, CSS, Widgets, Begriffe und Benutzer werden in der Option `_tabside_mcp_option_backups` gesichert (die letzten 20 pro Art). Das ist unabhängig von den WordPress-Revisionen, die manche Hostings abschalten.
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

## Elementor

Die Elementor-Tools arbeiten auf den Elementor-Daten (`_elementor_data`) von Seiten, Beiträgen, eigenen Beitragstypen mit Elementor-Unterstützung (Elementor > Einstellungen) und Vorlagen (`elementor_library`: Abschnitte, Container, Popups, Header, Footer …).

* **Lesen:** `elementor_get` liefert den Baum mit `id`, `elType`, `widgetType`, Pfad und den Inhalts-Settings (Tab "Inhalt" laut Elementor-Steuerelementen, also Texte, Links, Bilder, Icons, ohne Styles) sowie den verknüpften `popups` und `templates`. Erkannt werden Popup-Links (`#elementor-action:action=popup:open&settings=…`, auch URL-kodiert), dynamische Popup-Tags, Vorlagen-Widgets, globale Widgets und `[elementor-template id="…"]`. `full=true` gibt alle Settings, bei mehr als 300 KB nur die Zusammenfassung mit Hinweis (dann mit `element_id` einen Teilbaum holen). Das Gateway gibt nie mehr als `MAX_RESPONSE_KB` zurück.
* **Schreiben:** Jede Änderung wird vor dem Speichern geprüft: gültiges JSON, eindeutige IDs, registrierte Element- und Widget-Typen, erlaubte Verschachtelung (keine Widgets auf oberster Ebene, Spalten nur in Sections), alle verknüpften Popups und Vorlagen existieren, höchstens 5 MB (Filter `tabside_mcp_elementor_max_bytes`). Gespeichert wird über die Elementor-Dokument-API (`documents->get( $id )->save()`), damit Elementor Revisionen, CSS und Caches selbst behandelt. Nur für Dokumenttypen, die Elementor ohne Pro nicht kennt (z.B. Popups), direkt ins Meta mit `wp_slash( wp_json_encode() )`. Danach wird die Elementor-CSS-Datei der Seite neu erzeugt (`cache.elementor_css`) und mit dem gespeicherten Stand verglichen (`verify.equal`).
* **Texte ersetzen:** `elementor_replace_text` ersetzt nur in den Text-Werten der Settings (nie im rohen JSON, also keine kaputten Escapes; `__dynamic__` und `__globals__` bleiben unberührt) und nur, wenn die Trefferzahl `expected_count` stimmt. Sonst ändert sich nichts und die Fundstellen kommen zurück.
* **Kopieren:** `post_duplicate` kopiert alle Meta-Felder byte-genau und vergibt neue 8-stellige Element-IDs; Popups und Theme-Vorlagen bekommen keine Anzeigebedingungen, damit die Kopie nicht sofort erscheint. `elementor_copy_layout` überträgt den Aufbau einer Seite auf eine andere (auch auf einen anderen Beitragstyp) und ersetzt dabei Popup- und Vorlagen-IDs nach `replace_popup_ids` / `replace_template_ids`.
* **Rückgängig:** `post_rollback` stellt die Elementor-Meta-Felder exakt wieder her (`verify.elementor_exact`).
* **Elementor Pro:** Anzeigebedingungen, Popup-Auslöser und das Rendern von Vorlagen-Widgets gibt es nur mit Pro. `elementor_set_conditions` schreibt `_elementor_conditions` und `_elementor_popup_display_settings` und lässt den Bedingungs-Cache von Pro neu erzeugen; mangels Pro-Lizenz ist das nicht im Integrationstest abgedeckt.

Ablauf "Seite X wie Seite Y, mit eigenen Popups": `post_duplicate` für jedes Popup der Vorlage, `elementor_copy_layout` von Y nach X mit `replace_popup_ids` (alte -> neue Popup-IDs), dann `elementor_find` / `elementor_replace_text` für die Texte in Seite und Popups, zum Schluss `elementor_references` zur Kontrolle.

## Plugin auf einer Kundenseite installieren

Voraussetzungen: WordPress **6.9 oder neuer** (Abilities API im Core), HTTPS (sonst bietet WordPress keine Anwendungspasswörter an), Pretty Permalinks oder `rest_url` mit `?rest_route=` (siehe unten).

1. Plugin **tabside-mcp** über Plugins > Installieren > Plugin hochladen installieren und aktivieren: ZIP aus den [Releases](../../releases) dieses Repos (`tabside-mcp-<version>.zip`).
2. Beim WordPress-Benutzer, unter dem die Änderungen laufen sollen (Redakteur für Inhalte, Administrator für die Admin-Tools), unter Benutzer > Profil > Anwendungspasswörter ein Passwort "wordpress-mcp" erzeugen und sofort notieren, WordPress zeigt es nur einmal. Neue Beiträge haben diesen Benutzer als Autor.
3. Seite im Gateway eintragen (`WP_SITES`, siehe unten) und mit `list_sites` (`check=true`) prüfen.

Bei WordPress unter 6.9 bleibt das Plugin inaktiv und zeigt Administratoren einen Hinweis. Auf einen einzigen Benutzer beschränken lässt es sich mit `define( 'TABSIDE_MCP_USER', '<login>' );` in der `wp-config.php` oder dem Filter `tabside_mcp_allowed_user`.

**Updates kommen automatisch.** Das Plugin hat ein eigenes `Update URI` und fragt alle 6 Stunden die GitHub-Releases dieses Repos ab (Tag `plugin-v<Version>`, Anhang `tabside-mcp-<Version>.zip`). Eine neuere Version erscheint wie jedes andere Update unter Plugins bzw. Dashboard > Aktualisierungen und wird von WordPress automatisch installiert (WP-Cron, mit der eingebauten Absturzprüfung und Rückfall auf die alte Version). Nur Hinweis statt automatischer Installation: `define( 'TABSIDE_MCP_DISABLE_AUTO_UPDATE', true );` in der `wp-config.php`. Die Updatefunktion gibt es ab Version 1.3.0; ältere Versionen einmal von Hand ersetzen.

**Neue Version ausliefern:** Version im Plugin-Header und in `TABSIDE_MCP_VERSION` erhöhen und auf `main` pushen. Sobald die Tests grün sind, legt der Workflow "Plugin-ZIP bauen" das Release `plugin-v<Version>` mit dem ZIP an (Commit-Hash steht danach in `get_version`). Ohne Versionserhöhung wird nur ein Actions-Artefakt gebaut, kein Update verteilt. Änderungen siehe [CHANGELOG.md](CHANGELOG.md).

## Gateway betreiben

Das Image wird bei jedem Push auf `main` von GitHub Actions gebaut (Lint, Tests, Plugin-Integrationstest gegen WordPress 6.9 und die aktuelle Version, Smoke-Test) und nach `ghcr.io/tabside/wordpress-mcp` veröffentlicht (`latest`, Commit-SHA, Version). Einmalig nach dem ersten Push das Package auf GitHub unter Packages > Package settings auf **Public** stellen, sonst kann Portainer nicht ohne Zugangsdaten pullen.

1. Login-Benutzer anlegen: `docker run --rm -i ghcr.io/tabside/wordpress-mcp wordpressmcp hash-password` (Passwort mindestens 12 Zeichen eingeben), Ausgabe als `GATEWAY_USERS=kim=<hash>` eintragen. Mehrere Benutzer mit Komma trennen.
2. In Portainer **Stacks > Add stack > Build method: Repository**, dieses Repo, Branch `main`, Compose-Pfad `docker-compose.yml`. Unter Environment variables die Werte aus `.env.example` setzen. Die Anwendungspasswörter stehen nur dort in `WP_SITES`, nie im Repo.
3. DNS-Eintrag für die Subdomain und Proxy-Host im Nginx Proxy Manager auf `<Host-IP>:8440` (bzw. `MCP_HOST_PORT`) mit TLS-Zertifikat, `MCP_BIND_ADDR` auf die Host-IP setzen, über die NPM den Container erreicht. Unter einem Pfad eines bestehenden Hosts siehe [Reverse-Proxy mit Pfad](#reverse-proxy-mit-pfad).
4. Prüfen:

```bash
curl -s https://wordpress-mcp.example.com/healthz
curl -s https://wordpress-mcp.example.com/.well-known/oauth-protected-resource/mcp
curl -s https://wordpress-mcp.example.com/.well-known/oauth-authorization-server
curl -si -X POST https://wordpress-mcp.example.com/mcp   # 401 mit WWW-Authenticate: Bearer resource_metadata=...
```

### Reverse-Proxy mit Pfad

Bei `PUBLIC_BASE_URL=https://mcp.example.com/wordpress` müssen der Pfad `/wordpress/` **ohne Umschreiben** und die drei Well-known-Pfade mit dem Suffix `/wordpress` an den Container gehen (Advanced Config des Proxy-Hosts im Nginx Proxy Manager):

```nginx
location ~ ^(/wordpress(/|$)|/\.well-known/(oauth-authorization-server|openid-configuration)/wordpress$|/\.well-known/oauth-protected-resource/wordpress/mcp$) {
    proxy_pass http://<Host-IP>:8440;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_read_timeout 300s;
    client_max_body_size 32m;
}
```

### Variablen

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `PUBLIC_BASE_URL` | – | Öffentliche URL, z.B. `https://wordpress-mcp.example.com` |
| `GATEWAY_USERS` | – | `name=<hash>`, kommagetrennt (`wordpressmcp hash-password`) |
| `WP_SITES` | leer | JSON-Liste der Seiten, siehe unten. Leer startet das Gateway trotzdem (Warnung im Log). Alternativ `WP_SITES_FILE` (Pfad, z.B. Docker-Secret) oder pro Seite `WP_SITE_<KEY>_URL`, `_APP_PASSWORD` (bzw. `_APP_PASSWORD_FILE`), `_USER`, `_LABEL`, `_REST_URL` |
| `SERVICE_NAME` | `WordPress MCP` | Name auf Login- und Kontoseite |
| `ACCESS_TOKEN_TTL` / `REFRESH_TOKEN_TTL` | 3600 / 2592000 | Gültigkeit in Sekunden |
| `TOOL_CALLS_PER_MINUTE` | 120 | pro Benutzer |
| `LOGIN_FAILURES_PER_IP` / `LOGIN_FAILURE_WINDOW` | 10 / 900 | Sperre nach Fehlversuchen |
| `WP_TIMEOUT` | 60 | Sekunden pro Anfrage an eine Seite |
| `MAX_FILE_MB` | 20 | Maximale Grösse für `media_upload` und `docx_to_content` |
| `MAX_RESPONSE_KB` | 500 | Maximale Antwortgrösse eines Tools, grössere Antworten werden mit Hinweis zum Eingrenzen abgelehnt |
| `MCP_BIND_ADDR` / `MCP_HOST_PORT` | 127.0.0.1 / 8440 | veröffentlichter Port (Compose) |
| `TRUSTED_PROXIES` | `*` | Proxies, deren `X-Forwarded-*` übernommen wird |

`WP_SITES` (eine Zeile):

```json
[{"id":"kunde","url":"https://www.example.com","app_password":"xxxx xxxx xxxx xxxx xxxx xxxx","label":"Kunde AG"},
 {"id":"zweite","url":"https://www.example.org","app_password":"...","user":"redaktion","rest_url":"https://www.example.org/?rest_route="}]
```

Weitere Seiten lassen sich auch ohne Anfassen von `WP_SITES` ergänzen, mit einem Block Stack-Variablen pro Seite (`KEY` aus A-Z, 0-9, `_`; die `site`-id ist `KEY` klein geschrieben mit `-` statt `_`):

```
WP_SITE_KUNDE_URL=https://www.example.com
WP_SITE_KUNDE_USER=redaktion
WP_SITE_KUNDE_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
WP_SITE_KUNDE_LABEL=Kunde AG
```

Portainer legt alle Stack-Variablen in `stack.env` ab, die Compose-Datei bindet sie per `env_file` ein. Eine neue Seite braucht so nur neue Variablen und ein Neuausrollen des Stacks. Ausserhalb von Portainer (`docker compose` von Hand) eine `stack.env` neben die Compose-Datei legen (darf leer sein).

`id` (a-z, 0-9, -) ist der Wert für `site`. `user` (Pflicht) ist der WordPress-Benutzer des Anwendungspassworts, `rest_url` standardmässig `<url>/wp-json` (bei einfachen Permalinks `<url>/?rest_route=`). Nur https (http nur für localhost).

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

* Jede Ability prüft im `permission_callback` die passende Capability des angemeldeten Benutzers mit `current_user_can()`, nie pauschal: Beiträge über die Capabilities des Beitragstyps (`edit_post`, `publish_posts`, `delete_post` …), Begriffe über die der Taxonomie, Menüs und Widgets `edit_theme_options`, CSS `edit_css`, Einstellungen `manage_options`, Plugins `activate_plugins` / `update_plugins` / `install_plugins`, Themes `switch_themes` / `update_themes`, WordPress `update_core`, Benutzer `list_users` / `edit_user` / `promote_user`, Website-Zustand `view_site_health_checks`.
* **Admin-Tools** (Plugins, Themes, Core, Einstellungen, Benutzer) laufen nur mit diesen Capabilities, in WordPress standardmässig nur für Administratoren. Ein Redakteur erhält "Fehlende Berechtigung" (im Integrationstest geprüft). `get_version` bzw. `list_sites(check=true)` zeigen das als `admin_tools: enabled/disabled`. Optional lassen sich alle Abilities mit `define( 'TABSIDE_MCP_USER', '<login>' );` auf einen Benutzer beschränken.
* Über die REST-API nur mit **Anwendungspasswort**, nicht mit einer Browser-Sitzung des Benutzers (abschaltbar mit dem Filter `tabside_mcp_require_application_password`).
* **Feste Grenzen:** keine PHP-Ausführung, kein `eval`, kein Datei-Editor, keine beliebigen SQL-Abfragen, keine Datei-Schreibzugriffe ausserhalb der Mediathek (ausser den WordPress-eigenen Upgradern für Plugin-, Theme- und Core-Updates). Nie endgültig löschen: Beiträge in den Papierkorb, Plugins nur deaktivieren, Benutzer nicht löschen, Weiterleitungen nur abschalten, Begriffe nur ohne Zuordnung und mit Sicherung. Plugins nur aus dem WordPress-Verzeichnis per Slug. `tabside-mcp` lässt sich nicht deaktivieren. Bei Benutzern nur Anzeigename, Vor-/Nachname, Biografie und Rolle; Rolle `administrator` und Änderungen an Administratoren nur durch Administratoren, die eigene Rolle nie.
* **Einstellungen** nur aus einer Whitelist (Filter `tabside_mcp_option_whitelist`). Nie, auch nicht per Filter: `siteurl`, `home`, `admin_email`, `users_can_register`, `default_role`, `active_plugins`, `template`, `stylesheet` und alle Namen mit key, token, secret, pass, auth, salt, nonce, license, credential oder api.
* **Protokoll:** Jede ausgeführte Änderung wird mit Benutzer, Ability, Ziel, Sicherungs-ID und Zeitpunkt in der Option `_tabside_mcp_audit_log` festgehalten (letzte 500), lesbar mit `audit_log` (Administratoren alles, andere die eigenen Einträge). Werte von Einstellungen werden dort nicht gespeichert, nur ihre Namen.
* Die Abilities sind `meta.public` (REST-API des Kerns, bei installiertem MCP Adapter auch dessen Standard-Server); ausführen kann sie nur, wer mit Anwendungspasswort angemeldet ist und die Rechte hat (getestet: Redakteur ja, Abonnent nein).
* Schreiben nur mit `confirm=true`, vorher automatisch Sicherung, danach Kontrolle und Cache leeren.

**Gateway**

* Autorisierung nach der MCP-Spezifikation: OAuth 2.1 mit PKCE, dynamische Client-Registrierung und Client-ID-Metadata-Documents, Protected Resource Metadata, Audience-Prüfung (RFC 8707). Scopes `wordpress:read` und `wordpress:write`.
* Login mit Benutzer und Passwort aus `GATEWAY_USERS` (PBKDF2-SHA256, 600 000 Iterationen). Fehlversuche pro IP begrenzt, CSRF-Schutz, `no-store`, CSP, `X-Frame-Options: DENY`.
* Tokens und Codes nur als SHA-256-Hash in SQLite, Refresh-Token-Rotation mit Erkennung von Wiederverwendung, Access-Tokens 1 Stunde.
* Die Anwendungspasswörter der Seiten kommen nur aus der Umgebung, werden nie gespeichert, geloggt oder an Claude zurückgegeben. Verbindungen zu den Seiten nur über https.
* **Audit-Log** als JSON-Zeilen im Container-Log (`wordpressmcp.audit`): jeder Aufruf eines schreibenden Tools mit Seite, Tool, Ziel (Post-ID, betroffene Beiträge, Medien-ID, Element, Plugin, Theme, Menü, Benutzer …), Sicherungs-IDs, confirm, Ergebnis, Benutzer, Client und Zeitpunkt; dazu Logins, Fehlversuche, ausgegebene und widerrufene Tokens. Keine Passwörter, Tokens oder Inhalte.
* URL-Downloads (`media_upload`, `docx_to_content`): nur http/https ohne Zugangsdaten, alle aufgelösten Adressen müssen öffentlich sein, die Verbindung wird an die geprüfte Adresse gebunden (Host-Header und TLS-SNI bleiben der Originalname, Zertifikat wird dagegen geprüft), jede Weiterleitung wird neu geprüft, Grössenlimit beim Streamen.
* Word-Dateien: ZIP-Prüfung und Limit für die entpackte Grösse, Konvertierung ohne Ausführen von Inhalten.
* Container als uid 1000, read-only Root-Dateisystem.

## Entwicklung und Tests

```bash
pip install -r requirements.txt -e ".[dev]"
python -m pyflakes wordpressmcp tests
python -m pytest -q
```

Die Unit-Tests spielen OAuth, Weiterleitung an ein simuliertes Plugin (GET für lesende, POST für schreibende Abilities, für jedes Tool), Schemas, Sitzungserneuerung, confirm, Fehlermeldungen, Antwort-Grössenlimit, Audit-Log, Konfiguration, Downloads und die Word-Konvertierung durch. Ein Test vergleicht die Abilities im Plugin-Code mit den Tools des Gateways.

Der Integrationstest prüft die ganze Kette gegen ein echtes WordPress mit SQLite, Elementor und Redirection, ohne MCP Adapter, in CI mit WordPress 6.9 und der aktuellen Version: Entwurf mit Datum in der Zukunft, Uploads, Update mit Sicherung, Rollback, Planen, Papierkorb, Fehlerfälle; Elementor-Seite mit Container, Überschrift, Text mit Sonderzeichen, Icon-Box mit Popup-Link: Duplizieren von Seite und Popup ohne Datenverlust und Escape-Fehler, Seite rendert ohne PHP-Fehler mit den Texten, `elementor_replace_text` mit `expected_count`, `elementor_copy_layout` mit Popup-Zuordnung auf den eigenen Beitragstyp `service`, Rollback auf den exakten JSON-Stand, CSS-Datei vorhanden; Element-Operationen; Sicherheitsregeln (Redakteur ohne Admin-Tools, Whitelist, Sperren); Menüs, Einstellungen, CSS, Widgets, Weiterleitungen, Plugins, Website-Zustand, Protokoll.

```bash
plugin/tests/setup-wordpress.sh /tmp/wp 8871 6.9 > /tmp/wp.txt   # oder latest
PHP_CLI_SERVER_WORKERS=4 php -S 127.0.0.1:8871 -t /tmp/wp &
WP_TEST_URL=http://127.0.0.1:8871 WP_TEST_APP_PASSWORD=<APP> WP_TEST_OTHER_APP_PASSWORD=<OTHERAPP> \
  WP_TEST_READER_APP_PASSWORD=<READERAPP> WP_TEST_ADMIN_APP_PASSWORD=<ADMINAPP> \
  python -m pytest -q tests/test_integration_wordpress.py
```

Das Plugin-Release (`plugin-v<Version>`) entsteht erst, wenn dieser Testlauf auf `main` grün ist.
