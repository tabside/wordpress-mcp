=== tabside MCP ===
Requires at least: 6.9
Requires PHP: 7.4
Stable tag: 2.0.0
License: GPLv2 or later

WordPress-Seite über das WordPress-MCP-Gateway verwalten: Inhalte, Elementor, Menüs, Einstellungen, Plugins, Themes, Benutzer.

== Beschreibung ==

Registriert Abilities der Kategorie "tabside" (Abilities API, WordPress 6.9+). Das Gateway ruft sie über
den REST-Endpunkt des Kerns auf, weitere Plugins sind nicht nötig. Optional mit dem Plugin "MCP Adapter"
zusätzlich als MCP-Server unter /wp-json/mcp/tabside.

Inhalte: get-version, post-type-list, post-list, post-get, category-list, tag-list, term-list, media-list, post-create,
post-update, post-duplicate, media-upload, post-trash, post-rollback, term-create, term-update, term-delete.
Elementor (wenn aktiv): elementor-info, -get, -find, -references, -template-list, -update-element, -replace-text,
-insert-element, -move-element, -remove-element, -copy-layout, -set-conditions (Pro), -page-settings-update.
Navigation und Einstellungen: menu-*, option-get/-update/-rollback (Whitelist), custom-css-*, widget-*, redirect-* (Redirection).
Administration: plugin-*, theme-*, core-update-check, core-update (nur Minor), site-health, cache-flush, user-list,
user-get, user-update, application-password-list, audit-log.

Schreibende Abilities ändern nur mit confirm=true, sonst Vorschau. Vorher wird gesichert (Beiträge und Elementor im
Post-Meta, Menüs, Einstellungen, CSS, Widgets in der Option _tabside_mcp_option_backups), danach geprüft, Caches geleert
und protokolliert (audit-log, letzte 500).

Rechte pro Ability über die passende Capability (current_user_can), Admin-Abilities standardmässig nur für Administratoren.
Anmeldung über die REST-API nur mit Anwendungspasswort. Beschränken auf einen Benutzer: define( 'TABSIDE_MCP_USER', '<login>' );
Nie endgültig löschen, keine PHP-Ausführung, kein Datei-Editor, keine SQL-Abfragen, Plugins nur aus dem WordPress-Verzeichnis.

== Installation ==

1. Dieses Plugin hochladen und aktivieren.
2. Beim gewünschten Benutzer unter Profil ein Anwendungspasswort erzeugen.

Updates kommen automatisch aus den GitHub-Releases von tabside/wordpress-mcp.

Bei WordPress unter 6.9 zeigt das Plugin Administratoren einen Hinweis.

== Changelog ==

= 2.0.0 =
* Volle Administration: alle Beitragstypen, post-duplicate, Begriffe, Elementor bis auf Widget-Ebene, Menüs, Einstellungen (Whitelist), Customizer-CSS, Widgets, Weiterleitungen (Redirection), Plugins, Themes, Core-Minor-Updates, Website-Zustand, Cache, Benutzer, Protokoll. Details in CHANGELOG.md im Repo.

= 1.5.0 =
* post-create/post-update: hide_featured_on_single blendet das Beitragsbild auf der Beitragsseite aus (Theme Blockchain, Schlüssel per Filter tabside_mcp_hide_featured_meta_key anpassbar). Wird gesichert und beim Rollback wiederhergestellt.

= 1.4.0 =
* post-get zeigt die Zusatzfelder (Post-Meta) eines Beitrags, z.B. Theme-Optionen.

= 1.3.1 =
* Autor: tabside.

= 1.3.0 =
* Automatische Updates aus den GitHub-Releases (abschaltbar mit TABSIDE_MCP_DISABLE_AUTO_UPDATE).

= 1.2.0 =
* Nicht mehr auf den Benutzer claude-mcp beschränkt: jeder Benutzer mit Anwendungspasswort und Rechten.

= 1.1.0 =
* MCP Adapter nicht mehr nötig, das Gateway nutzt den REST-Endpunkt des Kerns.

= 1.0.0 =
* Erste Version.
