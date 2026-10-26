<?php
/**
 * Administration: Plugins, Themes, Core-Updates, Website-Zustand, Cache, Benutzer, Anwendungspasswörter, Protokoll.
 *
 * Jede Ability prüft die passende Capability (activate_plugins, install_plugins, update_core, list_users ...),
 * die in WordPress standardmässig nur Administratoren haben. Kein Löschen von Plugins, Themes oder Benutzern,
 * Installation nur aus dem WordPress-Verzeichnis per Slug.
 *
 * @package tabside-mcp
 */

defined( 'ABSPATH' ) || exit;

final class Tabside_MCP_Admin {

	const SELF_PLUGIN = 'tabside-mcp/tabside-mcp.php';

	/**
	 * Admin-Abilities verfügbar (Rolle Administrator bzw. manage_options)?
	 */
	public static function available() {
		return current_user_can( 'manage_options' );
	}

	/**
	 * @return array<string, array<string, mixed>>
	 */
	public static function definitions() {
		$confirm = Tabside_MCP_Abilities::confirm_schema();
		$cap     = static function ( $capability ) {
			return static function () use ( $capability ) {
				return Tabside_MCP_Plugin::check_user( $capability );
			};
		};
		$plugin  = array(
			'type'        => 'string',
			'description' => 'Plugin-Datei aus plugin-list (z.B. redirection/redirection.php) oder Verzeichnis-Slug (redirection).',
		);
		$theme   = array(
			'type'        => 'string',
			'description' => 'Theme-Verzeichnis (stylesheet) aus theme-list.',
		);
		$refresh = array(
			'type'        => 'boolean',
			'default'     => false,
			'description' => 'Vorher bei wordpress.org nach Updates fragen.',
		);
		$admin_note = ' Admin-Ability: Vorschau zuerst dem Benutzer zeigen, confirm=true erst nach Bestätigung.';

		return array(
			'plugin-list'             => array(
				'label'       => 'Plugins auflisten',
				'description' => 'Installierte Plugins mit Version, aktiv, verfügbarem Update und Auto-Update.',
				'readonly'    => true,
				'properties'  => array( 'refresh' => $refresh ),
				'permission'  => $cap( 'activate_plugins' ),
				'execute'     => array( __CLASS__, 'plugin_list' ),
			),
			'plugin-activate'         => array(
				'label'       => 'Plugin aktivieren',
				'description' => 'Aktiviert ein installiertes Plugin. Ohne confirm=true nur Vorschau.' . $admin_note,
				'flush'       => 'site',
				'properties'  => array(
					'plugin'  => $plugin,
					'confirm' => $confirm,
				),
				'required'    => array( 'plugin' ),
				'permission'  => $cap( 'activate_plugins' ),
				'execute'     => array( __CLASS__, 'plugin_activate' ),
			),
			'plugin-deactivate'       => array(
				'label'       => 'Plugin deaktivieren',
				'description' => 'Deaktiviert ein Plugin (kein Löschen). tabside-mcp selbst lässt sich nicht deaktivieren. Ohne confirm=true nur Vorschau.' . $admin_note,
				'destructive' => true,
				'flush'       => 'site',
				'properties'  => array(
					'plugin'  => $plugin,
					'confirm' => $confirm,
				),
				'required'    => array( 'plugin' ),
				'permission'  => $cap( 'activate_plugins' ),
				'execute'     => array( __CLASS__, 'plugin_deactivate' ),
			),
			'plugin-update'           => array(
				'label'       => 'Plugin aktualisieren',
				'description' => 'Aktualisiert ein Plugin auf die verfügbare Version (aktive Plugins bleiben aktiv). Ohne confirm=true nur Vorschau.' . $admin_note,
				'flush'       => 'site',
				'properties'  => array(
					'plugin'  => $plugin,
					'confirm' => $confirm,
				),
				'required'    => array( 'plugin' ),
				'permission'  => $cap( 'update_plugins' ),
				'execute'     => array( __CLASS__, 'plugin_update' ),
			),
			'plugin-auto-update-set'  => array(
				'label'       => 'Plugin-Auto-Update',
				'description' => 'Schaltet automatische Updates eines Plugins ein oder aus. Ohne confirm=true nur Vorschau.' . $admin_note,
				'properties'  => array(
					'plugin'  => $plugin,
					'enabled' => array( 'type' => 'boolean' ),
					'confirm' => $confirm,
				),
				'required'    => array( 'plugin', 'enabled' ),
				'permission'  => $cap( 'update_plugins' ),
				'execute'     => array( __CLASS__, 'plugin_auto_update_set' ),
			),
			'plugin-install'          => array(
				'label'       => 'Plugin installieren',
				'description' => 'Installiert ein Plugin aus dem WordPress-Verzeichnis (wordpress.org/plugins) per Slug, nie aus anderen Quellen. Optional gleich aktivieren. Ohne confirm=true nur Vorschau mit Angaben aus dem Verzeichnis.' . $admin_note,
				'flush'       => 'site',
				'properties'  => array(
					'slug'     => array(
						'type'        => 'string',
						'pattern'     => '^[a-z0-9][a-z0-9-]*$',
						'description' => 'Slug aus der Adresse wordpress.org/plugins/<slug>/.',
					),
					'activate' => array(
						'type'    => 'boolean',
						'default' => false,
					),
					'confirm'  => $confirm,
				),
				'required'    => array( 'slug' ),
				'permission'  => static function ( $input ) {
					$ok = Tabside_MCP_Plugin::check_user( 'install_plugins' );
					if ( true === $ok && ! empty( $input['activate'] ) ) {
						$ok = Tabside_MCP_Plugin::check_user( 'activate_plugins' );
					}
					return $ok;
				},
				'execute'     => array( __CLASS__, 'plugin_install' ),
			),
			'theme-list'              => array(
				'label'       => 'Themes auflisten',
				'description' => 'Installierte Themes mit Version, aktiv, Eltern-Theme, verfügbarem Update und Auto-Update.',
				'readonly'    => true,
				'properties'  => array( 'refresh' => $refresh ),
				'permission'  => $cap( 'switch_themes' ),
				'execute'     => array( __CLASS__, 'theme_list' ),
			),
			'theme-activate'          => array(
				'label'       => 'Theme aktivieren',
				'description' => 'Wechselt das aktive Theme. Achtung: die ganze Seite ändert ihr Aussehen, Menü-Positionen und Widgets können sich verschieben. Ohne confirm=true nur Vorschau.' . $admin_note,
				'flush'       => 'site',
				'properties'  => array(
					'theme'   => $theme,
					'confirm' => $confirm,
				),
				'required'    => array( 'theme' ),
				'permission'  => $cap( 'switch_themes' ),
				'execute'     => array( __CLASS__, 'theme_activate' ),
			),
			'theme-update'            => array(
				'label'       => 'Theme aktualisieren',
				'description' => 'Aktualisiert ein Theme auf die verfügbare Version. Ohne confirm=true nur Vorschau.' . $admin_note,
				'flush'       => 'site',
				'properties'  => array(
					'theme'   => $theme,
					'confirm' => $confirm,
				),
				'required'    => array( 'theme' ),
				'permission'  => $cap( 'update_themes' ),
				'execute'     => array( __CLASS__, 'theme_update' ),
			),
			'core-update-check'       => array(
				'label'       => 'WordPress-Updates prüfen',
				'description' => 'Installierte WordPress-Version und verfügbare Updates. core-update führt nur Minor-Updates (gleicher Zweig, z.B. 6.9.1 -> 6.9.2) aus.',
				'readonly'    => true,
				'properties'  => array( 'refresh' => $refresh ),
				'permission'  => $cap( 'update_core' ),
				'execute'     => array( __CLASS__, 'core_update_check' ),
			),
			'core-update'             => array(
				'label'       => 'WordPress-Minor-Update',
				'description' => 'Installiert das verfügbare Minor-Update von WordPress (nur gleicher Zweig, keine neue Hauptversion). Ohne confirm=true nur Vorschau.' . $admin_note,
				'flush'       => 'site',
				'properties'  => array( 'confirm' => $confirm ),
				'permission'  => $cap( 'update_core' ),
				'execute'     => array( __CLASS__, 'core_update' ),
			),
			'site-health'             => array(
				'label'       => 'Website-Zustand',
				'description' => 'Ergebnisse der direkten Website-Zustand-Tests, PHP-Version, Speicherlimit, Cron-Status, Debug-Modus, Objekt-Cache.',
				'readonly'    => true,
				'properties'  => array(),
				'permission'  => $cap( 'view_site_health_checks' ),
				'execute'     => array( __CLASS__, 'site_health' ),
			),
			'cache-flush'             => array(
				'label'       => 'Cache leeren',
				'description' => 'Leert Objekt-Cache, Elementor-CSS und erkannte Cache-Plugins (WP Super Cache, W3 Total Cache, WP Rocket, LiteSpeed, Autoptimize, SG Optimizer, Breeze). Mit post_id nur für diesen Beitrag. Läuft nach Änderungen ohnehin automatisch. Ohne confirm=true nur Vorschau.',
				'properties'  => array(
					'post_id' => array(
						'type'    => 'integer',
						'minimum' => 1,
					),
					'confirm' => $confirm,
				),
				'permission'  => static function ( $input ) {
					if ( ! empty( $input['post_id'] ) ) {
						return Tabside_MCP_Abilities::check_post_permission( array( 'id' => $input['post_id'] ), 'edit_post' );
					}
					return Tabside_MCP_Plugin::check_user( 'manage_options' );
				},
				'execute'     => array( __CLASS__, 'cache_flush' ),
			),
			'user-list'               => array(
				'label'       => 'Benutzer auflisten',
				'description' => 'Benutzer mit Login, Name, E-Mail, Rolle, Registrierung, Anzahl Anwendungspasswörter und letzter Nutzung eines Anwendungspassworts.',
				'readonly'    => true,
				'properties'  => array(
					'role'   => array( 'type' => 'string' ),
					'search' => array( 'type' => 'string' ),
					'limit'  => array(
						'type'    => 'integer',
						'minimum' => 1,
						'maximum' => Tabside_MCP_Abilities::MAX_LIMIT,
						'default' => 50,
					),
					'page'   => array(
						'type'    => 'integer',
						'minimum' => 1,
						'default' => 1,
					),
				),
				'permission'  => $cap( 'list_users' ),
				'execute'     => array( __CLASS__, 'user_list' ),
			),
			'user-get'                => array(
				'label'       => 'Benutzer abrufen',
				'description' => 'Ein Benutzer mit Namen, Biografie, Rollen und Anwendungspasswörtern (ohne Passwort).',
				'readonly'    => true,
				'properties'  => array( 'user_id' => Tabside_MCP_Abilities::id_schema( 'ID des Benutzers.' ) ),
				'required'    => array( 'user_id' ),
				'permission'  => static function ( $input ) {
					if ( (int) ( $input['user_id'] ?? 0 ) === get_current_user_id() ) {
						return Tabside_MCP_Plugin::check_user();
					}
					return Tabside_MCP_Plugin::check_user( 'list_users' );
				},
				'execute'     => array( __CLASS__, 'user_get' ),
			),
			'user-update'             => array(
				'label'       => 'Benutzer ändern',
				'description' => 'Ändert nur Anzeigename, Vor-/Nachname, Biografie oder Rolle. Kein Passwort, keine E-Mail, kein Anlegen oder Löschen. Rolle administrator und Änderungen an Administratoren nur durch Administratoren, die eigene Rolle nie. Ohne confirm=true nur Vorschau.' . $admin_note,
				'properties'  => array(
					'user_id'      => Tabside_MCP_Abilities::id_schema( 'ID des Benutzers.' ),
					'display_name' => array( 'type' => 'string' ),
					'first_name'   => array( 'type' => 'string' ),
					'last_name'    => array( 'type' => 'string' ),
					'description'  => array( 'type' => 'string' ),
					'role'         => array( 'type' => 'string' ),
					'confirm'      => $confirm,
				),
				'required'    => array( 'user_id' ),
				'permission'  => static function ( $input ) {
					$ok = Tabside_MCP_Plugin::check_user( 'edit_user', (int) ( $input['user_id'] ?? 0 ) );
					if ( true === $ok && isset( $input['role'] ) ) {
						$ok = Tabside_MCP_Plugin::check_user( 'promote_user', (int) $input['user_id'] );
					}
					return $ok;
				},
				'execute'     => array( __CLASS__, 'user_update' ),
			),
			'application-password-list' => array(
				'label'       => 'Eigene Anwendungspasswörter',
				'description' => 'Anwendungspasswörter des angemeldeten Benutzers: Name, erstellt, zuletzt benutzt, letzte IP. Nie das Passwort.',
				'readonly'    => true,
				'properties'  => array(),
				'permission'  => static function () {
					return Tabside_MCP_Plugin::check_user( 'read' );
				},
				'execute'     => array( __CLASS__, 'application_password_list' ),
			),
			'audit-log'               => array(
				'label'       => 'Protokoll',
				'description' => 'Protokoll der ausgeführten Änderungen über tabside MCP (Zeit, Benutzer, Ability, Ziel, Sicherungs-ID), neueste zuerst, höchstens 500. Administratoren sehen alle Einträge, andere nur die eigenen.',
				'readonly'    => true,
				'properties'  => array(
					'limit' => array(
						'type'    => 'integer',
						'minimum' => 1,
						'maximum' => Tabside_MCP_Store::MAX_AUDIT,
						'default' => 50,
					),
					'user'  => array( 'type' => 'string' ),
				),
				'permission'  => static function () {
					return Tabside_MCP_Plugin::check_user( 'edit_posts' );
				},
				'execute'     => array( __CLASS__, 'audit_log' ),
			),
		);
	}

