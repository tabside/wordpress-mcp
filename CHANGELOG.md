# Changelog

## Plugin tabside-mcp 2.4.0 / Gateway 1.3.0

* Neues Tool `wptc_repair`: repariert WP Time Capsule ohne Handarbeit im wp-admin. Diagnose (Temp-Verzeichnis vorhanden, beschreibbar, Besitzer, `index.php`; Pfad-Einstellung `backup_db_path`; laufende oder hängende Sicherung; Konto), dann über die WPTC-eigene Funktion `Config::choose_db_backup_path()` das Verzeichnis `wp-content/uploads/tCapsule/backups` anlegen (0755, über `WP_Filesystem_Direct`, Besitzer = PHP-Benutzer) und `backup_db_path` samt den übrigen Pfad-Flags setzen, `index.php` wie `Config::create_silence_file()` ablegen (eine `.htaccess` legt WPTC dort nicht an), hängende Sicherung abbrechen und zurücksetzen, mit `start_backup=true` (Vorgabe) neu starten. Der Pfad kommt immer aus `WP_CONTENT_DIR`, nie vom Aufrufer; symbolische Links im Temp-Pfad werden abgelehnt. Eine aktive, nicht hängende Sicherung nur mit `abort_running=true`, nie während einer Wiederherstellung. Die alten Pfad-Werte werden gesichert, `option_rollback` mit `backup_id` stellt sie zurück. Vorschau ohne `confirm=true`, `verify` nach dem Ausführen, Eintrag im `audit_log`, nur Administratoren.
* Fehler behoben: WPTC speichert `backup_db_path` relativ (`/wp-content/uploads`, `wptc_remove_fullpath`). Das Plugin las den Wert als absoluten Pfad und meldete das Temp-Verzeichnis deshalb als fehlend (`tmp_dir=null`), auch wenn es vorhanden war. Aufgelöst wird jetzt wie `wptc_add_fullpath()`; gültig ist das Verzeichnis nur innerhalb von `wp-content/uploads`.
* `wptc_status`: `warnings`, `tmp_dir_ok`, `tmp_dir_error`; `last_success` mit `source` (`option` oder `activity_log`) und `stale` (älter als 48 Stunden oder keine). WPTC leert `last_backup_success_complete_time` selbst nach 72 Stunden ohne Sicherung (`check_and_send_no_backup_email`), darum war `last_success` leer, obwohl es eine vollständige Sicherung gab; dann gilt jetzt der neueste Eintrag "Backup complete." im Aktivitätsprotokoll. `site_health` (Block `wptc`) ebenso.
* `wptc_backup_start` verweist bei fehlendem oder ungültigem Temp-Verzeichnis auf `wptc_repair`.

## Plugin tabside-mcp 2.3.0 / Gateway 1.2.0

* Neues Tool `wptc_status`: detaillierter Stand von WP Time Capsule. Konto und Verbindung zum WPTC-Dienst (`server_connected`, letzter Verbindungstest `cron_status`), Backup-Ziel, Speicherdauer (gesetzt und laut Konto zulässig), Zeitplan, letzte erfolgreiche Sicherung, laufende Sicherung mit letztem Lebenszeichen (`hanging` = über 60 Minuten still, gleiche Schwelle wie WPTC selbst), Warteschlange der aktuellen Sicherung, die letzten 5 Sicherungen und die neuesten Einträge des WPTC-Aktivitätsprotokolls (`log_limit`, Vorgabe 20). Nur lesend.
* Neues Tool `wptc_backup_start`: startet eine Sicherung wie BACKUP_START des WPTC-Dienstes (Einstellungen zurücksetzen, manueller Start mit Verbindungstest). Eine hängende Sicherung wird vorher abgebrochen und zurückgesetzt, eine aktive nur mit `abort_running=true`; während einer Wiederherstellung oder ohne verbundenes Konto/Ziel wird nichts gestartet. Schlägt der Verbindungstest fehl, wird der halb gestartete Zustand wieder zurückgesetzt. Vorschau ohne `confirm=true`, Eintrag im `audit_log`, nur Administratoren.

