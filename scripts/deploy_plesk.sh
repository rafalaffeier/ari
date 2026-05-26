#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-quick}"
SERVER="${ARI_DEPLOY_SERVER:-root@server.flusscreative.com}"
KEY="${ARI_DEPLOY_KEY:-$HOME/.ssh/ari_deploy_ed25519}"
REMOTE_ROOT="${ARI_REMOTE_ROOT:-/var/www/vhosts/flusscreative.com/ari.flusscreative.com}"
BACKEND_CONTAINER="${ARI_BACKEND_CONTAINER:-ari_backend_1}"
PUBLIC_URL="${ARI_PUBLIC_URL:-https://ari.flusscreative.com}"
TMP_DIR="/tmp/ari-deploy"

SSH=(ssh -i "$KEY" -o IdentitiesOnly=yes "$SERVER")
SCP=(scp -i "$KEY" -o IdentitiesOnly=yes)

if [[ "$MODE" != "quick" && "$MODE" != "rebuild" ]]; then
  echo "Usage: scripts/deploy_plesk.sh [quick|rebuild]"
  exit 2
fi

echo "==> Preparing remote deploy directory"
"${SSH[@]}" "rm -rf '$TMP_DIR' && mkdir -p '$TMP_DIR/backend/app/web/assets' '$TMP_DIR/mobile/src/services'"

echo "==> Uploading app files"
"${SCP[@]}" backend/app/main.py "$SERVER:$TMP_DIR/backend/app/main.py"
"${SCP[@]}" backend/app/web/index.html "$SERVER:$TMP_DIR/backend/app/web/index.html"
"${SCP[@]}" backend/app/web/assets/ari-icon.svg "$SERVER:$TMP_DIR/backend/app/web/assets/ari-icon.svg"
"${SCP[@]}" mobile/App.tsx "$SERVER:$TMP_DIR/mobile/App.tsx"
"${SCP[@]}" mobile/src/services/api.ts "$SERVER:$TMP_DIR/mobile/src/services/api.ts"

echo "==> Updating server checkout"
"${SSH[@]}" "mkdir -p '$REMOTE_ROOT/backend/app/web/assets' '$REMOTE_ROOT/mobile/src/services' && \
  cp '$TMP_DIR/backend/app/main.py' '$REMOTE_ROOT/backend/app/main.py' && \
  cp '$TMP_DIR/backend/app/web/index.html' '$REMOTE_ROOT/backend/app/web/index.html' && \
  cp '$TMP_DIR/backend/app/web/assets/ari-icon.svg' '$REMOTE_ROOT/backend/app/web/assets/ari-icon.svg' && \
  cp '$TMP_DIR/mobile/App.tsx' '$REMOTE_ROOT/mobile/App.tsx' && \
  cp '$TMP_DIR/mobile/src/services/api.ts' '$REMOTE_ROOT/mobile/src/services/api.ts'"

if [[ "$MODE" == "rebuild" ]]; then
  echo "==> Rebuilding Docker services"
  "${SSH[@]}" "cd '$REMOTE_ROOT' && docker-compose -f infra/docker/docker-compose.plesk.v1.yml up -d --build"
else
  echo "==> Updating running backend container"
  "${SSH[@]}" "docker exec '$BACKEND_CONTAINER' mkdir -p /app/app/web/assets && \
    docker cp '$TMP_DIR/backend/app/main.py' '$BACKEND_CONTAINER':/app/app/main.py && \
    docker cp '$TMP_DIR/backend/app/web/index.html' '$BACKEND_CONTAINER':/app/app/web/index.html && \
    docker cp '$TMP_DIR/backend/app/web/assets/ari-icon.svg' '$BACKEND_CONTAINER':/app/app/web/assets/ari-icon.svg && \
    docker restart '$BACKEND_CONTAINER' >/dev/null"
fi

echo "==> Checking production readiness"
for attempt in {1..20}; do
  if curl -fsS "$PUBLIC_URL/ready"; then
    echo
    echo "==> Deploy complete: $PUBLIC_URL"
    exit 0
  fi
  echo
  echo "Waiting for backend... ($attempt/20)"
  sleep 2
done
echo
echo "Deploy copied files, but readiness did not pass: $PUBLIC_URL/ready"
exit 1