	private static function admin_includes() {
		require_once ABSPATH . 'wp-admin/includes/admin.php';
		require_once ABSPATH . 'wp-admin/includes/plugin-install.php';
		require_once ABSPATH . 'wp-admin/includes/class-wp-upgrader.php';
	}

	/* ------------------------------------------------------------------ Plugins */

	public static function plugin_list( $input ) {
		self::admin_includes();
		if ( ! empty( $input['refresh'] ) ) {
			wp_update_plugins();
		}
		$updates = get_site_transient( 'update_plugins' );
		$auto    = (array) get_site_option( 'auto_update_plugins', array() );
		$out     = array();
		foreach ( get_plugins() as $file => $data ) {
			$update = isset( $updates->response[ $file ] ) ? $updates->response[ $file ] : null;
			$out[]  = array(
				'plugin'      => $file,
				'name'        => $data['Name'],
				'version'     => $data['Version'],
				'author'      => wp_strip_all_tags( $data['Author'] ),
				'active'      => is_plugin_active( $file ),
				'update'      => $update ? $update->new_version : null,
				'auto_update' => in_array( $file, $auto, true ) || ( self::SELF_PLUGIN === $file && ! defined( 'TABSIDE_MCP_DISABLE_AUTO_UPDATE' ) ),
			);
		}
		return array(
			'auto_updates_possible' => wp_is_auto_update_enabled_for_type( 'plugin' ),
			'plugins'               => $out,
		);
	}

