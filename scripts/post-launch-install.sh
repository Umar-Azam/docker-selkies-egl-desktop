#!/bin/bash

set -euo pipefail

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.jetson.yml)
SERVICE="egl"

cd "$(dirname "$0")/.."

echo "Running custom post-setup installation hook in '${SERVICE}'..."
docker compose "${COMPOSE_FILES[@]}" exec -T "${SERVICE}" bash -s <<'EOF'
set -euo pipefail

# Add packages to this list to install extra software after startup.
CUSTOM_APT_PACKAGES=(
  # "package-name"
)

if [ "${#CUSTOM_APT_PACKAGES[@]}" -eq 0 ]; then
  echo "No custom packages configured."
  echo "Edit scripts/post-launch-install.sh and add package names to CUSTOM_APT_PACKAGES."
  exit 0
fi

echo "Installing custom packages: ${CUSTOM_APT_PACKAGES[*]}"
sudo apt-get update
sudo apt-get install -y --no-install-recommends "${CUSTOM_APT_PACKAGES[@]}"
sudo apt-get clean
sudo rm -rf /var/lib/apt/lists/*
echo "Custom package install complete."
EOF
