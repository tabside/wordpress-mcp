=== tabside MCP ===
Requires at least: 6.9
Requires PHP: 7.4
Stable tag: 2.4.1
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
Administration: plugin-*, theme-*, core-update-check, core-update (nur Minor), site-health, cache-flush, wptc-set-revision-limit, wptc-status,
wptc-backup-start, wptc-repair, user-list,
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

= 2.4.1 =
* wptc-status/site-health: last_success aus dem Aktivitätsprotokoll nur noch bei exakt "Backup complete.", nicht mehr auch bei "SQL backup complete." (LIKE ohne Gross-/Kleinschreibung). Vorschau von wptc-backup-start mit demselben Wert.

= 2.4.0 =
* wptc-repair: repariert WP Time Capsule ohne wp-admin. Diagnose, Temp-Verzeichnis wp-content/uploads/tCapsule/backups mit index.php und Pfad backup_db_path über die WPTC-eigene Funktion (Config::choose_db_backup_path) anlegen, hängende Sicherung abbrechen und zurücksetzen, optional neu starten. Pfad nie vom Aufrufer, Sicherung der Pfad-Einstellungen (option-rollback mit backup_id), Vorschau, Protokoll, nur Administratoren.
* Temp-Verzeichnis richtig auflösen: WPTC speichert backup_db_path relativ (z.B. /wp-content/uploads), bisher wurde das als absoluter Pfad gelesen und das Verzeichnis fälschlich als fehlend gemeldet. Gültig ist es nur noch innerhalb von wp-content/uploads.
* wptc-status: warnings, tmp_dir_ok und tmp_dir_error; last_success mit source und stale (älter als 48 Stunden oder keine). WPTC leert last_backup_success_complete_time nach 72 Stunden ohne Sicherung, dann gilt der letzte Eintrag "Backup complete." im Aktivitätsprotokoll. Gleiches in site-health (wptc.last_success_source).
* wptc-backup-start verweist bei fehlendem Temp-Verzeichnis auf wptc-repair.

= 2.3.0 =
* wptc-status: detaillierter Stand von WP Time Capsule (Konto, Verbindung zum Dienst, Zeitplan, laufende Sicherung mit hanging-Erkennung, Warteschlange, letzte Sicherungen, Aktivitätsprotokoll).
* wptc-backup-start: Sicherung starten, hängende Sicherung vorher abbrechen (aktive nur mit abort_running). Vorschau, Protokoll, nur Administratoren.

= 2.2.2 =
* plugin-update, theme-update und plugin-list/theme-list mit refresh leeren den Update-Cache von WordPress, sonst fragt WordPress nur alle 12 Stunden neu an und meldet "kein Update verfügbar".

= 2.2.1 =
* plugin-update für tabside-mcp und plugin-list mit refresh fragen GitHub frisch ab statt die bis zu 6 Stunden alte Release-Angabe zu nutzen.

= 2.2.0 =
* wptc-set-revision-limit: Speicherdauer von WP Time Capsule setzen (1 bis 365 Tage), mit Vorschau, Kontrolle, Sicherung (option-rollback mit backup_id) und Protokoll. Nur Administratoren.

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
