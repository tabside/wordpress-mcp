=== tabside MCP ===
Requires at least: 6.9
Requires PHP: 7.4
Stable tag: 1.1.0
License: GPLv2 or later

Beiträge, Seiten und Medien für das WordPress-MCP-Gateway.

== Beschreibung ==

Registriert Abilities der Kategorie "tabside" (Abilities API, WordPress 6.9+). Das Gateway ruft sie über
den REST-Endpunkt des Kerns auf, weitere Plugins sind nicht nötig. Optional mit dem Plugin "MCP Adapter"
zusätzlich als MCP-Server unter /wp-json/mcp/tabside.

Lesen: get-version, post-list, post-get, category-list, tag-list, media-list.
Schreiben (nur mit confirm=true, sonst Vorschau): post-create, post-update, media-upload, post-trash, post-rollback.
Vor jedem Update wird der alte Stand gesichert (Post-Meta _tabside_mcp_backups).

Ausführen darf nur der Benutzer "claude-mcp" (Rolle Redakteur) mit Anwendungspasswort.
Keine Abilities für Plugins, Benutzer, Einstellungen oder Dateisystem, kein endgültiges Löschen.

== Installation ==

1. Dieses Plugin hochladen und aktivieren.
2. Benutzer "claude-mcp" mit der Rolle Redakteur anlegen und unter Profil ein Anwendungspasswort erzeugen.

Bei WordPress unter 6.9 oder fehlendem Benutzer zeigt das Plugin Administratoren einen Hinweis.

== Changelog ==

= 1.1.0 =
* MCP Adapter nicht mehr nötig, das Gateway nutzt den REST-Endpunkt des Kerns.

= 1.0.0 =
* Erste Version.
