#!/usr/bin/env bash
# Download a matching PYNQ bit/HWH pair from an immutable Git commit.
set -euo pipefail

REF="${1:?Usage: bash download_overlay.sh FULL_COMMIT_SHA [output_directory]}"
TARGET_DIR="${2:-$(pwd)/overlays}"
PROJECT="TransportPhaseLockFF"
REPO_OWNER="drkbldwn208"
REPO="TransportPhaseLockFF"

# Full SHA avoids a moving branch between the two requests.
[[ "$REF" =~ ^[[:xdigit:]]{40}$ ]] || { echo 'Use a full 40-character commit SHA.' >&2; exit 1; }
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    read -r -s -p 'GitHub token (hidden): ' GITHUB_TOKEN
    printf '\n'
fi
[[ -n "$GITHUB_TOKEN" ]] || { echo 'A token is required for this private repository.' >&2; exit 1; }

mkdir -p "$TARGET_DIR"
DOWNLOAD_TMP="$(mktemp -d "$TARGET_DIR/.download.XXXXXX")"
trap 'rm -rf "$DOWNLOAD_TMP"' EXIT
# Keep the credential out of the process command line and the saved script.
printf 'header = "Authorization: Bearer %s"\n' "$GITHUB_TOKEN" > "$DOWNLOAD_TMP/auth"
chmod 600 "$DOWNLOAD_TMP/auth"
unset GITHUB_TOKEN
BASE_URL="https://raw.githubusercontent.com/$REPO_OWNER/$REPO/$REF/pynq_overlays/latest"
for extension in bit hwh; do
    echo "Downloading $PROJECT.$extension at $REF"
    curl --fail --show-error --location --config "$DOWNLOAD_TMP/auth" \
        --output "$DOWNLOAD_TMP/$PROJECT.$extension" "$BASE_URL/$PROJECT.$extension"
    test -s "$DOWNLOAD_TMP/$PROJECT.$extension"
done
# A failed request must not truncate either of the existing working files.
mv "$DOWNLOAD_TMP/$PROJECT.bit" "$TARGET_DIR/$PROJECT.bit"
mv "$DOWNLOAD_TMP/$PROJECT.hwh" "$TARGET_DIR/$PROJECT.hwh"
printf '%s\n' "$REF" > "$TARGET_DIR/overlay_commit.txt"
echo 'Download complete. Load the overlay only after this script has finished.'
ls -lh "$TARGET_DIR/$PROJECT.bit" "$TARGET_DIR/$PROJECT.hwh"
