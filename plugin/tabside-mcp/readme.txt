=== tabside MCP ===
Requires at least: 6.9
Requires PHP: 7.4
Stable tag: 1.0.0
License: GPLv2 or later

Abilities für Beiträge, Seiten und Medien, über den WordPress MCP Adapter als MCP-Server "tabside" erreichbar.

== Beschreibung ==

Registriert Abilities der Kategorie "tabside" (Abilities API, WordPress 6.9+) und einen MCP-Server
unter /wp-json/mcp/tabside (benötigt das Plugin "MCP Adapter").

Lesen: get-version, post-list, post-get, category-list, tag-list, media-list.
Schreiben (nur mit confirm=true, sonst Vorschau): post-create, post-update, media-upload, post-trash, post-rollback.
Vor jedem Update wird der alte Stand gesichert (Post-Meta _tabside_mcp_backups).

Ausführen darf nur der Benutzer "claude-mcp" (Rolle Redakteur) mit Anwendungspasswort.
Keine Abilities für Plugins, Benutzer, Einstellungen oder Dateisystem, kein endgültiges Löschen.

== Installation ==

1. Plugin "MCP Adapter" installieren und aktivieren (https://github.com/WordPress/mcp-adapter/releases/latest).
2. Dieses Plugin hochladen und aktivieren.
3. Benutzer "claude-mcp" mit der Rolle Redakteur anlegen und unter Profil ein Anwendungspasswort erzeugen.

Bei WordPress unter 6.9, fehlendem MCP Adapter oder fehlendem Benutzer zeigt das Plugin Administratoren einen Hinweis.

== Changelog ==

= 1.0.0 =
* Erste Version.
