#!/usr/bin/env sh
# Deploys CreditGateway to one directory on a Docker host, isolated in its own compose project.
#   deploy/deploy.sh root@host [path-to-ssh-key] [remote-dir]
#   PROFILE=https (default; needs free ports 80/443 and PUBLIC_HOST in .env) or PROFILE=tunnel (outbound-only Cloudflare quick tunnel)
# Nothing outside <remote-dir> and the `creditgateway` compose project (containers, network, volumes) is touched.
set -eu
TARGET="${1:?usage: deploy.sh user@host [ssh-key] [remote-dir]}"
KEY="${2:-}"
DIR="${3:-/opt/creditgateway}"
PROFILE="${PROFILE:-https}"
SSH="ssh ${KEY:+-i $KEY}"
cd "$(dirname "$0")/.."
$SSH "$TARGET" "mkdir -p $DIR"
rsync -az --delete -e "$SSH" \
  --exclude .git --exclude .env --exclude node_modules --exclude .next --exclude .venv --exclude __pycache__ \
  --exclude apps/api/var --exclude eval/work --exclude data/tessdata --exclude '*.webm' \
  ./ "$TARGET:$DIR/"
$SSH "$TARGET" "cd $DIR && [ -f .env ] || { printf 'CG_SECRET_KEY=%s\nWEB_PORT=3101\n' \$(openssl rand -hex 24) > .env; chmod 600 .env; }
  COMPOSE_PARALLEL_LIMIT=1 docker compose --profile $PROFILE up -d --build"
echo "public URL:"
if [ "$PROFILE" = https ]; then
  $SSH "$TARGET" "cd $DIR && sed -n 's/^PUBLIC_HOST=//p' .env | sed 's|^|https://|'"
else
  $SSH "$TARGET" "cd $DIR && for i in \$(seq 1 30); do u=\$(docker compose logs tunnel 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1); [ -n \"\$u\" ] && { echo \$u; exit 0; }; sleep 2; done; echo 'tunnel URL not found yet: docker compose logs tunnel'"
fi
