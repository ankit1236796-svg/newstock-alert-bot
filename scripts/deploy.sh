#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ ! -f .env ]]; then
  echo "Missing .env. Copy .env.example to .env and set BOT_TOKEN." >&2
  exit 1
fi
chmod 600 .env
mkdir -p backups
chmod 700 backups
if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
else
  COMPOSE=(docker-compose)
fi
"${COMPOSE[@]}" pull --ignore-pull-failures
"${COMPOSE[@]}" up -d --build
"${COMPOSE[@]}" ps
