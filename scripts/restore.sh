#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 backups/newstock-alert-bot-YYYYMMDDTHHMMSSZ.tar.gz" >&2
  exit 1
fi
if docker compose version >/dev/null 2>&1; then COMPOSE=(docker compose); else COMPOSE=(docker-compose); fi
BACKUP="$1"
[[ -f "${BACKUP}" ]] || { echo "Backup not found: ${BACKUP}" >&2; exit 1; }
"${COMPOSE[@]}" stop bot || true
"${COMPOSE[@]}" run --rm --no-deps --entrypoint sh -T bot -c 'rm -rf /app/data/* && tar -xzf - -C /app' < "${BACKUP}"
"${COMPOSE[@]}" up -d bot
"${COMPOSE[@]}" ps
