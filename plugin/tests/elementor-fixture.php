<?php
/**
 * Testdaten für den Integrationstest (wp eval-file): Elementor-Seite mit Container, Überschrift, Text,
 * Icon-Box mit Popup-Link und Vorlagen-Widget, zwei Popups, eine Abschnitts-Vorlage und ein leerer
 * Beitrag des eigenen Typs "service". Gibt die IDs als KEY=VALUE aus.
 *
 * Bewusst mit Sonderzeichen (Anführungszeichen, Backslash, Umlaute, Zeilenumbruch, </script>), damit
 * kaputte Escapes beim Kopieren auffallen.
 *
 * @package tabside-mcp
 */

$create = static function ( $type, $title, $template_type, array $elements, $extra_meta = array() ) {
	$id = wp_insert_post(
		array(
			'post_type'   => $type,
			'post_title'  => $title,
			'post_status' => 'publish',
		),
		true
	);
	if ( is_wp_error( $id ) ) {
		fwrite( STDERR, $id->get_error_message() );
		exit( 1 );
	}
	update_post_meta( $id, '_elementor_edit_mode', 'builder' );
	update_post_meta( $id, '_elementor_template_type', $template_type );
	update_post_meta( $id, '_elementor_version', ELEMENTOR_VERSION );
	update_post_meta( $id, '_elementor_data', wp_slash( wp_json_encode( $elements ) ) );
	foreach ( $extra_meta as $key => $value ) {
		update_post_meta( $id, $key, wp_slash( $value ) );
	}
	return $id;
};

$heading = static function ( $id, $text ) {
	return array(
		'id'         => $id,
		'elType'     => 'widget',
		'widgetType' => 'heading',
		'settings'   => array(
			'title'       => $text,
			'title_color' => '#1B4D46',
		),
		'elements'   => array(),
		'isInner'    => false,
	);
};

$container = static function ( $id, array $children ) {
	return array(
		'id'       => $id,
		'elType'   => 'container',
		'settings' => array( 'padding' => array( 'unit' => 'px', 'top' => '20', 'right' => '20', 'bottom' => '20', 'left' => '20', 'isLinked' => true ) ),
		'elements' => $children,
		'isInner'  => false,
	);
};

$popup1  = $create( 'elementor_library', 'Popup Eins', 'popup', array( $container( 'a1000001', array( $heading( 'a1000002', 'Popup Eins Text' ) ) ) ), array( '_elementor_conditions' => array( 'include/general' ) ) );
$popup2  = $create( 'elementor_library', 'Popup Zwei', 'popup', array( $container( 'a2000001', array( $heading( 'a2000002', 'Popup Zwei Text' ) ) ) ) );
$section = $create( 'elementor_library', 'Kontakt-Abschnitt', 'container', array( $container( 'a3000001', array( $heading( 'a3000002', 'Kontakt Vorlage' ) ) ) ) );

$link = '#' . rawurlencode( 'elementor-action:action=popup:open&settings=' . base64_encode( wp_json_encode( array( 'id' => (string) $popup1, 'toggle' => false ) ) ) );
$page = $create(
	'page',
	'Vorlage Leistung',
	'wp-page',
	array(
		$container(
			'b1000001',
			array(
				$heading( 'b1000002', 'Willkommen bei Kunde' ),
				array(
					'id'         => 'b1000003',
					'elType'     => 'widget',
					'widgetType' => 'text-editor',
					'settings'   => array( 'editor' => "<p>Ein \"Zitat\" mit Backslash \\ und Umlaut ä, Ü.</p>\n<p>Zweite Zeile &amp; </script> Ende. Alter Satz.</p>" ),
					'elements'   => array(),
					'isInner'    => false,
				),
				array(
					'id'         => 'b1000004',
					'elType'     => 'widget',
					'widgetType' => 'icon-box',
					'settings'   => array(
						'selected_icon'    => array(
							'value'   => 'fas fa-star',
							'library' => 'fa-solid',
						),
						'title_text'       => 'Beratung',
						'description_text' => 'Alter Satz. Mehr erfahren im Popup.',
						'link'             => array(
							'url'         => $link,
							'is_external' => '',
							'nofollow'    => '',
						),
					),
					'elements'   => array(),
					'isInner'    => false,
				),
				array(
					'id'         => 'b1000005',
					'elType'     => 'widget',
					'widgetType' => 'template',
					'settings'   => array( 'template_id' => (string) $section ),
					'elements'   => array(),
					'isInner'    => false,
				),
			)
		),
	),
	array(
		'_wp_page_template'       => 'elementor_header_footer',
		'_elementor_page_settings' => array( 'hide_title' => 'yes' ),
	)
);

$service = wp_insert_post(
	array(
		'post_type'   => 'service',
		'post_title'  => 'Leistung Neu',
		'post_status' => 'publish',
	)
);

foreach ( array( $page, $popup1, $popup2, $section ) as $id ) {
	\Elementor\Core\Files\CSS\Post::create( $id )->update();
}

echo "ELEMENTOR_PAGE=$page\nELEMENTOR_POPUP1=$popup1\nELEMENTOR_POPUP2=$popup2\nELEMENTOR_SECTION=$section\nSERVICE_POST=$service\n";