	public static function plugin_activate( $input ) {
		$file = self::plugin_file( $input['plugin'] );
		if ( is_wp_error( $file ) ) {
			return $file;
		}
		if ( ! current_user_can( 'activate_plugin', $file ) ) {
			return self::forbidden( 'activate_plugin' );
		}
		if ( is_plugin_active( $file ) ) {
			return new WP_Error( 'tabside_mcp_plugin_active', sprintf( '%s ist bereits aktiv.', $file ) );
		}
		if ( empty( $input['confirm'] ) ) {
			return Tabside_MCP_Abilities::preview_result( array( 'plugin' => self::plugin_info( $file ) ), array( 'Wird aktiviert.' ) );
		}
		$result = activate_plugin( $file );
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		return array(
			'confirmed' => true,
			'plugin'    => self::plugin_info( $file ),
		);
	}

	public static function plugin_deactivate( $input ) {
		$file = self::plugin_file( $input['plugin'] );
		if ( is_wp_error( $file ) ) {
			return $file;
		}
		if ( self::SELF_PLUGIN === $file || plugin_basename( TABSIDE_MCP_DIR . 'tabside-mcp.php' ) === $file ) {
			return new WP_Error( 'tabside_mcp_self', 'tabside-mcp lässt sich über tabside MCP nicht deaktivieren.', array( 'status' => 403 ) );
		}
		if ( ! current_user_can( 'deactivate_plugin', $file ) ) {
			return self::forbidden( 'deactivate_plugin' );
		}
		if ( ! is_plugin_active( $file ) ) {
			return new WP_Error( 'tabside_mcp_plugin_inactive', sprintf( '%s ist nicht aktiv.', $file ) );
		}
		if ( empty( $input['confirm'] ) ) {
			return Tabside_MCP_Abilities::preview_result( array( 'plugin' => self::plugin_info( $file ) ), array( 'Wird deaktiviert, nicht gelöscht. Wieder einschalten mit plugin-activate.' ) );
		}
		deactivate_plugins( $file );
		return array(
			'confirmed' => true,
			'plugin'    => self::plugin_info( $file ),
		);
	}

