<?php
/**
 * Abilities der Kategorie "tabside": Beiträge, Seiten, Kategorien, Schlagwörter, Medien.
 *
 * Schreibende Abilities führen nur mit confirm=true aus, sonst liefern sie eine Vorschau.
 * Keine Abilities für Plugins, Benutzer, Einstellungen oder Dateisystem.
 *
 * @package tabside-mcp
 */

defined( 'ABSPATH' ) || exit;

final class Tabside_MCP_Abilities {

	const CATEGORY   = 'tabside';
	const POST_TYPES = array( 'post', 'page' );
	const STATUSES   = array( 'draft', 'pending', 'publish', 'future', 'private' );
	const MAX_LIMIT  = 100;

	/**
	 * Ability-Namen in der Reihenfolge der Registrierung.
	 *
	 * @return string[]
	 */
	public static function names() {
		return array_map(
			static function ( $slug ) {
				return self::CATEGORY . '/' . $slug;
			},
			array_keys( self::definitions() )
		);
	}

	public static function register_category() {
		wp_register_ability_category(
			self::CATEGORY,
			array(
				'label'       => __( 'tabside', 'tabside-mcp' ),
				'description' => __( 'Inhalte verwalten über tabside MCP (Beiträge, Seiten, Medien).', 'tabside-mcp' ),
			)
		);
	}

	public static function register() {
		foreach ( self::definitions() as $slug => $def ) {
			$readonly = ! empty( $def['readonly'] );
			wp_register_ability(
				self::CATEGORY . '/' . $slug,
				array(
					'label'               => $def['label'],
					'description'         => $def['description'],
					'category'            => self::CATEGORY,
					'input_schema'        => array(
						'type'                 => 'object',
						// Der REST-Endpunkt des Kerns übergibt ohne Parameter null, der Standardwert macht daraus {}.
						'default'              => array(),
						'properties'           => $def['properties'],
						'required'             => $def['required'] ?? array(),
						'additionalProperties' => false,
					),
					'execute_callback'    => $def['execute'],
					'permission_callback' => $def['permission'],
					'meta'                => array(
						// meta.public gibt es im Core erst ab 7.1, der MCP Adapter liest zusätzlich meta.mcp.public.
						'public'       => true,
						'show_in_rest' => true,
						'mcp'          => array( 'public' => true ),
						'annotations'  => array(
							'readonly'    => $readonly,
							'destructive' => ! empty( $def['destructive'] ),
							'idempotent'  => $readonly,
						),
					),
				)
			);
		}
	}

