#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAVALINK_DIR="$ROOT_DIR/lavalink"
JAR="$LAVALINK_DIR/Lavalink.jar"

if ! command -v java >/dev/null 2>&1; then
  echo "Java 17+ is required. Rebuild the Codespace after updating the devcontainer."
  exit 1
fi

if [[ ! -f "$JAR" ]]; then
  echo "Missing $JAR"
  echo "Download the official Lavalink.jar release and place it at that exact path."
  exit 1
fi

cd "$LAVALINK_DIR"
exec java -Xms256M -Xmx1G -jar "$JAR"