	public static function plugin_update( $input ) {
		$file = self::plugin_file( $input['plugin'] );
		if ( is_wp_error( $file ) ) {
			return $file;
		}
		wp_update_plugins();
		$updates = get_site_transient( 'update_plugins' );
		$update  = $updates->response[ $file ] ?? null;
		if ( ! $update ) {
			return new WP_Error( 'tabside_mcp_no_update', sprintf( 'Für %s ist kein Update verfügbar.', $file ) );
		}
		$info = self::plugin_info( $file );
		if ( empty( $input['confirm'] ) ) {
			return Tabside_MCP_Abilities::preview_result(
				array(
					'plugin'      => $info,
					'new_version' => $update->new_version,
				),
				array()
			);
		}
		$was_active = is_plugin_active( $file );
		$skin       = new WP_Ajax_Upgrader_Skin();
		$result     = ( new Plugin_Upgrader( $skin ) )->upgrade( $file );
		$error      = self::upgrader_error( $result, $skin );
		if ( $error ) {
			return $error;
		}
		wp_clean_plugins_cache();
		// Über die REST-API deaktiviert WordPress das Plugin vor dem Update und aktiviert es nicht wieder.
		if ( $was_active && ! is_plugin_active( $file ) ) {
			activate_plugin( $file, '', false, true );
		}
		return array(
			'confirmed'   => true,
			'old_version' => $info['version'],
			'plugin'      => self::plugin_info( $file ),
		);
	}

	public static function plugin_auto_update_set( $input ) {
		$file = self::plugin_file( $input['plugin'] );
		if ( is_wp_error( $file ) ) {
			return $file;
		}
		if ( ! wp_is_auto_update_enabled_for_type( 'plugin' ) ) {
			return new WP_Error( 'tabside_mcp_auto_updates_off', 'Automatische Plugin-Updates sind auf dieser Seite abgeschaltet.' );
		}
		$enabled = (bool) $input['enabled'];
		$list    = (array) get_site_option( 'auto_update_plugins', array() );
		$old     = in_array( $file, $list, true );
		$notes   = self::SELF_PLUGIN === $file ? array( 'tabside-mcp aktualisiert sich unabhängig davon selbst (abschaltbar mit TABSIDE_MCP_DISABLE_AUTO_UPDATE).' ) : array();
		if ( empty( $input['confirm'] ) ) {
			return Tabside_MCP_Abilities::preview_result(
				array(
					'plugin'      => $file,
					'auto_update' => array(
						'old' => $old,
						'new' => $enabled,
					),
				),
				$notes
			);
		}
		$list = $enabled ? array_values( array_unique( array_merge( $list, array( $file ) ) ) ) : array_values( array_diff( $list, array( $file ) ) );
		update_site_option( 'auto_update_plugins', $list );
		return array(
			'confirmed'   => true,
			'plugin'      => $file,
			'auto_update' => in_array( $file, (array) get_site_option( 'auto_update_plugins', array() ), true ),
			'notes'       => $notes,
		);
	}