	/**
	 * @return array<string, array<string, mixed>>
	 */
	private static function definitions() {
		$confirm = array(
			'type'        => 'boolean',
			'default'     => false,
			'description' => 'Ohne true wird nichts geändert, es kommt nur eine Vorschau.',
		);
		$terms   = array(
			'type'  => 'array',
			'items' => array( 'type' => array( 'integer', 'string' ) ),
		);
		$fields  = array(
			'title'          => array(
				'type'        => 'string',
				'description' => 'Titel.',
			),
			'content'        => array(
				'type'        => 'string',
				'description' => 'Inhalt als HTML oder als Gutenberg-Block-Markup (<!-- wp:paragraph -->...). Wird unverändert gespeichert.',
			),
			'status'         => array(
				'type'        => 'string',
				'enum'        => self::STATUSES,
				'description' => 'draft, pending, publish, future oder private. publish mit Datum in der Zukunft wird zu future.',
			),
			'date'           => array(
				'type'        => 'string',
				'description' => 'Veröffentlichungsdatum: YYYY-MM-DD, YYYY-MM-DD HH:MM[:SS] oder ISO 8601 mit Zeitzone. Ohne Zeitzone gilt die Zeitzone der Seite, ohne Uhrzeit 00:00.',
			),
			'categories'     => $terms + array( 'description' => 'Nur Beiträge. Kategorien als ID, Slug oder Name; müssen existieren. Ersetzt die bisherigen.' ),
			'tags'           => $terms + array( 'description' => 'Nur Beiträge. Schlagwörter als ID oder Name; fehlende Namen werden angelegt. Ersetzt die bisherigen.' ),
			'featured_media' => array(
				'type'        => 'integer',
				'minimum'     => 0,
				'description' => 'ID eines Bildes aus der Mediathek als Beitragsbild, 0 entfernt es.',
			),
			'excerpt'        => array(
				'type'        => 'string',
				'description' => 'Auszug.',
			),
			'slug'           => array(
				'type'        => 'string',
				'description' => 'Titelform (URL-Teil).',
			),
		);
		$id      = array(
			'type'        => 'integer',
			'minimum'     => 1,
			'description' => 'ID des Beitrags oder der Seite.',
		);
		$limit   = array(
			'type'    => 'integer',
			'minimum' => 1,
			'maximum' => self::MAX_LIMIT,
			'default' => 20,
		);
		$page    = array(
			'type'    => 'integer',
			'minimum' => 1,
			'default' => 1,
		);
		$search  = array( 'type' => 'string' );

		return array(
			'get-version'   => array(
				'label'       => 'Version',
				'description' => 'Version und Commit von tabside MCP, WordPress-, MCP-Adapter- und PHP-Version.',
				'readonly'    => true,
				'properties'  => array(),
				'permission'  => static function () {
					return Tabside_MCP_Plugin::check_user( 'edit_posts' );
				},
				'execute'     => array( __CLASS__, 'get_version' ),
			),
			'post-list'     => array(
				'label'       => 'Beiträge auflisten',
				'description' => 'Listet Beiträge oder Seiten, neueste zuerst. Filter: Typ, Status, Suche, Kategorie.',
				'readonly'    => true,
				'properties'  => array(
					'type'     => array(
						'type'    => 'string',
						'enum'    => array( 'post', 'page', 'any' ),
						'default' => 'post',
					),
					'status'   => array(
						'type'    => 'string',
						'enum'    => array_merge( self::STATUSES, array( 'trash', 'any' ) ),
						'default' => 'any',
					),
					'search'   => $search,
					'category' => array(
						'type'        => array( 'integer', 'string' ),
						'description' => 'Kategorie-ID oder Slug (nur Beiträge).',
					),
					'limit'    => $limit,
					'page'     => $page,
				),
				'permission'  => static function () {
					return Tabside_MCP_Plugin::check_user( 'edit_posts' );
				},
				'execute'     => array( __CLASS__, 'post_list' ),
			),
			'post-get'      => array(
				'label'       => 'Beitrag abrufen',
				'description' => 'Ein Beitrag oder eine Seite mit Inhalt (roh), Datum, Kategorien, Schlagwörtern, Beitragsbild und den vorhandenen Sicherungen.',
				'readonly'    => true,
				'properties'  => array( 'id' => $id ),
				'required'    => array( 'id' ),
				'permission'  => static function ( $input ) {
					return self::check_post_permission( $input, 'edit_post' );
				},
				'execute'     => array( __CLASS__, 'post_get' ),
			),
			'category-list' => array(
				'label'       => 'Kategorien auflisten',
				'description' => 'Kategorien mit ID, Name, Slug, Eltern-ID und Anzahl Beiträge.',
				'readonly'    => true,
				'properties'  => array(
					'search' => $search,
					'limit'  => array_merge( $limit, array( 'default' => 100 ) ),
				),
				'permission'  => static function () {
					return Tabside_MCP_Plugin::check_user( 'edit_posts' );
				},
				'execute'     => static function ( $input ) {
					return self::term_list( 'category', $input );
				},
			),
			'tag-list'      => array(
				'label'       => 'Schlagwörter auflisten',
				'description' => 'Schlagwörter mit ID, Name, Slug und Anzahl Beiträge.',
				'readonly'    => true,
				'properties'  => array(
					'search' => $search,
					'limit'  => array_merge( $limit, array( 'default' => 100 ) ),
				),
				'permission'  => static function () {
					return Tabside_MCP_Plugin::check_user( 'edit_posts' );
				},
				'execute'     => static function ( $input ) {
					return self::term_list( 'post_tag', $input );
				},
			),
			'media-list'    => array(
				'label'       => 'Medien auflisten',
				'description' => 'Dateien der Mediathek, neueste zuerst, mit URL zum Verlinken.',
				'readonly'    => true,
				'properties'  => array(
					'search'    => $search,
					'mime_type' => array(
						'type'        => 'string',
						'description' => 'z.B. application/pdf oder image.',
					),
					'limit'     => $limit,
					'page'      => $page,
				),
				'permission'  => static function () {
					return Tabside_MCP_Plugin::check_user( 'upload_files' );
				},
				'execute'     => array( __CLASS__, 'media_list' ),
			),
			'post-create'   => array(
				'label'       => 'Beitrag anlegen',
				'description' => 'Legt einen Beitrag oder eine Seite an. Ohne confirm=true nur Vorschau.',
				'properties'  => array_merge(
					array(
						'type' => array(
							'type'    => 'string',
							'enum'    => self::POST_TYPES,
							'default' => 'post',
						),
					),
					$fields,
					array( 'confirm' => $confirm )
				),
				'required'    => array( 'title' ),
				'permission'  => array( __CLASS__, 'permission_create' ),
				'execute'     => array( __CLASS__, 'post_create' ),
			),
			'post-update'   => array(
				'label'       => 'Beitrag ändern',
				'description' => 'Ändert nur die übergebenen Felder. Vorher wird der alte Stand gesichert (post-rollback). Ohne confirm=true nur Vorschau.',
				'properties'  => array_merge( array( 'id' => $id ), $fields, array( 'confirm' => $confirm ) ),
				'required'    => array( 'id' ),
				'permission'  => array( __CLASS__, 'permission_update' ),
				'execute'     => array( __CLASS__, 'post_update' ),
			),
			'media-upload'  => array(
				'label'       => 'Datei hochladen',
				'description' => 'Lädt eine Datei (Base64) in die Mediathek, z.B. PDF oder Bild, und gibt die URL zum Verlinken zurück. Ohne confirm=true nur Vorschau.',
				'properties'  => array(
					'filename'    => array(
						'type'        => 'string',
						'description' => 'Dateiname mit Endung, z.B. merkblatt.pdf.',
					),
					'data_base64' => array(
						'type'        => 'string',
						'description' => 'Dateiinhalt als Base64 (optional mit data:-Präfix).',
					),
					'title'       => array( 'type' => 'string' ),
					'alt_text'    => array( 'type' => 'string' ),
					'caption'     => array( 'type' => 'string' ),
					'description' => array( 'type' => 'string' ),
					'post_id'     => array(
						'type'        => 'integer',
						'minimum'     => 1,
						'description' => 'Optional: Datei diesem Beitrag zuordnen.',
					),
					'confirm'     => $confirm,
				),
				'required'    => array( 'filename', 'data_base64' ),
				'permission'  => static function ( $input ) {
					$ok = Tabside_MCP_Plugin::check_user( 'upload_files' );
					if ( true === $ok && ! empty( $input['post_id'] ) ) {
						$ok = self::check_post_permission( array( 'id' => $input['post_id'] ), 'edit_post' );
					}
					return $ok;
				},
				'execute'     => array( __CLASS__, 'media_upload' ),
			),
			'post-trash'    => array(
				'label'       => 'In den Papierkorb',
				'description' => 'Verschiebt einen Beitrag oder eine Seite in den Papierkorb (kein endgültiges Löschen). Ohne confirm=true nur Vorschau.',
				'destructive' => true,
				'properties'  => array(
					'id'      => $id,
					'confirm' => $confirm,
				),
				'required'    => array( 'id' ),
				'permission'  => static function ( $input ) {
					return self::check_post_permission( $input, 'delete_post' );
				},
				'execute'     => array( __CLASS__, 'post_trash' ),
			),
			'post-rollback' => array(
				'label'       => 'Sicherung zurückholen',
				'description' => 'Stellt einen Beitrag aus einer Sicherung wieder her (Standard: neueste). Der aktuelle Stand wird vorher ebenfalls gesichert. Ohne confirm=true nur Vorschau.',
				'properties'  => array(
					'id'        => $id,
					'backup_id' => array(
						'type'        => 'string',
						'description' => 'ID aus post-get (backups). Leer = neueste Sicherung.',
					),
					'confirm'   => $confirm,
				),
				'required'    => array( 'id' ),
				'permission'  => static function ( $input ) {
					return self::check_post_permission( $input, 'edit_post' );
				},
				'execute'     => array( __CLASS__, 'post_rollback' ),
			),
		);
	}

