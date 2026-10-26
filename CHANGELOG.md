# Changelog

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