	public static function plugin_install( $input ) {
		self::admin_includes();
		$slug = (string) $input['slug'];
		if ( ! preg_match( '/^[a-z0-9][a-z0-9-]*$/', $slug ) ) {
			return new WP_Error( 'tabside_mcp_plugin_slug', 'Ungültiger Slug.' );
		}
		foreach ( array_keys( get_plugins() ) as $file ) {
			if ( dirname( $file ) === $slug ) {
				return new WP_Error( 'tabside_mcp_plugin_installed', sprintf( 'Plugin %s ist bereits installiert (%s).', $slug, $file ) );
			}
		}
		$api = plugins_api(
			'plugin_information',
			array(
				'slug'   => $slug,
				'fields' => array(
					'sections'    => false,
					'short_description' => true,
					'icons'       => false,
					'banners'     => false,
					'reviews'     => false,
					'downloaded'  => false,
					'active_installs' => true,
				),
			)
		);
		if ( is_wp_error( $api ) ) {
			return new WP_Error( 'tabside_mcp_plugin_unknown', sprintf( 'Plugin "%s" im WordPress-Verzeichnis nicht gefunden: %s', $slug, $api->get_error_message() ) );
		}
		$link = (string) ( $api->download_link ?? '' );
		if ( 0 !== strpos( $link, 'https://downloads.wordpress.org/' ) ) {
			return new WP_Error( 'tabside_mcp_plugin_source', 'Download stammt nicht aus dem WordPress-Verzeichnis, Installation abgebrochen.' );
		}
		$preview = array(
			'slug'            => $slug,
			'name'            => $api->name,
			'version'         => $api->version,
			'author'          => wp_strip_all_tags( (string) $api->author ),
			'requires_wp'     => $api->requires ?? null,
			'tested_wp'       => $api->tested ?? null,
			'requires_php'    => $api->requires_php ?? null,
			'active_installs' => $api->active_installs ?? null,
			'rating'          => $api->rating ?? null,
			'last_updated'    => $api->last_updated ?? null,
			'description'     => wp_strip_all_tags( (string) ( $api->short_description ?? '' ) ),
			'activate'        => ! empty( $input['activate'] ),
		);
		if ( empty( $input['confirm'] ) ) {
			return Tabside_MCP_Abilities::preview_result( $preview, array( 'Quelle: wordpress.org/plugins/' . $slug . '/' ) );
		}
		$skin   = new WP_Ajax_Upgrader_Skin();
		$upgr   = new Plugin_Upgrader( $skin );
		$result = $upgr->install( $link );
		$error  = self::upgrader_error( $result, $skin );
		if ( $error ) {
			return $error;
		}
		wp_clean_plugins_cache();
		$file = $upgr->plugin_info();
		if ( ! $file ) {
			return new WP_Error( 'tabside_mcp_plugin_install', 'Installiert, aber die Plugin-Datei wurde nicht gefunden.' );
		}
		$notes = array();
		if ( ! empty( $input['activate'] ) ) {
			$activated = activate_plugin( $file );
			if ( is_wp_error( $activated ) ) {
				$notes[] = 'Installiert, aber nicht aktiviert: ' . $activated->get_error_message();
			}
		}
		return array(
			'confirmed' => true,
			'notes'     => $notes,
			'plugin'    => self::plugin_info( $file ),
		);
	}

	/**
	 * Datei oder Verzeichnis-Slug -> Plugin-Datei.
	 *
	 * @return string|WP_Error
	 */
	private static function plugin_file( $plugin ) {
		self::admin_includes();
		$plugin  = trim( (string) $plugin );
		$plugins = get_plugins();
		if ( isset( $plugins[ $plugin ] ) ) {
			return $plugin;
		}
		$matches = array();
		foreach ( array_keys( $plugins ) as $file ) {
			if ( dirname( $file ) === $plugin || basename( $file, '.php' ) === $plugin ) {
				$matches[] = $file;
			}
		}
		if ( 1 === count( $matches ) ) {
			return $matches[0];
		}
		return new WP_Error( 'tabside_mcp_plugin_not_found', sprintf( 'Plugin "%s" nicht eindeutig gefunden (plugin-list).', $plugin ), array( 'status' => 404 ) );
	}

	private static function plugin_info( $file ) {
		self::admin_includes();
		wp_clean_plugins_cache( false );
		$plugins = get_plugins();
		$data    = $plugins[ $file ] ?? array();
		return array(
			'plugin'  => $file,
			'name'    => $data['Name'] ?? $file,
			'version' => $data['Version'] ?? null,
			'active'  => is_plugin_active( $file ),
		);
	}

	/**
	 * @return WP_Error|null
	 */
	private static function upgrader_error( $result, $skin ) {
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		if ( $skin->get_errors()->has_errors() ) {
			return new WP_Error( 'tabside_mcp_upgrade', implode( ' ', $skin->get_error_messages() ? (array) $skin->get_error_messages() : $skin->get_errors()->get_error_messages() ) );
		}
		if ( false === $result || null === $result ) {
			return new WP_Error( 'tabside_mcp_upgrade', 'Fehlgeschlagen. Möglicherweise fehlt der direkte Dateizugriff (FS_METHOD) auf diesem Server.' );
		}
		return null;
	}

	/* ------------------------------------------------------------------ Themes */

	public static function theme_list( $input ) {
		self::admin_includes();
		if ( ! empty( $input['refresh'] ) ) {
			wp_update_themes();
		}
		$updates = get_site_transient( 'update_themes' );
		$auto    = (array) get_site_option( 'auto_update_themes', array() );
		$out     = array();
		foreach ( wp_get_themes() as $stylesheet => $theme ) {
			$out[] = array(
				'theme'       => $stylesheet,
				'name'        => $theme->get( 'Name' ),
				'version'     => $theme->get( 'Version' ),
				'active'      => get_stylesheet() === $stylesheet,
				'parent'      => $theme->parent() ? $theme->get_template() : null,
				'block_theme' => $theme->is_block_theme(),
				'update'      => isset( $updates->response[ $stylesheet ]['new_version'] ) ? $updates->response[ $stylesheet ]['new_version'] : null,
				'auto_update' => in_array( $stylesheet, $auto, true ),
			);
		}
		return array( 'themes' => $out );
	}