## Plugin tabside-mcp 2.2.2

* `plugin_update`, `theme_update` sowie `plugin_list`/`theme_list` mit `refresh=true` leeren vorher den Update-Cache von WordPress (wie "Erneut prüfen" im wp-admin). `wp_update_plugins()` fragt sonst höchstens alle 12 Stunden neu an, darum meldete `plugin_update` nach einem neuen Release "kein Update verfügbar". Behebt den Fall, den 2.2.1 nur zur Hälfte abgedeckt hat.

## Plugin tabside-mcp 2.2.1

* `plugin_update` für tabside-mcp und `plugin_list` mit `refresh=true` leeren vorher den Release-Zwischenspeicher des eigenen Updaters. Bisher meldeten sie bis zu 6 Stunden nach einem neuen Release noch "kein Update verfügbar".

## Plugin tabside-mcp 2.2.0

* Neues Tool `wptc_set_revision_limit` (wie im plesk-mcp): setzt bei WP Time Capsule die Speicherdauer der Sicherungen (`revision_limit` in `{prefix}wptc_options`, 1 bis 365 Tage, Vorgabe 30), nur wenn WPTC aktiv ist. Ohne `confirm=true` Vorschau mit altem und neuem Wert, danach Kontrolle durch erneutes Auslesen. Der alte Wert wird gesichert; zurückstellen mit `option_rollback` und der zurückgegebenen `backup_id`. Nur für Administratoren (`manage_options`), Eintrag im `audit_log`.
* `option_rollback` ohne `backup_id` nimmt weiterhin nur Sicherungen von Einstellungen, WPTC-Sicherungen nur mit ausdrücklicher ID. `site_health` unverändert.

## Plugin tabside-mcp 2.1.0

* `site_health` liefert neu den Block `wptc` (WP Time Capsule): aktiv, Speicherdauer in Tagen, Backup-Ziel, letzte erfolgreiche Sicherung (GMT) und deren Alter in Stunden; `null`, wenn WPTC nicht installiert ist. Damit lässt sich der Backup-Stand auch bei Seiten ausserhalb des eigenen Plesk prüfen.

## Compose

* `env_file: stack.env`: Einzelvariablen pro Seite (`WP_SITE_<KEY>_*`) kommen aus den Portainer-Stack-Variablen in den Container. Neue Seiten lassen sich ergänzen, ohne `WP_SITES` oder die Compose-Datei zu ändern.

## Plugin tabside-mcp 2.0.0 / Gateway 1.1.0

Volle WordPress-Administration über den Connector, inklusive Elementor.

**Beitragstypen und Taxonomien**

* Alle Beitragstypen mit Verwaltungsoberfläche (auch `elementor_library` und eigene wie `service`), Rechte über die Capabilities des Beitragstyps. Neu `post_type_list`.
* `post_list`: Filter `parent`, `meta_key`/`meta_value` (Elementor-Modus, Vorlagentyp, Template), `orderby`, `order`.
* `post_get`: Template, Eltern-Seite, Reihenfolge, Kommentare, alle Taxonomien, Elementor-Angaben (Version, Vorlagentyp, Anzeigebedingungen, Popup-Einstellungen).
* `post_create` / `post_update`: zusätzlich `terms`, `parent`, `menu_order`, `template`, `comment_status`.
* Neu `post_duplicate`: Kopie mit allen Zusatzfeldern (Elementor-Daten byte-genau mit neuen Element-IDs), Begriffen und Beitragsbild; Popups und Theme-Vorlagen ohne Anzeigebedingungen.
* Neu `term_list`, `term_create`, `term_update`, `term_delete` (nur ohne Zuordnung, mit Sicherung). `category_list` und `tag_list` bleiben.

**Elementor**

