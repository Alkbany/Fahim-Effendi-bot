#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAVALINK_DIR="$ROOT_DIR/lavalink"
JAR="$LAVALINK_DIR/Lavalink.jar"

if ! command -v java >/dev/null 2>&1; then
  echo "Java 17+ is required. Install a supported Java runtime first." >&2
  exit 1
fi

JAVA_VERSION="$(java -version 2>&1 | head -n 1 | sed -E 's/.*version "([0-9]+).*/\1/')"
if [[ -z "$JAVA_VERSION" || "$JAVA_VERSION" -lt 17 ]]; then
  echo "Java 17 or newer is required; detected: ${JAVA_VERSION:-unknown}" >&2
  exit 1
fi

if [[ -z "${LAVALINK_PASSWORD:-}" ]]; then
  echo "Set LAVALINK_PASSWORD before starting local Lavalink." >&2
  exit 1
fi

mkdir -p "$LAVALINK_DIR"

if [[ ! -s "$JAR" ]]; then
  python - "$JAR" <<'PY'
import hashlib
import json
import os
import pathlib
import sys
import urllib.request

destination = pathlib.Path(sys.argv[1])
version = os.environ.get("LAVALINK_VERSION", "4.2.2").lstrip("v")
api_url = f"https://api.github.com/repos/lavalink-devs/Lavalink/releases/tags/{version}"
request = urllib.request.Request(
    api_url,
    headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "Fahim-Effendi-Music-Setup",
    },
)
with urllib.request.urlopen(request, timeout=30) as response:
    release = json.load(response)

asset = next(
    (item for item in release.get("assets", []) if item.get("name") == "Lavalink.jar"),
    None,
)
if asset is None:
    raise SystemExit("The selected Lavalink release does not contain Lavalink.jar. Check LAVALINK_VERSION.")

temporary = destination.with_suffix(".jar.part")
digest = hashlib.sha256()
download = urllib.request.Request(
    asset["browser_download_url"],
    headers={"User-Agent": "Fahim-Effendi-Music-Setup"},
)
with urllib.request.urlopen(download, timeout=120) as response, temporary.open("wb") as output:
    while chunk := response.read(1024 * 1024):
        output.write(chunk)
        digest.update(chunk)

expected = asset.get("digest")
if expected and expected.startswith("sha256:"):
    if digest.hexdigest() != expected.split(":", 1)[1]:
        temporary.unlink(missing_ok=True)
        raise SystemExit("Lavalink JAR SHA-256 verification failed.")

temporary.replace(destination)
print(f"Downloaded Lavalink {release.get('tag_name', 'unknown')} to {destination}")
PY
fi

cd "$LAVALINK_DIR"
export SERVER_ADDRESS="${SERVER_ADDRESS:-127.0.0.1}"
export SERVER_PORT="${SERVER_PORT:-2333}"
export LAVALINK_SERVER_PASSWORD="$LAVALINK_PASSWORD"

read -r -a JAVA_ARGS <<< "${JAVA_OPTS:--Xms256M -Xmx1G}"
exec java "${JAVA_ARGS[@]}" -jar "$JAR"
