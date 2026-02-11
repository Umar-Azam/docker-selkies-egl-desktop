#!/bin/bash

set -euo pipefail

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.jetson.yml)
SERVICE="egl"
STARTUP_WAIT_SECONDS="${STARTUP_WAIT_SECONDS:-360}"
LOG_CHECK_INTERVAL_SECONDS="${LOG_CHECK_INTERVAL_SECONDS:-2}"
PROBE_TIMEOUT_SECONDS="${PROBE_TIMEOUT_SECONDS:-3}"

compose() {
  docker compose "${COMPOSE_FILES[@]}" "$@"
}

compose_timeout() {
  local duration="$1"
  shift
  timeout "${duration}" docker compose "${COMPOSE_FILES[@]}" "$@"
}

cleanup() {
  compose down >/dev/null 2>&1 || true
}
trap cleanup EXIT

export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-0}"
export COMPOSE_DOCKER_CLI_BUILD="${COMPOSE_DOCKER_CLI_BUILD:-0}"

compose up -d --build

echo "Waiting for desktop startup..."
READY=0
ATTEMPTS=$((STARTUP_WAIT_SECONDS / LOG_CHECK_INTERVAL_SECONDS))
for _ in $(seq 1 "${ATTEMPTS}"); do
  if compose_timeout "${PROBE_TIMEOUT_SECONDS}s" exec -T "${SERVICE}" bash -lc 'grep -q "X Server is ready" /tmp/entrypoint.log /tmp/selkies-gstreamer-entrypoint.log'; then
    READY=1
    break
  fi
  sleep "${LOG_CHECK_INTERVAL_SECONDS}"
done

if [ "${READY}" -ne 1 ]; then
  echo "Container did not reach desktop startup state (X11 probe)"
  compose_timeout 20s ps || true
  compose_timeout 20s exec -T "${SERVICE}" bash -lc 'tail -n 160 /tmp/entrypoint.log /tmp/selkies-gstreamer-entrypoint.log' || true
  compose_timeout 20s logs --no-color "${SERVICE}" | tail -n 200 || true
  exit 1
fi

compose_timeout 10m exec -T "${SERVICE}" bash -lc "/usr/local/bin/validate-acceleration"

echo "Jetson smoke test passed"
