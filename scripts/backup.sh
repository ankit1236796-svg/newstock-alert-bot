#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if docker compose version >/dev/null 2>&1; then COMPOSE=(docker compose); else COMPOSE=(docker-compose); fi
mkdir -p backups
chmod 700 backups
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="backups/newstock-alert-bot-${STAMP}.tar.gz"
"${COMPOSE[@]}" run --rm --no-deps --entrypoint tar bot -czf - -C /app data > "${BACKUP}"
chmod 600 "${BACKUP}"
echo "Created ${BACKUP}"
