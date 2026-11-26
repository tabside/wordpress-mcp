<?php
/**
 * Einmal-Anmeldelinks (Magic Links): Login im wp-admin ohne Passwort.
 *
 * Die Ability "login-link-create" erzeugt für den Benutzer, mit dem das Gateway angemeldet ist, einen Link
 * auf wp-login.php?action=tabside_mcp_link. Nur dieser eigene Benutzer, nie ein anderer: der Link gibt keine
 * Rechte, die das Gateway nicht schon hat. Sicherheit:
 * - Token mit 256 Bit Zufall, gespeichert wird nur ein HMAC (wp_salt), nie das Token selbst.
 * - Einmalig: beim Einlösen sofort gelöscht. Gültig 1 bis 30 Minuten (Vorgabe 10).
 * - Der Link selbst meldet nicht an: GET zeigt nur eine Bestätigungsseite, angemeldet wird erst per POST.
 *   So verbrauchen Link-Vorschauen und Virenscanner den Link nicht.
 * - Höchstens 3 offene Links pro Benutzer, ältere werden verworfen. Ausschalten mit
 *   define( 'TABSIDE_MCP_LOGIN_LINKS', false ) oder Filter tabside_mcp_login_links_enabled.
 * - Erzeugen und Einlösen stehen im audit-log.
 *
 * @package tabside-mcp
 */

defined( 'ABSPATH' ) || exit;

final class Tabside_MCP_Login_Link {

	const ACTION      = 'tabside_mcp_link';
	const OPTION      = '_tabside_mcp_login_links';
	const DEFAULT_TTL = 10;
	const MAX_TTL     = 30;
	const MAX_OPEN    = 3;

	public static function boot() {
		add_action( 'login_form_' . self::ACTION, array( __CLASS__, 'handle' ) );
	}

	public static function enabled() {
		$enabled = defined( 'TABSIDE_MCP_LOGIN_LINKS' ) ? (bool) TABSIDE_MCP_LOGIN_LINKS : true;
		return (bool) apply_filters( 'tabside_mcp_login_links_enabled', $enabled );
	}

	/**
	 * @return array<string, array<string, mixed>>
	 */
	public static function definitions() {
		return array(
			'login-link-create' => array(
				'label'       => 'Anmeldelink erzeugen',
				'description' => 'Einmal-Anmeldelink (Magic Link) für den eigenen Benutzer des Gateways: Login im wp-admin ohne Passwort. '
					. 'Gültig ttl_minutes (1-30, Vorgabe 10), nur einmal verwendbar; der Link zeigt zuerst eine Bestätigungsseite, angemeldet wird erst mit dem Klick auf "Anmelden". '
					. 'redirect = Ziel im wp-admin nach dem Login (relativ, z.B. plugin-install.php?tab=upload). Den Link nur dem Benutzer geben, nie weiterleiten oder speichern. '
					. 'Ohne confirm=true nur Vorschau.',
				'properties'  => array(
					'ttl_minutes' => array(
						'type'    => 'integer',
						'minimum' => 1,
						'maximum' => self::MAX_TTL,
						'default' => self::DEFAULT_TTL,
					),
					'redirect'    => array(
						'type'        => 'string',
						'description' => 'Ziel im wp-admin, relativ zu /wp-admin/ (z.B. plugins.php). Leer = Dashboard.',
					),
					'confirm'     => Tabside_MCP_Abilities::confirm_schema(),
				),
				'permission'  => static function () {
					return Tabside_MCP_Plugin::check_user( 'read' );
				},
				'execute'     => array( __CLASS__, 'create' ),
			),
		);
	}

	public static function create( $input ) {
		if ( ! self::enabled() ) {
			return new WP_Error( 'tabside_mcp_login_links_disabled', 'Anmeldelinks sind auf dieser Seite ausgeschaltet (TABSIDE_MCP_LOGIN_LINKS).', array( 'status' => 403 ) );
		}
		$user     = wp_get_current_user();
		$ttl      = min( self::MAX_TTL, max( 1, (int) ( $input['ttl_minutes'] ?? self::DEFAULT_TTL ) ) );
		$redirect = self::clean_redirect( (string) ( $input['redirect'] ?? '' ) );
		if ( is_wp_error( $redirect ) ) {
			return $redirect;
		}
		$preview = array(
			'user'        => $user->user_login,
			'ttl_minutes' => $ttl,
			'redirect'    => admin_url( $redirect ),
		);
		if ( empty( $input['confirm'] ) ) {
			return Tabside_MCP_Abilities::preview_result( $preview, array( 'Der Link meldet als dieser Benutzer an und ist nur einmal gültig.' ) );
		}

		$token   = rtrim( strtr( base64_encode( random_bytes( 32 ) ), '+/', '-_' ), '=' );
		$expires = time() + $ttl * MINUTE_IN_SECONDS;
		$links   = self::prune( self::all() );
		$own     = array_keys(
			array_filter(
				$links,
				static function ( $link ) use ( $user ) {
					return (int) $link['user_id'] === (int) $user->ID;
				}
			)
		);
		// Älteste offene Links desselben Benutzers verwerfen.
		while ( count( $own ) >= self::MAX_OPEN ) {
			unset( $links[ array_shift( $own ) ] );
		}
		$links[ self::hash( $token ) ] = array(
			'user_id'     => (int) $user->ID,
			'expires'     => $expires,
			'redirect'    => $redirect,
			'created_gmt' => gmdate( 'Y-m-d H:i:s' ),
		);
		self::save( $links );

		$url = add_query_arg(
			array(
				'action' => self::ACTION,
				'token'  => $token,
			),
			site_url( 'wp-login.php', 'login' )
		);
		return array(
			'confirmed'       => true,
			'url'             => $url,
			'user'            => $user->user_login,
			'expires_gmt'     => gmdate( 'Y-m-d H:i:s', $expires ),
			'ttl_minutes'     => $ttl,
			'redirect'        => admin_url( $redirect ),
			'note'            => 'Nur einmal gültig. Nicht weitergeben oder speichern.',
			'audit_target'    => 'user ' . $user->user_login . ' ttl ' . $ttl,
		);
	}

