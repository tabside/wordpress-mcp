#!/bin/bash
# Local or CI test WordPress with SQLite and tabside-mcp (symlinked), without MCP Adapter.
#
#   plugin/tests/setup-wordpress.sh <dir> <port> [wordpress-version]
#
# Prints APP=<application password of claude-mcp (editor)>, OTHERAPP=<of editor "other">, READERAPP=<of subscriber "leser">.
# Start the site afterwards with:  php -S 127.0.0.1:<port> -t <dir>
set -euo pipefail
D=$1; PORT=$2; VERSION=${3:-latest}
REPO=$(cd "$(dirname "$0")/../.." && pwd)
CACHE=${WP_TEST_CACHE:-$HOME/.cache/tabside-wp-test}
mkdir -p "$CACHE"
fetch() { [ -s "$CACHE/$1" ] || curl -fsSL -o "$CACHE/$1" "$2"; }
if [ "$VERSION" = latest ]; then fetch wordpress-latest.zip https://wordpress.org/latest.zip; ZIP=$CACHE/wordpress-latest.zip
else fetch "wordpress-$VERSION.zip" "https://wordpress.org/wordpress-$VERSION.zip"; ZIP=$CACHE/wordpress-$VERSION.zip; fi
fetch sqlite.zip https://downloads.wordpress.org/plugin/sqlite-database-integration.latest-stable.zip
fetch wp-cli.phar https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar
WP="php $CACHE/wp-cli.phar --allow-root --path=$D"

rm -rf "$D" "$D.tmp"; mkdir -p "$D.tmp"; unzip -q "$ZIP" -d "$D.tmp"; mv "$D.tmp/wordpress" "$D"; rm -rf "$D.tmp"
unzip -q "$CACHE/sqlite.zip" -d "$D/wp-content/plugins/"
SQ=$D/wp-content/plugins/sqlite-database-integration
sed -e "s#{SQLITE_IMPLEMENTATION_FOLDER_PATH}#$SQ#" -e "s#{SQLITE_PLUGIN}#sqlite-database-integration/load.php#" "$SQ/db.copy" > "$D/wp-content/db.php"
cat > "$D/wp-config.php" <<CFG
<?php
define('DB_NAME','wp'); define('DB_USER','x'); define('DB_PASSWORD','x'); define('DB_HOST','localhost');
define('DB_CHARSET','utf8mb4'); define('DB_COLLATE','');
\$table_prefix = 'wp_';
// "local" allows Application Passwords without HTTPS (test only).
define('WP_ENVIRONMENT_TYPE','local');
// Keine Auto-Updates während der Tests (sonst Wartungsmodus und eine andere WordPress-Version).
define('AUTOMATIC_UPDATER_DISABLED', true);
define('WP_DEBUG', true); define('WP_DEBUG_LOG', '$D/debug.log'); define('WP_DEBUG_DISPLAY', false);
foreach (array('AUTH_KEY','SECURE_AUTH_KEY','LOGGED_IN_KEY','NONCE_KEY','AUTH_SALT','SECURE_AUTH_SALT','LOGGED_IN_SALT','NONCE_SALT') as \$k) { define(\$k, 'test-' . \$k); }
if ( ! defined('ABSPATH') ) define('ABSPATH', __DIR__ . '/');
require_once ABSPATH . 'wp-settings.php';
CFG
$WP core install --url="http://127.0.0.1:$PORT" --title="Testseite" --admin_user=admin --admin_password=admin-pass-123 --admin_email=admin@example.com --skip-email >/dev/null
$WP option update timezone_string Europe/Zurich >/dev/null
ln -s "$REPO/plugin/tabside-mcp" "$D/wp-content/plugins/tabside-mcp"
$WP plugin activate tabside-mcp >/dev/null
$WP user create claude-mcp claude-mcp@example.com --role=editor --user_pass="$(openssl rand -hex 16)" >/dev/null
$WP user create other other@example.com --role=editor --user_pass="$(openssl rand -hex 16)" >/dev/null
$WP term create category "Recht" --slug=recht >/dev/null
$WP term create category "Gemeinden" --slug=gemeinden >/dev/null
echo "APP=$($WP user application-password create claude-mcp gateway --porcelain)"
$WP user create leser leser@example.com --role=subscriber --user_pass="$(openssl rand -hex 16)" >/dev/null
echo "READERAPP=$($WP user application-password create leser gateway --porcelain)"
echo "OTHERAPP=$($WP user application-password create other gateway --porcelain)"
echo "WORDPRESS=$($WP core version)"
