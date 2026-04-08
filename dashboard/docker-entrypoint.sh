#!/bin/sh
# Inject runtime API_BASE_URL into a small JS file loaded before the app.
cat > /usr/share/nginx/html/env.js <<EOF
window.__ENV__ = { API_BASE_URL: "${API_BASE_URL:-}" };
EOF
exec nginx -g 'daemon off;'
