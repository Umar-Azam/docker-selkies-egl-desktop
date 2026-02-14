#!/bin/bash

set -euo pipefail

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.jetson.yml)
SERVICE="egl"
PORT="8080"
IMAGE_TAG="${JETSON_IMAGE_TAG:-selkies-egl-desktop:jetson}"
POST_SETUP_SCRIPT="${POST_SETUP_SCRIPT:-./scripts/post-launch-install.sh}"
DESKTOP_READY_TIMEOUT_SECONDS="${DESKTOP_READY_TIMEOUT_SECONDS:-240}"

cd "$(dirname "$0")/.."

UP_ARGS=(-d)
if [ "$(echo "${FORCE_REBUILD:-false}" | tr '[:upper:]' '[:lower:]')" = "true" ]; then
  echo "FORCE_REBUILD=true, rebuilding image '${IMAGE_TAG}'."
  UP_ARGS=(--build -d)
elif docker image inspect "${IMAGE_TAG}" >/dev/null 2>&1; then
  echo "Found existing image '${IMAGE_TAG}', skipping rebuild."
else
  echo "Image '${IMAGE_TAG}' was not found, building it now."
  UP_ARGS=(--build -d)
fi

echo "Starting Jetson desktop container..."
docker compose "${COMPOSE_FILES[@]}" up "${UP_ARGS[@]}"

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

echo "Waiting for desktop startup readiness..."
READY=0
ATTEMPTS=$((DESKTOP_READY_TIMEOUT_SECONDS / 2))
for _ in $(seq 1 "${ATTEMPTS}"); do
  if docker compose "${COMPOSE_FILES[@]}" exec -T "${SERVICE}" bash -lc 'grep -q "X Server is ready" /tmp/entrypoint.log /tmp/selkies-gstreamer-entrypoint.log' >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done

if [ "${READY}" -ne 1 ]; then
  echo "Desktop did not report ready state within ${DESKTOP_READY_TIMEOUT_SECONDS}s."
  echo "Recent logs:"
  docker compose "${COMPOSE_FILES[@]}" logs --no-color "${SERVICE}" | tail -n 160 || true
  exit 1
fi

if [ -x "${POST_SETUP_SCRIPT}" ]; then
  echo "Running post-setup hook: ${POST_SETUP_SCRIPT}"
  "${POST_SETUP_SCRIPT}"
else
  echo "Post-setup hook not found or not executable: ${POST_SETUP_SCRIPT}"
  echo "Create/edit scripts/post-launch-install.sh for custom installs."
fi

echo
echo "Desktop is up."
echo "Open: http://localhost:${PORT}"
echo "Default password from compose file: mypasswd"
echo
echo "Useful commands:"
echo "  Stop:  docker compose ${COMPOSE_FILES[*]} down"
echo "  Logs:  docker compose ${COMPOSE_FILES[*]} logs -f ${SERVICE}"
