<?php
/**
 * Sicherungen des alten Inhalts vor jedem Update (Post-Meta), Grundlage für post-rollback.
 *
 * Unabhängig von den WordPress-Revisionen, die auf manchen Hostings abgeschaltet sind.
 *
 * @package tabside-mcp
 */

defined( 'ABSPATH' ) || exit;

final class Tabside_MCP_Backups {

	const META_KEY = '_tabside_mcp_backups';
	const MAX      = 20;

	/**
	 * Aktueller Zustand eines Beitrags (alle Felder, die post-update ändern kann).
	 *
	 * @param WP_Post $post Beitrag.
	 * @return array<string, mixed>
	 */
	public static function snapshot( WP_Post $post ) {
		$fields = array(
			'title'          => $post->post_title,
			'content'        => $post->post_content,
			'excerpt'        => $post->post_excerpt,
			'status'         => $post->post_status,
			'date'           => $post->post_date,
			'date_gmt'       => $post->post_date_gmt,
			'slug'           => $post->post_name,
			'featured_media' => (int) get_post_thumbnail_id( $post ),
			'hide_featured_on_single' => Tabside_MCP_Abilities::get_hide_featured( $post->ID ),
		);
		if ( 'post' === $post->post_type ) {
			$fields['categories'] = array_map( 'intval', wp_get_post_categories( $post->ID ) );
			$fields['tags']       = array_map( 'intval', wp_get_post_tags( $post->ID, array( 'fields' => 'ids' ) ) );
		}
		return $fields;
	}

	/**
	 * @param int $post_id Beitrag.
	 * @return array<int, array<string, mixed>> Neueste zuerst.
	 */
	public static function all( $post_id ) {
		$list = get_post_meta( $post_id, self::META_KEY, true );
		return is_array( $list ) ? array_values( $list ) : array();
	}

	/**
	 * Sichert den aktuellen Zustand und gibt die ID der Sicherung zurück.
	 *
	 * @param WP_Post $post   Beitrag.
	 * @param string  $reason update | rollback.
	 * @return string
	 */
	public static function create( WP_Post $post, $reason ) {
		$id    = gmdate( 'Ymd-His' ) . '-' . strtolower( wp_generate_password( 6, false ) );
		$entry = array(
			'id'          => $id,
			'created_gmt' => gmdate( 'Y-m-d H:i:s' ),
			'reason'      => $reason,
			'user'        => wp_get_current_user()->user_login,
			'fields'      => self::snapshot( $post ),
		);
		$list = self::all( $post->ID );
		array_unshift( $list, $entry );
		$max  = (int) apply_filters( 'tabside_mcp_max_backups', self::MAX );
		$list = array_slice( $list, 0, max( 1, $max ) );
		// update_post_meta() entfernt Slashes, darum vorher wp_slash().
		update_post_meta( $post->ID, self::META_KEY, wp_slash( $list ) );
		return $id;
	}

	/**
	 * @param int         $post_id   Beitrag.
	 * @param string|null $backup_id ID oder null für die neueste Sicherung.
	 * @return array<string, mixed>|null
	 */
	public static function find( $post_id, $backup_id = null ) {
		foreach ( self::all( $post_id ) as $entry ) {
			if ( null === $backup_id || '' === $backup_id || $entry['id'] === $backup_id ) {
				return $entry;
			}
		}
		return null;
	}

	/**
	 * Kurzliste ohne Inhalt für post-get.
	 *
	 * @param int $post_id Beitrag.
	 * @return array<int, array<string, mixed>>
	 */
	public static function summary( $post_id ) {
		$out = array();
		foreach ( self::all( $post_id ) as $entry ) {
			$out[] = array(
				'id'          => $entry['id'],
				'created_gmt' => $entry['created_gmt'],
				'reason'      => $entry['reason'],
				'user'        => $entry['user'],
				'title'       => $entry['fields']['title'] ?? '',
				'status'      => $entry['fields']['status'] ?? '',
			);
		}
		return $out;
	}
}