	/* ------------------------------------------------------------------ Berechtigung */

	/**
	 * @param array  $input      Eingabe mit id.
	 * @param string $capability edit_post | delete_post.
	 * @return true|WP_Error
	 */
	private static function check_post_permission( $input, $capability ) {
		$ok = Tabside_MCP_Plugin::check_user();
		if ( true !== $ok ) {
			return $ok;
		}
		$post = self::load_post( (int) ( $input['id'] ?? 0 ) );
		if ( is_wp_error( $post ) ) {
			return $post;
		}
		return Tabside_MCP_Plugin::check_user( $capability, $post->ID );
	}

	public static function permission_create( $input ) {
		$type = $input['type'] ?? 'post';
		$obj  = get_post_type_object( $type );
		if ( ! $obj || ! in_array( $type, self::POST_TYPES, true ) ) {
			return new WP_Error( 'tabside_mcp_invalid_type', 'Nur post oder page.' );
		}
		$ok = Tabside_MCP_Plugin::check_user( $obj->cap->create_posts );
		if ( true === $ok && in_array( $input['status'] ?? 'draft', array( 'publish', 'future', 'private' ), true ) ) {
			$ok = Tabside_MCP_Plugin::check_user( $obj->cap->publish_posts );
		}
		return $ok;
	}

	public static function permission_update( $input ) {
		$ok = self::check_post_permission( $input, 'edit_post' );
		if ( true === $ok && in_array( $input['status'] ?? '', array( 'publish', 'future', 'private' ), true ) ) {
			$post = get_post( (int) $input['id'] );
			$ok   = Tabside_MCP_Plugin::check_user( get_post_type_object( $post->post_type )->cap->publish_posts );
		}
		return $ok;
	}

	/* ------------------------------------------------------------------ Lesen */

	public static function get_version() {
		return array(
			'plugin'        => 'tabside-mcp',
			'version'       => TABSIDE_MCP_VERSION,
			'commit'        => TABSIDE_MCP_COMMIT,
			'wordpress'     => get_bloginfo( 'version' ),
			'mcp_adapter'   => defined( 'WP_MCP_VERSION' ) ? WP_MCP_VERSION : null,
			'php'           => PHP_VERSION,
			'site_url'      => home_url( '/' ),
			'timezone'      => wp_timezone_string(),
			'allowed_user'  => Tabside_MCP_Plugin::allowed_login(),
			'max_upload_mb' => round( wp_max_upload_size() / 1048576, 1 ),
		);
	}

	public static function post_list( $input ) {
		$type  = $input['type'] ?? 'post';
		$limit = min( self::MAX_LIMIT, max( 1, (int) ( $input['limit'] ?? 20 ) ) );
		$page  = max( 1, (int) ( $input['page'] ?? 1 ) );
		$args  = array(
			'post_type'           => 'any' === $type ? self::POST_TYPES : $type,
			'post_status'         => $input['status'] ?? 'any',
			'posts_per_page'      => $limit,
			'paged'               => $page,
			'orderby'             => 'date',
			'order'               => 'DESC',
			'ignore_sticky_posts' => true,
		);
		if ( ! empty( $input['search'] ) ) {
			$args['s'] = (string) $input['search'];
		}
		if ( isset( $input['category'] ) && '' !== $input['category'] ) {
			if ( is_numeric( $input['category'] ) ) {
				$args['cat'] = (int) $input['category'];
			} else {
				$args['category_name'] = sanitize_title( (string) $input['category'] );
			}
		}
		$query = new WP_Query( $args );
		return array(
			'total' => (int) $query->found_posts,
			'page'  => $page,
			'pages' => (int) $query->max_num_pages,
			'posts' => array_map( array( __CLASS__, 'summary' ), $query->posts ),
		);
	}

	public static function post_get( $input ) {
		$post = self::load_post( (int) $input['id'] );
		if ( is_wp_error( $post ) ) {
			return $post;
		}
		return self::details( $post );
	}

	private static function term_list( $taxonomy, $input ) {
		$args = array(
			'taxonomy'   => $taxonomy,
			'hide_empty' => false,
			'number'     => min( self::MAX_LIMIT, max( 1, (int) ( $input['limit'] ?? 100 ) ) ),
			'orderby'    => 'name',
		);
		if ( ! empty( $input['search'] ) ) {
			$args['search'] = (string) $input['search'];
		}
		$terms = get_terms( $args );
		if ( is_wp_error( $terms ) ) {
			return $terms;
		}
		$out = array();
		foreach ( $terms as $term ) {
			$out[] = array(
				'id'     => (int) $term->term_id,
				'name'   => $term->name,
				'slug'   => $term->slug,
				'parent' => (int) $term->parent,
				'count'  => (int) $term->count,
			);
		}
		return array( 'terms' => $out );
	}

