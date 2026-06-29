#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if docker compose version >/dev/null 2>&1; then COMPOSE=(docker compose); else COMPOSE=(docker-compose); fi
git pull --ff-only
"${COMPOSE[@]}" up -d --build
"${COMPOSE[@]}" ps
