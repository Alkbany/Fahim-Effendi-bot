#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAVALINK_DIR="$ROOT_DIR/lavalink"
PLUGINS_DIR="$LAVALINK_DIR/plugins"
JAR="$LAVALINK_DIR/Lavalink.jar"

if ! command -v java >/dev/null 2>&1; then
  echo "Java 17+ is required. Rebuild the Codespace after updating the devcontainer."
  exit 1
fi

mkdir -p "$PLUGINS_DIR"

download_release_asset() {
  local repository="$1"
  local release_endpoint="$2"
  local asset_name="$3"
  local destination="$4"

  if [[ -s "$destination" ]]; then
    echo "Already present: $destination"
    return
  fi

  python - "$repository" "$release_endpoint" "$asset_name" "$destination" <<'PY'
import hashlib
import json
import pathlib
import sys
import urllib.request

repository, endpoint, asset_name, destination = sys.argv[1:]
api_url = f"https://api.github.com/repos/{repository}/releases/{endpoint}"
headers = {"Accept": "application/vnd.github+json", "User-Agent": "Fahim-Effendi-Music-Setup"}
request = urllib.request.Request(api_url, headers=headers)
with urllib.request.urlopen(request, timeout=30) as response:
    release = json.load(response)

asset = next((item for item in release.get("assets", []) if item["name"] == asset_name), None)
if asset is None:
    raise SystemExit(f"Release asset not found: {repository}/{asset_name}")

target = pathlib.Path(destination)
temporary = target.with_suffix(target.suffix + ".part")
download_request = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": "Fahim-Effendi-Music-Setup"})
digest = hashlib.sha256()
with urllib.request.urlopen(download_request, timeout=120) as response, temporary.open("wb") as output:
    while chunk := response.read(1024 * 1024):
        output.write(chunk)
        digest.update(chunk)

expected = asset.get("digest")
if expected and expected.startswith("sha256:") and digest.hexdigest() != expected.split(":", 1)[1]:
    temporary.unlink(missing_ok=True)
    raise SystemExit(f"SHA-256 verification failed for {asset_name}")

temporary.replace(target)
print(f"Downloaded and verified: {target}")
PY
}

download_release_asset "lavalink-devs/Lavalink" "latest" "Lavalink.jar" "$JAR"
download_release_asset "lavalink-devs/youtube-source" "tags/1.18.2" "youtube-plugin-1.18.2.jar" "$PLUGINS_DIR/youtube-plugin-1.18.2.jar"

cd "$LAVALINK_DIR"
exec java -Xms256M -Xmx1G -jar "$JAR"