	public static function media_list( $input ) {
		$limit = min( self::MAX_LIMIT, max( 1, (int) ( $input['limit'] ?? 20 ) ) );
		$page  = max( 1, (int) ( $input['page'] ?? 1 ) );
		$args  = array(
			'post_type'      => 'attachment',
			'post_status'    => 'inherit',
			'posts_per_page' => $limit,
			'paged'          => $page,
			'orderby'        => 'date',
			'order'          => 'DESC',
		);
		if ( ! empty( $input['search'] ) ) {
			$args['s'] = (string) $input['search'];
		}
		if ( ! empty( $input['mime_type'] ) ) {
			$args['post_mime_type'] = (string) $input['mime_type'];
		}
		$query = new WP_Query( $args );
		return array(
			'total' => (int) $query->found_posts,
			'page'  => $page,
			'pages' => (int) $query->max_num_pages,
			'media' => array_map( array( __CLASS__, 'media_summary' ), $query->posts ),
		);
	}

	/* ------------------------------------------------------------------ Schreiben */

	public static function post_create( $input ) {
		$type    = $input['type'] ?? 'post';
		$status  = $input['status'] ?? 'draft';
		$notes   = array();
		$changes = self::prepare_fields( $input, $type, $notes );
		if ( is_wp_error( $changes ) ) {
			return $changes;
		}
		$ts        = isset( $changes['date'] ) ? $changes['date']['ts'] : null;
		$effective = self::effective_status( $status, $ts );
		if ( is_wp_error( $effective ) ) {
			return $effective;
		}
		if ( $effective !== $status ) {
			$notes[] = sprintf( 'Status %s wird wegen des Datums zu %s.', $status, $effective );
		}

		$preview = array(
			'type'    => $type,
			'title'   => $input['title'],
			'status'  => $effective,
			'date'    => isset( $changes['date'] ) ? $changes['date']['local'] : 'jetzt',
			'content' => self::text_preview( $input['content'] ?? '' ),
		);
		foreach ( array( 'categories', 'tags', 'featured_media', 'excerpt', 'slug' ) as $key ) {
			if ( array_key_exists( $key, $changes ) ) {
				$preview[ $key ] = self::describe( $key, $changes[ $key ] );
			}
		}
		if ( empty( $input['confirm'] ) ) {
			return self::preview_result( $preview, $notes );
		}

		$postarr = array(
			'post_type'    => $type,
			'post_title'   => (string) $input['title'],
			'post_content' => (string) ( $input['content'] ?? '' ),
			'post_status'  => $effective,
			'post_author'  => get_current_user_id(),
		);
		$postarr = array_merge( $postarr, self::postarr_from_changes( $changes ) );
		// wp_insert_post() erwartet Daten mit Slashes.
		$post_id = wp_insert_post( wp_slash( $postarr ), true );
		if ( is_wp_error( $post_id ) ) {
			return $post_id;
		}
		$applied = self::apply_terms_and_thumbnail( $post_id, $changes );
		if ( is_wp_error( $applied ) ) {
			return $applied;
		}
		return array(
			'confirmed' => true,
			'notes'     => $notes,
			'post'      => self::details( get_post( $post_id ) ),
		);
	}

	public static function post_update( $input ) {
		$post = self::load_post( (int) $input['id'] );
		if ( is_wp_error( $post ) ) {
			return $post;
		}
		$notes   = array();
		$changes = self::prepare_fields( $input, $post->post_type, $notes );
		if ( is_wp_error( $changes ) ) {
			return $changes;
		}
		foreach ( array( 'title', 'content', 'status' ) as $key ) {
			if ( array_key_exists( $key, $input ) ) {
				$changes[ $key ] = (string) $input[ $key ];
			}
		}
		if ( empty( $changes ) ) {
			return new WP_Error( 'tabside_mcp_nothing_to_update', 'Keine Felder zum Ändern übergeben.' );
		}

		// Status neu bestimmen, wenn Status oder Datum sich ändern.
		$status = $changes['status'] ?? $post->post_status;
		if ( isset( $changes['status'] ) || isset( $changes['date'] ) ) {
			$ts = null;
			if ( isset( $changes['date'] ) ) {
				$ts = $changes['date']['ts'];
			} elseif ( '0000-00-00 00:00:00' !== $post->post_date_gmt ) {
				$ts = strtotime( $post->post_date_gmt . ' UTC' );
			}
			$effective = self::effective_status( $status, $ts );
			if ( is_wp_error( $effective ) ) {
				return $effective;
			}
			if ( $effective !== $status ) {
				$notes[] = sprintf( 'Status %s wird wegen des Datums zu %s.', $status, $effective );
			}
			if ( $effective !== $post->post_status ) {
				$changes['status'] = $effective;
				if ( in_array( $effective, array( 'publish', 'future', 'private' ), true )
					&& ! current_user_can( get_post_type_object( $post->post_type )->cap->publish_posts ) ) {
					return new WP_Error( 'tabside_mcp_forbidden', 'Fehlende Berechtigung zum Veröffentlichen.' );
				}
			} else {
				unset( $changes['status'] );
			}
		}

		$before  = Tabside_MCP_Backups::snapshot( $post );
		$preview = array();
		foreach ( $changes as $key => $value ) {
			$preview[ $key ] = array(
				'old' => self::describe( $key, $before[ $key ] ?? null, $post ),
				'new' => self::describe( $key, $value, $post ),
			);
		}
		if ( empty( $input['confirm'] ) ) {
			return self::preview_result(
				array(
					'post'    => self::summary( $post ),
					'changes' => $preview,
				),
				$notes
			);
		}

		$backup_id = Tabside_MCP_Backups::create( $post, 'update' );
		$postarr   = array_merge( array( 'ID' => $post->ID ), self::postarr_from_changes( $changes ) );
		if ( isset( $changes['title'] ) ) {
			$postarr['post_title'] = $changes['title'];
		}
		if ( isset( $changes['content'] ) ) {
			$postarr['post_content'] = $changes['content'];
		}
		if ( isset( $changes['status'] ) ) {
			$postarr['post_status'] = $changes['status'];
		}
		$result = wp_update_post( wp_slash( $postarr ), true );
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		$applied = self::apply_terms_and_thumbnail( $post->ID, $changes );
		if ( is_wp_error( $applied ) ) {
			return $applied;
		}
		return array(
			'confirmed' => true,
			'backup_id' => $backup_id,
			'notes'     => $notes,
			'post'      => self::details( get_post( $post->ID ) ),
		);
	}