	public static function theme_activate( $input ) {
		$theme = wp_get_theme( (string) $input['theme'] );
		if ( ! $theme->exists() || $theme->errors() ) {
			return new WP_Error( 'tabside_mcp_theme_not_found', sprintf( 'Theme "%s" nicht gefunden oder fehlerhaft (theme-list).', $input['theme'] ), array( 'status' => 404 ) );
		}
		if ( get_stylesheet() === $theme->get_stylesheet() ) {
			return new WP_Error( 'tabside_mcp_theme_active', 'Dieses Theme ist bereits aktiv.' );
		}
		if ( empty( $input['confirm'] ) ) {
			return Tabside_MCP_Abilities::preview_result(
				array(
					'current' => get_stylesheet(),
					'new'     => $theme->get_stylesheet(),
					'name'    => $theme->get( 'Name' ),
				),
				array( 'ACHTUNG: Die ganze Seite ändert ihr Aussehen. Menü-Positionen, Widgets und Customizer-Einstellungen gehören zum Theme und können sich verschieben. Zurück mit theme-activate und dem bisherigen Theme.' )
			);
		}
		$old = get_stylesheet();
		switch_theme( $theme->get_stylesheet() );
		return array(
			'confirmed' => true,
			'previous'  => $old,
			'active'    => get_stylesheet(),
		);
	}

	public static function theme_update( $input ) {
		self::admin_includes();
		$stylesheet = (string) $input['theme'];
		$theme      = wp_get_theme( $stylesheet );
		if ( ! $theme->exists() ) {
			return new WP_Error( 'tabside_mcp_theme_not_found', sprintf( 'Theme "%s" nicht gefunden.', $stylesheet ), array( 'status' => 404 ) );
		}
		wp_update_themes();
		$updates = get_site_transient( 'update_themes' );
		if ( empty( $updates->response[ $stylesheet ] ) ) {
			return new WP_Error( 'tabside_mcp_no_update', sprintf( 'Für %s ist kein Update verfügbar.', $stylesheet ) );
		}
		$old = $theme->get( 'Version' );
		if ( empty( $input['confirm'] ) ) {
			return Tabside_MCP_Abilities::preview_result(
				array(
					'theme'       => $stylesheet,
					'version'     => $old,
					'new_version' => $updates->response[ $stylesheet ]['new_version'],
				),
				array()
			);
		}
		$skin   = new WP_Ajax_Upgrader_Skin();
		$result = ( new Theme_Upgrader( $skin ) )->upgrade( $stylesheet );
		$error  = self::upgrader_error( $result, $skin );
		if ( $error ) {
			return $error;
		}
		wp_clean_themes_cache();
		return array(
			'confirmed'   => true,
			'old_version' => $old,
			'version'     => wp_get_theme( $stylesheet )->get( 'Version' ),
		);
	}

	/* ------------------------------------------------------------------ Core */

	public static function core_update_check( $input ) {
		self::admin_includes();
		if ( ! empty( $input['refresh'] ) ) {
			wp_version_check( array(), true );
		}
		$offers = array();
		foreach ( self::core_offers() as $offer ) {
			$offers[] = array(
				'response' => $offer->response,
				'version'  => $offer->version ?? $offer->current ?? null,
				'locale'   => $offer->locale ?? null,
				'minor'    => self::is_minor( $offer ),
			);
		}
		$minor = self::minor_offer();
		return array(
			'wordpress'       => get_bloginfo( 'version' ),
			'offers'          => $offers,
			'minor_available' => $minor ? $minor->version : null,
		);
	}

	public static function core_update( $input ) {
		self::admin_includes();
		wp_version_check( array(), true );
		$offer = self::minor_offer();
		if ( ! $offer ) {
			return new WP_Error( 'tabside_mcp_no_update', 'Kein Minor-Update verfügbar (neue Hauptversionen nur über wp-admin).' );
		}
		if ( empty( $input['confirm'] ) ) {
			return Tabside_MCP_Abilities::preview_result(
				array(
					'wordpress'   => get_bloginfo( 'version' ),
					'new_version' => $offer->version,
				),
				array( 'Die Seite ist während des Updates kurz im Wartungsmodus.' )
			);
		}
		$old    = get_bloginfo( 'version' );
		$skin   = new WP_Ajax_Upgrader_Skin();
		$result = ( new Core_Upgrader( $skin ) )->upgrade( $offer );
		$error  = self::upgrader_error( $result, $skin );
		if ( $error ) {
			return $error;
		}
		return array(
			'confirmed'   => true,
			'old_version' => $old,
			'version'     => is_string( $result ) ? $result : $offer->version,
		);
	}

	private static function is_minor( $offer ) {
		$current = explode( '.', preg_replace( '/-.*$/', '', get_bloginfo( 'version' ) ) );
		$new     = explode( '.', (string) ( $offer->version ?? '' ) );
		return isset( $new[1] ) && 'upgrade' === ( $offer->response ?? '' )
			&& $current[0] === $new[0] && ( $current[1] ?? '0' ) === $new[1]
			&& version_compare( $offer->version, get_bloginfo( 'version' ), '>' );
	}

	/**
	 * Update-Angebote von wordpress.org (leer, solange WordPress noch nicht nachgefragt hat).
	 *
	 * @return object[]
	 */
	private static function core_offers() {
		$offers = get_core_updates();
		return is_array( $offers ) ? array_filter( $offers, 'is_object' ) : array();
	}

