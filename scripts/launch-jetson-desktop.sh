#!/bin/bash

set -euo pipefail

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.jetson.yml)
SERVICE="egl"
PORT="8080"

cd "$(dirname "$0")/.."

echo "Starting Jetson desktop container..."
docker compose "${COMPOSE_FILES[@]}" up -d --build

echo "Waiting for service '${SERVICE}' to report running..."
for _ in $(seq 1 60); do
  STATUS="$(docker compose "${COMPOSE_FILES[@]}" ps --status running --services 2>/dev/null || true)"
  if echo "${STATUS}" | grep -qx "${SERVICE}"; then
    break
  fi
  sleep 2
done

if ! docker compose "${COMPOSE_FILES[@]}" ps --status running --services | grep -qx "${SERVICE}"; then
  echo "Service '${SERVICE}' did not reach running state."
  echo "Recent logs:"
  docker compose "${COMPOSE_FILES[@]}" logs --no-color "${SERVICE}" | tail -n 120 || true
  exit 1
fi

echo
echo "Desktop is up."
echo "Open: http://localhost:${PORT}"
echo "Default password from compose file: mypasswd"
echo
echo "Useful commands:"
echo "  Stop:  docker compose ${COMPOSE_FILES[*]} down"
echo "  Logs:  docker compose ${COMPOSE_FILES[*]} logs -f ${SERVICE}"