	public static function media_upload( $input ) {
		$filename = sanitize_file_name( (string) $input['filename'] );
		$check    = wp_check_filetype( $filename );
		if ( '' === $filename || empty( $check['ext'] ) || empty( $check['type'] ) ) {
			return new WP_Error( 'tabside_mcp_filetype', 'Dateityp ist auf dieser Seite nicht erlaubt oder der Dateiname hat keine Endung.' );
		}
		$data = (string) $input['data_base64'];
		if ( 0 === strpos( $data, 'data:' ) && false !== strpos( $data, ',' ) ) {
			$data = substr( $data, strpos( $data, ',' ) + 1 );
		}
		$data   = preg_replace( '/\s+/', '', $data );
		$max    = (int) wp_max_upload_size();
		$binary = base64_decode( $data, true ); // phpcs:ignore WordPress.PHP.DiscouragedPHPFunctions.obfuscation_base64_decode
		if ( false === $binary || '' === $binary ) {
			return new WP_Error( 'tabside_mcp_base64', 'data_base64 ist kein gültiges Base64.' );
		}
		$size = strlen( $binary );
		if ( $max > 0 && $size > $max ) {
			return new WP_Error( 'tabside_mcp_too_large', sprintf( 'Datei ist %s gross, erlaubt sind %s.', size_format( $size ), size_format( $max ) ) );
		}
		$preview = array(
			'filename'  => $filename,
			'mime_type' => $check['type'],
			'size'      => size_format( $size ),
			'title'     => $input['title'] ?? preg_replace( '/\.[^.]+$/', '', $filename ),
			'post_id'   => $input['post_id'] ?? null,
		);
		if ( empty( $input['confirm'] ) ) {
			return self::preview_result( $preview, array() );
		}

		require_once ABSPATH . 'wp-admin/includes/file.php';
		require_once ABSPATH . 'wp-admin/includes/media.php';
		require_once ABSPATH . 'wp-admin/includes/image.php';

		$tmp = wp_tempnam( $filename );
		if ( ! $tmp || false === file_put_contents( $tmp, $binary ) ) { // phpcs:ignore WordPress.WP.AlternativeFunctions.file_system_operations_file_put_contents
			return new WP_Error( 'tabside_mcp_tmp', 'Temporäre Datei konnte nicht geschrieben werden.' );
		}
		$file_array = array(
			'name'     => $filename,
			'tmp_name' => $tmp,
		);
		$post_data  = array();
		if ( isset( $input['caption'] ) ) {
			$post_data['post_excerpt'] = (string) $input['caption'];
		}
		if ( isset( $input['description'] ) ) {
			$post_data['post_content'] = (string) $input['description'];
		}
		$title = isset( $input['title'] ) ? (string) $input['title'] : null;
		$id    = media_handle_sideload( $file_array, (int) ( $input['post_id'] ?? 0 ), $title, $post_data );
		if ( file_exists( $tmp ) ) {
			wp_delete_file( $tmp );
		}
		if ( is_wp_error( $id ) ) {
			return $id;
		}
		if ( isset( $input['alt_text'] ) ) {
			update_post_meta( $id, '_wp_attachment_image_alt', wp_slash( sanitize_text_field( (string) $input['alt_text'] ) ) );
		}
		return array(
			'confirmed' => true,
			'media'     => self::media_summary( get_post( $id ) ),
		);
	}

	public static function post_trash( $input ) {
		$post = self::load_post( (int) $input['id'] );
		if ( is_wp_error( $post ) ) {
			return $post;
		}
		if ( 'trash' === $post->post_status ) {
			return new WP_Error( 'tabside_mcp_already_trashed', 'Liegt bereits im Papierkorb.' );
		}
		if ( empty( $input['confirm'] ) ) {
			return self::preview_result( array( 'post' => self::summary( $post ) ), array( 'Wird in den Papierkorb verschoben und kann dort wiederhergestellt werden.' ) );
		}
		if ( ! wp_trash_post( $post->ID ) ) {
			return new WP_Error( 'tabside_mcp_trash_failed', 'Verschieben in den Papierkorb fehlgeschlagen.' );
		}
		return array(
			'confirmed' => true,
			'post'      => self::summary( get_post( $post->ID ) ),
		);
	}