	private static function minor_offer() {
		foreach ( self::core_offers() as $offer ) {
			if ( self::is_minor( $offer ) ) {
				return $offer;
			}
		}
		return null;
	}

	/* ------------------------------------------------------------------ Wartung */

	public static function site_health() {
		self::admin_includes();
		require_once ABSPATH . 'wp-admin/includes/class-wp-site-health.php';
		$health  = WP_Site_Health::get_instance();
		$results = array();
		foreach ( (array) ( $health::get_tests()['direct'] ?? array() ) as $key => $test ) {
			$callback = null;
			if ( is_string( $test['test'] ) && method_exists( $health, 'get_test_' . $test['test'] ) ) {
				$callback = array( $health, 'get_test_' . $test['test'] );
			} elseif ( is_callable( $test['test'] ) ) {
				$callback = $test['test'];
			}
			if ( ! $callback ) {
				continue;
			}
			$result = call_user_func( $callback );
			if ( ! is_array( $result ) ) {
				continue;
			}
			$results[] = array(
				'test'        => $key,
				'label'       => wp_strip_all_tags( (string) ( $result['label'] ?? $test['label'] ?? $key ) ),
				'status'      => $result['status'] ?? null,
				'category'    => $result['badge']['label'] ?? null,
				'description' => trim( preg_replace( '/\s+/', ' ', html_entity_decode( wp_strip_all_tags( str_replace( '</p>', '</p> ', (string) ( $result['description'] ?? '' ) ) ), ENT_QUOTES ) ) ),
			);
		}
		$crons   = _get_cron_array();
		$overdue = 0;
		$next    = null;
		foreach ( (array) $crons as $timestamp => $events ) {
			if ( $timestamp < time() - 600 ) {
				$overdue += count( $events );
			}
			if ( null === $next || $timestamp < $next ) {
				$next = $timestamp;
			}
		}
		$counts = array_count_values( wp_list_pluck( $results, 'status' ) );
		return array(
			'summary'      => $counts,
			'php'          => PHP_VERSION,
			'memory_limit' => ini_get( 'memory_limit' ),
			'wp_memory'    => WP_MEMORY_LIMIT,
			'debug'        => array(
				'WP_DEBUG'         => defined( 'WP_DEBUG' ) && WP_DEBUG,
				'WP_DEBUG_LOG'     => defined( 'WP_DEBUG_LOG' ) && WP_DEBUG_LOG,
				'WP_DEBUG_DISPLAY' => defined( 'WP_DEBUG_DISPLAY' ) && WP_DEBUG_DISPLAY,
			),
			'cron'         => array(
				'disabled'       => defined( 'DISABLE_WP_CRON' ) && DISABLE_WP_CRON,
				'next_event_gmt' => $next ? gmdate( 'Y-m-d H:i:s', $next ) : null,
				'overdue_events' => $overdue,
			),
			'object_cache' => (bool) wp_using_ext_object_cache(),
			'https'        => 0 === strpos( home_url(), 'https://' ),
			'tests'        => $results,
		);
	}

	public static function cache_flush( $input ) {
		$posts = ! empty( $input['post_id'] ) ? array( (int) $input['post_id'] ) : array();
		if ( empty( $input['confirm'] ) ) {
			return Tabside_MCP_Abilities::preview_result(
				array(
					'scope'   => $posts ? 'posts' : 'site',
					'posts'   => $posts,
					'plugins' => array_keys( array_filter( Tabside_MCP_Cache::detected() ) ),
				),
				array()
			);
		}
		return array(
			'confirmed' => true,
			'cache'     => Tabside_MCP_Cache::flush( $posts ),
		);
	}

	/* ------------------------------------------------------------------ Benutzer */

	public static function user_list( $input ) {
		$limit = min( Tabside_MCP_Abilities::MAX_LIMIT, max( 1, (int) ( $input['limit'] ?? 50 ) ) );
		$args  = array(
			'number'      => $limit,
			'paged'       => max( 1, (int) ( $input['page'] ?? 1 ) ),
			'orderby'     => 'login',
			'count_total' => true,
		);
		if ( ! empty( $input['role'] ) ) {
			$args['role'] = (string) $input['role'];
		}
		if ( ! empty( $input['search'] ) ) {
			$args['search'] = '*' . (string) $input['search'] . '*';
		}
		$query = new WP_User_Query( $args );
		return array(
			'total' => (int) $query->get_total(),
			'users' => array_map( array( __CLASS__, 'user_summary' ), $query->get_results() ),
		);
	}

	public static function user_get( $input ) {
		$user = get_userdata( (int) $input['user_id'] );
		if ( ! $user ) {
			return new WP_Error( 'tabside_mcp_not_found', sprintf( 'Benutzer %d nicht gefunden.', $input['user_id'] ), array( 'status' => 404 ) );
		}
		$out                          = self::user_summary( $user );
		$out['first_name']            = $user->first_name;
		$out['last_name']             = $user->last_name;
		$out['description']           = $user->description;
		$out['url']                   = $user->user_url;
		$out['application_passwords'] = self::app_passwords( $user->ID );
		return $out;
	}

