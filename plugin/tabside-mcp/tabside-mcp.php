<?php
/**
 * Plugin Name:       tabside MCP
 * Description:       Beiträge, Seiten und Medien für das WordPress-MCP-Gateway (Abilities API von WordPress 6.9+). Nur mit Anwendungspasswort.
 * Version:           1.2.0
 * Requires PHP:      7.4
 * Author:            KDT Solutions
 * License:           GPL-2.0-or-later
 * License URI:       https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain:       tabside-mcp
 *
 * @package tabside-mcp
 */

defined( 'ABSPATH' ) || exit;

define( 'TABSIDE_MCP_VERSION', '1.2.0' );
// Wird beim Bau des ZIP-Release durch den Commit-Hash ersetzt (.github/workflows/plugin-release.yml).
define( 'TABSIDE_MCP_COMMIT', 'dev' );
define( 'TABSIDE_MCP_MIN_WP', '6.9' );
define( 'TABSIDE_MCP_DIR', plugin_dir_path( __FILE__ ) );

require_once TABSIDE_MCP_DIR . 'includes/class-tabside-mcp-plugin.php';
require_once TABSIDE_MCP_DIR . 'includes/class-tabside-mcp-backups.php';
require_once TABSIDE_MCP_DIR . 'includes/class-tabside-mcp-abilities.php';

Tabside_MCP_Plugin::boot();