	public static function post_rollback( $input ) {
		$post = self::load_post( (int) $input['id'] );
		if ( is_wp_error( $post ) ) {
			return $post;
		}
		$backup = Tabside_MCP_Backups::find( $post->ID, $input['backup_id'] ?? null );
		if ( null === $backup ) {
			return new WP_Error( 'tabside_mcp_no_backup', 'Keine passende Sicherung vorhanden.' );
		}
		$target  = $backup['fields'];
		$current = Tabside_MCP_Backups::snapshot( $post );
		$changes = array();
		foreach ( $target as $key => $value ) {
			if ( 'date_gmt' === $key ) {
				continue;
			}
			if ( self::comparable( $current[ $key ] ?? null ) !== self::comparable( $value ) ) {
				$changes[ $key ] = array(
					'old' => self::describe( $key, $current[ $key ] ?? null, $post ),
					'new' => self::describe( $key, $value, $post ),
				);
			}
		}
		$notes = array();
		if ( empty( $changes ) ) {
			$notes[] = 'Der aktuelle Stand entspricht bereits dieser Sicherung.';
		}
		if ( empty( $input['confirm'] ) ) {
			return self::preview_result(
				array(
					'post'        => self::summary( $post ),
					'backup_id'   => $backup['id'],
					'backup_time' => $backup['created_gmt'] . ' UTC',
					'changes'     => $changes,
				),
				$notes
			);
		}
		if ( in_array( $target['status'], array( 'publish', 'future', 'private' ), true )
			&& ! current_user_can( get_post_type_object( $post->post_type )->cap->publish_posts ) ) {
			return new WP_Error( 'tabside_mcp_forbidden', 'Fehlende Berechtigung zum Veröffentlichen.' );
		}

		$safety  = Tabside_MCP_Backups::create( $post, 'rollback' );
		$postarr = array(
			'ID'            => $post->ID,
			'post_title'    => $target['title'],
			'post_content'  => $target['content'],
			'post_excerpt'  => $target['excerpt'],
			'post_status'   => $target['status'],
			'post_name'     => $target['slug'],
			'post_date'     => $target['date'],
			'post_date_gmt' => $target['date_gmt'],
			'edit_date'     => true,
		);
		$result  = wp_update_post( wp_slash( $postarr ), true );
		if ( is_wp_error( $result ) ) {
			return $result;
		}
		if ( 'post' === $post->post_type ) {
			wp_set_post_categories( $post->ID, $target['categories'] ?? array() );
			wp_set_post_terms( $post->ID, $target['tags'] ?? array(), 'post_tag' );
		}
		if ( ! empty( $target['featured_media'] ) ) {
			set_post_thumbnail( $post->ID, (int) $target['featured_media'] );
		} else {
			delete_post_thumbnail( $post->ID );
		}
		return array(
			'confirmed'        => true,
			'restored_backup'  => $backup['id'],
			'safety_backup_id' => $safety,
			'post'             => self::details( get_post( $post->ID ) ),
		);
	}

	/* ------------------------------------------------------------------ Hilfen */

	/**
	 * @param int $id ID.
	 * @return WP_Post|WP_Error
	 */
	private static function load_post( $id ) {
		$post = $id > 0 ? get_post( $id ) : null;
		if ( ! $post || ! in_array( $post->post_type, self::POST_TYPES, true ) || 'auto-draft' === $post->post_status ) {
			return new WP_Error( 'tabside_mcp_not_found', sprintf( 'Beitrag/Seite %d nicht gefunden.', $id ), array( 'status' => 404 ) );
		}
		return $post;
	}

	/**
	 * Prüft und normalisiert date, categories, tags, featured_media, excerpt, slug.
	 *
	 * @param array    $input Eingabe.
	 * @param string   $type  post | page.
	 * @param string[] $notes Hinweise (Ausgabe).
	 * @return array<string, mixed>|WP_Error
	 */
	private static function prepare_fields( $input, $type, &$notes ) {
		$changes = array();
		if ( isset( $input['date'] ) && '' !== $input['date'] ) {
			$date = self::parse_date( (string) $input['date'] );
			if ( is_wp_error( $date ) ) {
				return $date;
			}
			if ( ! $date['has_time'] ) {
				$notes[] = 'Keine Uhrzeit angegeben, es gilt 00:00 (' . wp_timezone_string() . ').';
			}
			$changes['date'] = $date;
		}
		if ( 'post' !== $type && ( ! empty( $input['categories'] ) || ! empty( $input['tags'] ) ) ) {
			return new WP_Error( 'tabside_mcp_terms_on_page', 'Kategorien und Schlagwörter gibt es nur bei Beiträgen.' );
		}
		if ( isset( $input['categories'] ) ) {
			$ids = self::resolve_categories( (array) $input['categories'] );
			if ( is_wp_error( $ids ) ) {
				return $ids;
			}
			$changes['categories'] = $ids;
		}
		if ( isset( $input['tags'] ) ) {
			$tags = self::resolve_tags( (array) $input['tags'] );
			if ( is_wp_error( $tags ) ) {
				return $tags;
			}
			if ( ! empty( $tags['new'] ) ) {
				$notes[] = 'Neue Schlagwörter werden angelegt: ' . implode( ', ', $tags['new'] );
			}
			$changes['tags'] = $tags;
		}
		if ( isset( $input['featured_media'] ) ) {
			$media_id = (int) $input['featured_media'];
			if ( $media_id > 0 ) {
				$att = get_post( $media_id );
				if ( ! $att || 'attachment' !== $att->post_type || ! wp_attachment_is_image( $att ) ) {
					return new WP_Error( 'tabside_mcp_featured_media', sprintf( 'Medium %d ist kein Bild aus der Mediathek.', $media_id ) );
				}
			}
			$changes['featured_media'] = $media_id;
		}
		foreach ( array( 'excerpt', 'slug' ) as $key ) {
			if ( isset( $input[ $key ] ) ) {
				$changes[ $key ] = (string) $input[ $key ];
			}
		}
		return $changes;
	}

	private static function postarr_from_changes( $changes ) {
		$postarr = array();
		if ( isset( $changes['date'] ) ) {
			$postarr['post_date']     = $changes['date']['local'];
			$postarr['post_date_gmt'] = $changes['date']['gmt'];
			// Sonst setzt wp_update_post() das Datum von Entwürfen zurück.
			$postarr['edit_date'] = true;
		}
		if ( isset( $changes['excerpt'] ) ) {
			$postarr['post_excerpt'] = $changes['excerpt'];
		}
		if ( isset( $changes['slug'] ) ) {
			$postarr['post_name'] = sanitize_title( $changes['slug'] );
		}
		return $postarr;
	}

