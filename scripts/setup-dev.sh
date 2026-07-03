#!/usr/bin/env bash
# Development setup: link this repo's integration into a Home Assistant
# config directory (e.g. the HA dev container's /config).
#
# Usage: ./scripts/setup-dev.sh [HA_CONFIG_DIR]
#   HA_CONFIG_DIR defaults to $HA_CONFIG or /config (dev container).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HA_CONFIG_DIR="${1:-${HA_CONFIG:-/config}}"

if [ ! -d "$HA_CONFIG_DIR" ]; then
    echo "Home Assistant config directory not found: $HA_CONFIG_DIR" >&2
    echo "Pass it as the first argument or set \$HA_CONFIG." >&2
    exit 1
fi

mkdir -p "$HA_CONFIG_DIR/custom_components"

TARGET="$HA_CONFIG_DIR/custom_components/herold"
if [ -e "$TARGET" ] && [ ! -L "$TARGET" ]; then
    echo "Refusing to overwrite existing non-symlink: $TARGET" >&2
    exit 1
fi

ln -sfn "$REPO_ROOT/custom_components/herold" "$TARGET"
echo "Linked $REPO_ROOT/custom_components/herold -> $TARGET"
echo "Restart Home Assistant to pick up the integration."