* Lesen: `elementor_info`, `elementor_get` (Baum mit Inhalts-Zusammenfassung, Popup- und Vorlagen-Verknüpfungen), `elementor_find`, `elementor_references`, `elementor_template_list`.
* Schreiben: `elementor_update_element`, `elementor_replace_text` (mit `expected_count`), `elementor_insert_element`, `elementor_move_element`, `elementor_remove_element`, `elementor_copy_layout` (mit `replace_popup_ids` / `replace_template_ids`), `elementor_set_conditions` (nur Pro), `elementor_page_settings_update`.
* Validierung vor dem Speichern (JSON, eindeutige IDs, registrierte Widgets, Verschachtelung, existierende Verweise, 5 MB), Speichern über die Elementor-Dokument-API, CSS-Neuaufbau, Kontrolle nach dem Speichern.
* Sicherungen enthalten alle Elementor-Meta-Felder, `post_rollback` stellt `_elementor_data` exakt wieder her. Die Sicherungsdaten liegen pro Sicherung in einem eigenen Meta-Feld.

**Navigation, Einstellungen, Erscheinungsbild**

* Menüs: `menu_list`, `menu_get`, `menu_item_create`, `menu_item_update`, `menu_item_move`, `menu_item_remove`, `menu_locations_set`, `menu_rollback`.
* Einstellungen aus einer Whitelist: `option_get`, `option_update`, `option_rollback`.
* `custom_css_get`, `custom_css_update`, `custom_css_rollback`; `widget_list`, `widget_update`, `widget_rollback`.
* Weiterleitungen (`redirect_list`, `redirect_create`, `redirect_update`), wenn das Plugin Redirection aktiv ist. Rank Math und Yoast Premium werden nicht unterstützt.

**Administration**

* Plugins: `plugin_list`, `plugin_activate`, `plugin_deactivate` (nicht `tabside-mcp`), `plugin_update`, `plugin_auto_update_set`, `plugin_install` (nur WordPress-Verzeichnis per Slug).
* Themes: `theme_list`, `theme_activate`, `theme_update`. WordPress: `core_update_check`, `core_update` (nur Minor).
* `site_health`, `cache_flush` (läuft nach jeder Änderung an Inhalten oder Darstellung automatisch).
* Benutzer: `user_list`, `user_get`, `user_update` (nur Namen, Biografie, Rolle), `application_password_list`.
* Admin-Tools laufen mit den passenden Capabilities, standardmässig nur für Administratoren. `get_version` und `list_sites(check=true)` melden `admin_tools`, Elementor- und Pro-Version.

**Sicherheit und Betrieb**

* Protokoll aller ausgeführten Änderungen im Plugin (`audit_log`, letzte 500), im Gateway mit betroffenen Beiträgen und Sicherungs-IDs.
* Plugin-Fehler ohne HTTP-Status kommen als 400 statt 500.
* Gateway: Antworten höchstens `MAX_RESPONSE_KB` (Standard 500), bei abweichender Trefferzahl von `elementor_replace_text` die Fundstellen in der Fehlermeldung, klare Meldung, wenn Elementor oder Redirection fehlt.
* Das Plugin-Release wird erst nach grünen Tests auf `main` angelegt.
* Gateway-Version: Patch-Stand zählt ab der letzten Änderung von `_VERSION_BASE` (diese Version: 1.1.0).

## Plugin tabside-mcp 1.5.0

* `post_create` / `post_update`: `hide_featured_on_single` blendet das Beitragsbild auf der Beitragsseite aus (Theme Blockchain).

## Plugin tabside-mcp 1.4.0

* `post_get` zeigt die Zusatzfelder (Post-Meta) eines Beitrags.

## Plugin tabside-mcp 1.3.0 / 1.3.1

* Automatische Updates aus den GitHub-Releases, Autor tabside.

## Plugin tabside-mcp 1.2.0

* Nicht mehr auf einen Benutzer beschränkt: jeder Benutzer mit Anwendungspasswort und Rechten.

## Plugin tabside-mcp 1.1.0 / Gateway 1.0

* Kein MCP Adapter mehr nötig, das Gateway nutzt den REST-Endpunkt des Kerns. Erste Version des Gateways.