	/**
	 * @return true|WP_Error
	 */
	private static function apply_terms_and_thumbnail( $post_id, $changes ) {
		if ( isset( $changes['categories'] ) ) {
			wp_set_post_categories( $post_id, $changes['categories'] );
		}
		if ( isset( $changes['tags'] ) ) {
			$ids = $changes['tags']['ids'];
			foreach ( $changes['tags']['new'] as $name ) {
				$term = wp_insert_term( $name, 'post_tag' );
				if ( is_wp_error( $term ) ) {
					$existing = $term->get_error_data( 'term_exists' );
					if ( ! $existing ) {
						return $term;
					}
					$ids[] = (int) $existing;
				} else {
					$ids[] = (int) $term['term_id'];
				}
			}
			wp_set_post_terms( $post_id, $ids, 'post_tag' );
		}
		if ( isset( $changes['featured_media'] ) ) {
			if ( $changes['featured_media'] > 0 ) {
				set_post_thumbnail( $post_id, $changes['featured_media'] );
			} else {
				delete_post_thumbnail( $post_id );
			}
		}
		return true;
	}

	/**
	 * @return array{local: string, gmt: string, ts: int, has_time: bool}|WP_Error
	 */
	private static function parse_date( $value ) {
		$value = trim( $value );
		$re    = '/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?)?\s*(Z|[+-]\d{2}:?\d{2})?$/i';
		if ( ! preg_match( $re, $value, $m ) || ! checkdate( (int) $m[2], (int) $m[3], (int) $m[1] ) ) {
			return new WP_Error( 'tabside_mcp_date', sprintf( 'Datum "%s" nicht lesbar. Erwartet YYYY-MM-DD oder YYYY-MM-DD HH:MM.', $value ) );
		}
		$has_time = isset( $m[4] ) && '' !== $m[4];
		$hour     = $has_time ? (int) $m[4] : 0;
		$minute   = $has_time ? (int) $m[5] : 0;
		$second   = isset( $m[6] ) && '' !== $m[6] ? (int) $m[6] : 0;
		if ( $hour > 23 || $minute > 59 || $second > 59 ) {
			return new WP_Error( 'tabside_mcp_date', sprintf( 'Uhrzeit in "%s" ungültig.', $value ) );
		}
		if ( isset( $m[7] ) && '' !== $m[7] ) {
			$tz = new DateTimeZone( 'Z' === strtoupper( $m[7] ) ? 'UTC' : $m[7] );
		} else {
			$tz = wp_timezone();
		}
		$dt = DateTimeImmutable::createFromFormat(
			'Y-m-d H:i:s',
			sprintf( '%04d-%02d-%02d %02d:%02d:%02d', $m[1], $m[2], $m[3], $hour, $minute, $second ),
			$tz
		);
		if ( ! $dt ) {
			return new WP_Error( 'tabside_mcp_date', sprintf( 'Datum "%s" nicht lesbar.', $value ) );
		}
		return array(
			'local'    => $dt->setTimezone( wp_timezone() )->format( 'Y-m-d H:i:s' ),
			'gmt'      => $dt->setTimezone( new DateTimeZone( 'UTC' ) )->format( 'Y-m-d H:i:s' ),
			'ts'       => $dt->getTimestamp(),
			'has_time' => $has_time,
		);
	}

	/**
	 * publish mit Datum in der Zukunft wird future, future braucht ein Datum in der Zukunft.
	 *
	 * @return string|WP_Error
	 */
	private static function effective_status( $status, $ts ) {
		if ( ! in_array( $status, array( 'publish', 'future' ), true ) ) {
			return $status;
		}
		if ( null === $ts ) {
			if ( 'future' === $status ) {
				return new WP_Error( 'tabside_mcp_future_needs_date', 'Status future braucht ein Datum in der Zukunft.' );
			}
			return 'publish';
		}
		if ( $ts > time() ) {
			return 'future';
		}
		if ( 'future' === $status ) {
			return new WP_Error( 'tabside_mcp_date_past', 'Status future, aber das Datum liegt nicht in der Zukunft.' );
		}
		return 'publish';
	}

	/**
	 * @return int[]|WP_Error
	 */
	private static function resolve_categories( array $items ) {
		$ids     = array();
		$missing = array();
		foreach ( $items as $item ) {
			$term = self::find_term( $item, 'category' );
			if ( $term ) {
				$ids[] = (int) $term->term_id;
			} else {
				$missing[] = (string) $item;
			}
		}
		if ( $missing ) {
			return new WP_Error( 'tabside_mcp_category_missing', 'Kategorie nicht gefunden: ' . implode( ', ', $missing ) . '. Vorhandene Kategorien liefert category-list.' );
		}
		return array_values( array_unique( $ids ) );
	}

	/**
	 * @return array{ids: int[], new: string[]}|WP_Error
	 */
	private static function resolve_tags( array $items ) {
		$ids = array();
		$new = array();
		foreach ( $items as $item ) {
			$term = self::find_term( $item, 'post_tag' );
			if ( $term ) {
				$ids[] = (int) $term->term_id;
			} elseif ( is_numeric( $item ) ) {
				return new WP_Error( 'tabside_mcp_tag_missing', sprintf( 'Schlagwort-ID %s nicht gefunden.', $item ) );
			} elseif ( '' !== trim( (string) $item ) ) {
				$new[] = trim( (string) $item );
			}
		}
		return array(
			'ids' => array_values( array_unique( $ids ) ),
			'new' => array_values( array_unique( $new ) ),
		);
	}

