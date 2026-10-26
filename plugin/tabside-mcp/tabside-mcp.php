<?php
/**
 * Plugin Name:       tabside MCP
 * Description:       WordPress-Seite über das WordPress-MCP-Gateway verwalten: Inhalte aller Beitragstypen, Elementor, Menüs, Einstellungen, Plugins, Themes, Benutzer (Abilities API von WordPress 6.9+). Nur mit Anwendungspasswort.
 * Version:           2.0.0
 * Update URI:        https://github.com/tabside/wordpress-mcp
 * Requires PHP:      7.4
 * Author:            tabside
 * License:           GPL-2.0-or-later
 * License URI:       https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain:       tabside-mcp
 *
 * @package tabside-mcp
 */

defined( 'ABSPATH' ) || exit;

define( 'TABSIDE_MCP_VERSION', '2.0.0' );
// Wird beim Bau des ZIP-Release durch den Commit-Hash ersetzt (.github/workflows/plugin-release.yml).
define( 'TABSIDE_MCP_COMMIT', 'dev' );
define( 'TABSIDE_MCP_MIN_WP', '6.9' );
define( 'TABSIDE_MCP_DIR', plugin_dir_path( __FILE__ ) );

require_once TABSIDE_MCP_DIR . 'includes/class-tabside-mcp-plugin.php';
require_once TABSIDE_MCP_DIR . 'includes/class-tabside-mcp-backups.php';
require_once TABSIDE_MCP_DIR . 'includes/class-tabside-mcp-store.php';
require_once TABSIDE_MCP_DIR . 'includes/class-tabside-mcp-cache.php';
require_once TABSIDE_MCP_DIR . 'includes/class-tabside-mcp-abilities.php';
require_once TABSIDE_MCP_DIR . 'includes/class-tabside-mcp-elementor.php';
require_once TABSIDE_MCP_DIR . 'includes/class-tabside-mcp-site.php';
require_once TABSIDE_MCP_DIR . 'includes/class-tabside-mcp-admin.php';
require_once TABSIDE_MCP_DIR . 'includes/class-tabside-mcp-updater.php';

// Updates auch dann, wenn das Plugin wegen einer zu alten WordPress-Version inaktiv ist.
Tabside_MCP_Updater::boot();

Tabside_MCP_Plugin::boot();
