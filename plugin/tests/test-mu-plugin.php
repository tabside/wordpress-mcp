<?php
/**
 * Plugin Name: Test: Beitragstyp service, Menü-Position, Seitenleiste
 * Description: Für den Integrationstest: eigener Beitragstyp service (URL-Präfix /service/, Elementor-Unterstützung), eine Menü-Position und eine klassische Seitenleiste.
 *
 * @package tabside-mcp
 */

add_action(
	'init',
	static function () {
		register_post_type(
			'service',
			array(
				'label'        => 'Leistungen',
				'public'       => true,
				'show_ui'      => true,
				'show_in_rest' => true,
				'hierarchical' => false,
				'rewrite'      => array( 'slug' => 'service' ),
				'supports'     => array( 'title', 'editor', 'thumbnail', 'elementor' ),
			)
		);
		register_nav_menus( array( 'primary' => 'Hauptmenü' ) );
	}
);

add_action(
	'widgets_init',
	static function () {
		register_sidebar(
			array(
				'id'   => 'test-sidebar',
				'name' => 'Test-Seitenleiste',
			)
		);
	}
);