	/**
	 * @return WP_Term|null
	 */
	private static function find_term( $item, $taxonomy ) {
		if ( is_numeric( $item ) ) {
			$term = get_term( (int) $item, $taxonomy );
			return $term instanceof WP_Term ? $term : null;
		}
		$item = trim( (string) $item );
		if ( '' === $item ) {
			return null;
		}
		$term = get_term_by( 'slug', sanitize_title( $item ), $taxonomy );
		if ( ! $term ) {
			$term = get_term_by( 'name', $item, $taxonomy );
		}
		return $term instanceof WP_Term ? $term : null;
	}

	/**
	 * Vergleichswert: Listen sortiert, Zahlen als int.
	 */
	private static function comparable( $value ) {
		if ( is_array( $value ) ) {
			$value = array_map( 'intval', $value );
			sort( $value );
			return $value;
		}
		return is_int( $value ) ? $value : (string) $value;
	}

	private static function preview_result( $preview, $notes ) {
		return array(
			'confirmed' => false,
			'preview'   => $preview,
			'notes'     => $notes,
			'hint'      => 'Nichts geändert. Zum Ausführen denselben Aufruf mit confirm=true wiederholen.',
		);
	}

	private static function text_preview( $html, $length = 300 ) {
		$text = trim( preg_replace( '/\s+/', ' ', wp_strip_all_tags( (string) $html ) ) );
		return array(
			'chars'  => strlen( (string) $html ),
			'blocks' => has_blocks( (string) $html ),
			'start'  => mb_substr( $text, 0, $length ) . ( mb_strlen( $text ) > $length ? ' …' : '' ),
		);
	}

	/**
	 * Lesbare Darstellung eines Feldwerts für Vorschauen.
	 */
	private static function describe( $key, $value, $post = null ) {
		switch ( $key ) {
			case 'content':
				return self::text_preview( $value );
			case 'date':
				return is_array( $value ) ? $value['local'] : $value;
			case 'categories':
				return self::term_names( (array) $value, 'category' );
			case 'tags':
				if ( is_array( $value ) && isset( $value['ids'] ) ) {
					return array_merge( self::term_names( $value['ids'], 'post_tag' ), array_map( static function ( $n ) {
						return $n . ' (neu)';
					}, $value['new'] ) );
				}
				return self::term_names( (array) $value, 'post_tag' );
			case 'featured_media':
				$id = (int) $value;
				return $id > 0 ? array(
					'id'  => $id,
					'url' => wp_get_attachment_url( $id ),
				) : null;
			default:
				return $value;
		}
	}

	private static function term_names( array $ids, $taxonomy ) {
		$out = array();
		foreach ( $ids as $id ) {
			$term  = get_term( (int) $id, $taxonomy );
			$out[] = $term instanceof WP_Term ? $term->name : '#' . (int) $id;
		}
		return $out;
	}

	private static function summary( WP_Post $post ) {
		return array(
			'id'       => $post->ID,
			'type'     => $post->post_type,
			'title'    => $post->post_title,
			'status'   => $post->post_status,
			'date'     => $post->post_date,
			'date_gmt' => '0000-00-00 00:00:00' === $post->post_date_gmt ? null : $post->post_date_gmt,
			'modified' => $post->post_modified,
			'slug'     => $post->post_name,
			'link'     => get_permalink( $post ),
			'author'   => get_the_author_meta( 'display_name', (int) $post->post_author ),
		);
	}

	private static function details( WP_Post $post ) {
		$out             = self::summary( $post );
		$out['content']  = $post->post_content;
		$out['format']   = has_blocks( $post->post_content ) ? 'blocks' : 'html';
		$out['excerpt']  = $post->post_excerpt;
		$out['edit_url'] = admin_url( 'post.php?post=' . $post->ID . '&action=edit' );
		if ( in_array( $post->post_status, array( 'draft', 'pending', 'future' ), true ) ) {
			$out['preview_url'] = get_preview_post_link( $post );
		}
		if ( 'post' === $post->post_type ) {
			$out['categories'] = self::terms_of( $post->ID, 'category' );
			$out['tags']       = self::terms_of( $post->ID, 'post_tag' );
		}
		$thumb                 = (int) get_post_thumbnail_id( $post );
		$out['featured_media'] = $thumb ? array(
			'id'  => $thumb,
			'url' => wp_get_attachment_url( $thumb ),
		) : null;
		$out['backups']        = Tabside_MCP_Backups::summary( $post->ID );
		return $out;
	}

	private static function terms_of( $post_id, $taxonomy ) {
		$terms = wp_get_post_terms( $post_id, $taxonomy );
		if ( is_wp_error( $terms ) ) {
			return array();
		}
		$out = array();
		foreach ( $terms as $term ) {
			$out[] = array(
				'id'   => (int) $term->term_id,
				'name' => $term->name,
				'slug' => $term->slug,
			);
		}
		return $out;
	}

	private static function media_summary( WP_Post $att ) {
		$file = get_attached_file( $att->ID );
		$meta = wp_get_attachment_metadata( $att->ID );
		$size = is_array( $meta ) && ! empty( $meta['filesize'] ) ? (int) $meta['filesize'] : ( $file && file_exists( $file ) ? (int) filesize( $file ) : null );
		return array(
			'id'        => $att->ID,
			'title'     => $att->post_title,
			'filename'  => $file ? wp_basename( $file ) : null,
			'url'       => wp_get_attachment_url( $att->ID ),
			'mime_type' => $att->post_mime_type,
			'size'      => $size,
			'date'      => $att->post_date,
			'alt_text'  => (string) get_post_meta( $att->ID, '_wp_attachment_image_alt', true ),
			'post_id'   => (int) $att->post_parent,
		);
	}
}
