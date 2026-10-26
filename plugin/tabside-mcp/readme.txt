=== tabside MCP ===
Requires at least: 6.9
Requires PHP: 7.4
Stable tag: 1.4.0
License: GPLv2 or later

Beiträge, Seiten und Medien für das WordPress-MCP-Gateway.

== Beschreibung ==

Registriert Abilities der Kategorie "tabside" (Abilities API, WordPress 6.9+). Das Gateway ruft sie über
den REST-Endpunkt des Kerns auf, weitere Plugins sind nicht nötig. Optional mit dem Plugin "MCP Adapter"
zusätzlich als MCP-Server unter /wp-json/mcp/tabside.

Lesen: get-version, post-list, post-get, category-list, tag-list, media-list.
Schreiben (nur mit confirm=true, sonst Vorschau): post-create, post-update, media-upload, post-trash, post-rollback.
Vor jedem Update wird der alte Stand gesichert (Post-Meta _tabside_mcp_backups).

Ausführen darf jeder Benutzer mit den nötigen Rechten (mindestens Redakteur), der sich mit einem Anwendungspasswort
anmeldet. Beschränken auf einen Benutzer: define( 'TABSIDE_MCP_USER', '<login>' ); in der wp-config.php.
Keine Abilities für Plugins, Benutzer, Einstellungen oder Dateisystem, kein endgültiges Löschen.

== Installation ==

1. Dieses Plugin hochladen und aktivieren.
2. Beim gewünschten Benutzer unter Profil ein Anwendungspasswort erzeugen.

Updates kommen automatisch aus den GitHub-Releases von tabside/wordpress-mcp.

Bei WordPress unter 6.9 zeigt das Plugin Administratoren einen Hinweis.

== Changelog ==

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