	public static function user_update( $input ) {
		$user = get_userdata( (int) $input['user_id'] );
		if ( ! $user ) {
			return new WP_Error( 'tabside_mcp_not_found', sprintf( 'Benutzer %d nicht gefunden.', $input['user_id'] ), array( 'status' => 404 ) );
		}
		$me       = wp_get_current_user();
		$is_admin = in_array( 'administrator', (array) $me->roles, true ) || is_super_admin();
		if ( in_array( 'administrator', (array) $user->roles, true ) && ! $is_admin ) {
			return new WP_Error( 'tabside_mcp_forbidden', 'Administratoren darf nur ein Administrator ändern.', array( 'status' => 403 ) );
		}
		$changes = array();
		$data    = array( 'ID' => $user->ID );
		foreach ( array( 'display_name', 'first_name', 'last_name', 'description' ) as $key ) {
			if ( isset( $input[ $key ] ) && (string) $input[ $key ] !== (string) $user->$key ) {
				$data[ $key ]    = (string) $input[ $key ];
				$changes[ $key ] = array(
					'old' => $user->$key,
					'new' => (string) $input[ $key ],
				);
			}
		}
		$role = null;
		if ( isset( $input['role'] ) ) {
			$role = (string) $input['role'];
			if ( $user->ID === $me->ID ) {
				return new WP_Error( 'tabside_mcp_own_role', 'Die eigene Rolle lässt sich über tabside MCP nicht ändern.', array( 'status' => 403 ) );
			}
			require_once ABSPATH . 'wp-admin/includes/user.php';
			$editable = get_editable_roles();
			if ( ! isset( $editable[ $role ] ) ) {
				return new WP_Error( 'tabside_mcp_role', sprintf( 'Rolle "%s" gibt es nicht oder darf nicht vergeben werden. Möglich: %s.', $role, implode( ', ', array_keys( $editable ) ) ) );
			}
			if ( 'administrator' === $role && ! $is_admin ) {
				return new WP_Error( 'tabside_mcp_forbidden', 'Die Rolle administrator darf nur ein Administrator vergeben.', array( 'status' => 403 ) );
			}
			if ( array( $role ) !== array_values( (array) $user->roles ) ) {
				$changes['role'] = array(
					'old' => array_values( (array) $user->roles ),
					'new' => $role,
				);
			} else {
				$role = null;
			}
		}
		if ( empty( $changes ) ) {
			return new WP_Error( 'tabside_mcp_nothing_to_update', 'Keine Änderung gegenüber dem aktuellen Stand.' );
		}
		if ( empty( $input['confirm'] ) ) {
			return Tabside_MCP_Abilities::preview_result(
				array(
					'user'    => self::user_summary( $user ),
					'changes' => $changes,
				),
				array()
			);
		}
		$backup = Tabside_MCP_Store::backup(
			'user',
			(string) $user->ID,
			array(
				'display_name' => $user->display_name,
				'first_name'   => $user->first_name,
				'last_name'    => $user->last_name,
				'description'  => $user->description,
				'roles'        => array_values( (array) $user->roles ),
			)
		);
		if ( count( $data ) > 1 ) {
			$result = wp_update_user( wp_slash( $data ) );
			if ( is_wp_error( $result ) ) {
				return $result;
			}
		}
		if ( null !== $role ) {
			$user->set_role( $role );
		}
		return array(
			'confirmed' => true,
			'backup_id' => $backup,
			'user'      => self::user_get( array( 'user_id' => $user->ID ) ),
		);
	}

	public static function application_password_list() {
		$user = wp_get_current_user();
		return array(
			'user'                  => $user->user_login,
			'application_passwords' => self::app_passwords( $user->ID ),
		);
	}

	public static function audit_log( $input ) {
		$limit = min( Tabside_MCP_Store::MAX_AUDIT, max( 1, (int) ( $input['limit'] ?? 50 ) ) );
		$user  = current_user_can( 'manage_options' ) ? ( empty( $input['user'] ) ? null : (string) $input['user'] ) : wp_get_current_user()->user_login;
		return array( 'entries' => Tabside_MCP_Store::audit( $limit, $user ) );
	}

	private static function app_passwords( $user_id ) {
		$out = array();
		foreach ( WP_Application_Passwords::get_user_application_passwords( $user_id ) as $item ) {
			$out[] = array(
				'uuid'      => $item['uuid'],
				'name'      => $item['name'],
				'created'   => $item['created'] ? gmdate( 'Y-m-d H:i:s', (int) $item['created'] ) : null,
				'last_used' => $item['last_used'] ? gmdate( 'Y-m-d H:i:s', (int) $item['last_used'] ) : null,
				'last_ip'   => $item['last_ip'] ?? null,
			);
		}
		return $out;
	}

	private static function user_summary( WP_User $user ) {
		$last = null;
		$apps = WP_Application_Passwords::get_user_application_passwords( $user->ID );
		foreach ( $apps as $item ) {
			if ( ! empty( $item['last_used'] ) && ( null === $last || $item['last_used'] > $last ) ) {
				$last = (int) $item['last_used'];
			}
		}
		return array(
			'id'                         => $user->ID,
			'login'                      => $user->user_login,
			'display_name'               => $user->display_name,
			'email'                      => $user->user_email,
			'roles'                      => array_values( (array) $user->roles ),
			'registered'                 => $user->user_registered,
			'application_passwords'      => count( $apps ),
			'last_application_login_gmt' => $last ? gmdate( 'Y-m-d H:i:s', $last ) : null,
		);
	}

	private static function forbidden( $capability ) {
		return new WP_Error( 'tabside_mcp_forbidden', sprintf( 'Fehlende Berechtigung: %s', $capability ), array( 'status' => 403 ) );
	}
}