	/**
	 * wp-login.php?action=tabside_mcp_link: GET zeigt die Bestätigung, POST meldet an.
	 */
	public static function handle() {
		nocache_headers();
		header( 'Referrer-Policy: no-referrer' );
		header( 'X-Robots-Tag: noindex, nofollow' );

		$token = isset( $_REQUEST['token'] ) ? sanitize_text_field( wp_unslash( $_REQUEST['token'] ) ) : '';
		if ( ! self::enabled() || '' === $token || ! preg_match( '/^[A-Za-z0-9_-]{40,64}$/', $token ) ) {
			self::fail();
		}
		$links = self::prune( self::all() );
		$hash  = self::hash( $token );
		$link  = null;
		foreach ( $links as $key => $item ) {
			if ( hash_equals( (string) $key, $hash ) ) {
				$link = $item;
				break;
			}
		}
		if ( null === $link ) {
			self::save( $links );
			self::fail();
		}
		$user = get_userdata( (int) $link['user_id'] );

		if ( 'POST' !== strtoupper( (string) ( $_SERVER['REQUEST_METHOD'] ?? 'GET' ) ) ) {
			self::confirm_page( $token, $user );
			exit;
		}

		// Einmalig: vor dem Anmelden löschen.
		unset( $links[ $hash ] );
		self::save( $links );

		$allowed = Tabside_MCP_Plugin::allowed_login();
		if ( ! $user || ( '' !== $allowed && strtolower( $user->user_login ) !== strtolower( $allowed ) ) ) {
			self::fail();
		}

		wp_set_current_user( $user->ID );
		wp_set_auth_cookie( $user->ID, false, is_ssl() );
		Tabside_MCP_Store::log( 'login-link-use', 'user ' . $user->user_login, '' );
		/** Gleiche Aktion wie bei einer normalen Anmeldung (Protokoll-Plugins usw.). */
		do_action( 'wp_login', $user->user_login, $user );

		wp_safe_redirect( admin_url( (string) $link['redirect'] ) );
		exit;
	}

	private static function confirm_page( $token, $user ) {
		login_header( 'Anmelden' );
		printf(
			'<form method="post" action="%1$s"><p>Als <strong>%2$s</strong> anmelden?</p><p>Der Link ist nur einmal gültig.</p>'
			. '<input type="hidden" name="token" value="%3$s"><p class="submit"><input type="submit" class="button button-primary button-large" value="Anmelden"></p></form>',
			esc_url( add_query_arg( 'action', self::ACTION, site_url( 'wp-login.php', 'login_post' ) ) ),
			esc_html( $user ? $user->user_login : '' ),
			esc_attr( $token )
		);
		login_footer();
	}

	private static function fail() {
		wp_die(
			esc_html__( 'Dieser Anmeldelink ist ungültig, abgelaufen oder wurde schon verwendet.', 'tabside-mcp' ),
			esc_html__( 'Anmeldelink ungültig', 'tabside-mcp' ),
			array(
				'response'  => 403,
				'link_url'  => wp_login_url(),
				'link_text' => esc_html__( 'Zur normalen Anmeldung', 'tabside-mcp' ),
			)
		);
	}

	/**
	 * Nur Pfade im wp-admin, keine absoluten URLs, kein "..".
	 *
	 * @return string|WP_Error
	 */
	private static function clean_redirect( $redirect ) {
		$redirect = ltrim( trim( $redirect ), '/' );
		if ( 0 === strpos( $redirect, 'wp-admin/' ) ) {
			$redirect = substr( $redirect, 9 );
		}
		if ( '' === $redirect ) {
			return '';
		}
		if ( preg_match( '#^[a-z][a-z0-9+.-]*:|^//|\\\\|\.\.#i', $redirect ) || preg_match( '/[\x00-\x1f]/', $redirect ) ) {
			return new WP_Error( 'tabside_mcp_redirect', 'redirect muss ein Pfad im wp-admin sein, z.B. plugins.php oder edit.php?post_type=page.' );
		}
		return $redirect;
	}

	private static function hash( $token ) {
		return hash_hmac( 'sha256', $token, wp_salt( 'auth' ) );
	}

	/**
	 * @return array<string, array<string, mixed>>
	 */
	private static function all() {
		$links = get_option( self::OPTION, array() );
		return is_array( $links ) ? $links : array();
	}

	private static function prune( array $links ) {
		$now = time();
		return array_filter(
			$links,
			static function ( $link ) use ( $now ) {
				return is_array( $link ) && (int) ( $link['expires'] ?? 0 ) > $now;
			}
		);
	}

	private static function save( array $links ) {
		if ( false === get_option( self::OPTION, false ) ) {
			add_option( self::OPTION, $links, '', false );
		} else {
			update_option( self::OPTION, $links, false );
		}
	}
}
