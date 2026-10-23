#!/bin/sh
# Installs LENS for the current user: copies the binary and icon under ~/.local and adds a
# launcher entry (.desktop file) to the application menu. Any earlier install is removed first.
#
#   sh lens-install-linux.sh        install from lens-linux-x64 and lens-icon.png next to this script
#   sh lens-install-linux.sh --uninstall  remove LENS and its launcher
#
# Run it from the folder holding the files downloaded from the release page. Missing files are
# fetched from the latest release. No root needed; XDG_DATA_HOME is honoured.
set -eu

REPO="inverseinertia/laconic-ens"
BASE="https://github.com/$REPO/releases/latest/download"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA/laconic-lens"
BIN="$APP_DIR/lens"
ICON="$DATA/icons/hicolor/512x512/apps/laconic-lens.png"
DESKTOP="$DATA/applications/laconic-lens.desktop"
LINK="$HOME/.local/bin/lens"

remove_existing() {
    rm -f "$DESKTOP" "$ICON"
    rm -rf "$APP_DIR"
    # the command-line link, only if it points at our binary
    if [ -L "$LINK" ] && [ "$(readlink "$LINK")" = "$BIN" ]; then rm -f "$LINK"; fi
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA/applications" 2>/dev/null || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$DATA/icons/hicolor" 2>/dev/null || true
}

if [ "${1:-}" = "--uninstall" ]; then
    remove_existing
    echo "LENS removed."
    exit 0
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
fetch() {  # fetch <file name>: use the copy beside the script, else download it
    if [ -f "$HERE/$1" ]; then cp "$HERE/$1" "$2"; return; fi
    echo "Downloading $1 ..."
    if command -v curl >/dev/null 2>&1; then curl -fsSL "$BASE/$1" -o "$2"
    elif command -v wget >/dev/null 2>&1; then wget -q "$BASE/$1" -O "$2"
    else echo "Need $1 next to this script, or curl/wget to download it." >&2; exit 1; fi
}

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
fetch lens-linux-x64 "$STAGE/lens"
fetch lens-icon.png "$STAGE/icon.png"

remove_existing
mkdir -p "$APP_DIR" "$(dirname "$ICON")" "$(dirname "$DESKTOP")"
install -m 755 "$STAGE/lens" "$BIN"
install -m 644 "$STAGE/icon.png" "$ICON"
cat > "$DESKTOP" <<DESK
[Desktop Entry]
Type=Application
Name=LENS
GenericName=Engineering calculation worksheet
Comment=Laconic engineering notation worksheet
Exec="$BIN"
Icon=laconic-lens
Terminal=false
Categories=Education;Science;Engineering;
StartupWMClass=lens
DESK
chmod 644 "$DESKTOP"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA/applications" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$DATA/icons/hicolor" 2>/dev/null || true

echo "LENS installed to $APP_DIR; find it in your application menu."
echo "Remove it with: $0 --uninstall"
