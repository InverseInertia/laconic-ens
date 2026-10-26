#!/bin/sh
# Installs LENS for the current user: copies the binary and icon under ~/.local, adds a
# launcher entry (.desktop file) to the application menu, and makes .lens files open in LENS
# with an icon of their own. Any earlier install is removed first.
#
#   sh lens-<version>-install-linux.sh             install from lens-<version>-linux-x64,
#                                                  lens-<version>-icon.png and lens-<version>-file-icon.png next to this script
#   sh lens-<version>-install-linux.sh --uninstall remove LENS and its launcher
#
# Run it from the folder holding the files downloaded from the release page. Missing files are
# fetched from the same release. No root needed; XDG_DATA_HOME is honoured.
set -eu

VERSION=""  # the release job writes the release's version here (e.g. 0.2.0)
REPO="inverseinertia/laconic-ens"
if [ -n "$VERSION" ]; then
    PREFIX="lens-$VERSION"
    BASE="https://github.com/$REPO/releases/download/v$VERSION"
else  # a copy from the source tree: no release to download from, so the files must be beside it
    PREFIX="lens"
    BASE=""
fi
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA/laconic-lens"
BIN="$APP_DIR/lens"
ICON="$DATA/icons/hicolor/512x512/apps/laconic-lens.png"
DESKTOP="$DATA/applications/laconic-lens.desktop"
LINK="$HOME/.local/bin/lens"
MIME_TYPE="application/x-laconic-lens"
MIME_XML="$DATA/mime/packages/laconic-lens.xml"
FILE_ICON="$DATA/icons/hicolor/512x512/mimetypes/application-x-laconic-lens.png"
BROWSER_PROFILE="${XDG_CACHE_HOME:-$HOME/.cache}/laconic-lens"  # the LENS window's own browser profile

refresh() {  # rebuild the caches the desktop reads the menu, file types and icons from
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA/applications" 2>/dev/null || true
    command -v update-mime-database >/dev/null 2>&1 && update-mime-database "$DATA/mime" >/dev/null 2>&1 || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$DATA/icons/hicolor" 2>/dev/null || true
}

remove_existing() {
    rm -f "$DESKTOP" "$ICON" "$MIME_XML" "$FILE_ICON"
    rm -rf "$APP_DIR"
    # the command-line link, only if it points at our binary
    if [ -L "$LINK" ] && [ "$(readlink "$LINK")" = "$BIN" ]; then rm -f "$LINK"; fi
    refresh
}

if [ "${1:-}" = "--uninstall" ]; then
    remove_existing
    rm -rf "$BROWSER_PROFILE"
    echo "LENS removed."
    exit 0
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
fetch() {  # fetch <file name>: use the copy beside the script, else download it
    if [ -f "$HERE/$1" ]; then cp "$HERE/$1" "$2"; return; fi
    if [ -z "$BASE" ]; then echo "Need $1 next to this script." >&2; exit 1; fi
    echo "Downloading $1 ..."
    if command -v curl >/dev/null 2>&1; then curl -fsSL "$BASE/$1" -o "$2"
    elif command -v wget >/dev/null 2>&1; then wget -q "$BASE/$1" -O "$2"
    else echo "Need $1 next to this script, or curl/wget to download it." >&2; exit 1; fi
}
is_png() {  # a proxy or captive portal can hand back an HTML page instead of the file
    [ "$(head -c 4 "$1" | od -An -c | tr -d ' \n')" = "211PNG" ]
}

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
fetch "$PREFIX-linux-x64" "$STAGE/lens"
fetch "$PREFIX-icon.png" "$STAGE/icon.png"
fetch "$PREFIX-file-icon.png" "$STAGE/file-icon.png"
for f in icon.png file-icon.png; do
    if ! is_png "$STAGE/$f"; then
        echo "$PREFIX-$f is not a PNG image (download failed?); not installing." >&2
        exit 1
    fi
done

remove_existing
mkdir -p "$APP_DIR" "$(dirname "$ICON")" "$(dirname "$DESKTOP")" "$(dirname "$MIME_XML")" "$(dirname "$FILE_ICON")"
install -m 755 "$STAGE/lens" "$BIN"
install -m 644 "$STAGE/icon.png" "$ICON"
install -m 644 "$STAGE/file-icon.png" "$FILE_ICON"
# The .lens file type. A file type's icon can only be named, so it is found through the icon theme.
cat > "$MIME_XML" <<MIME
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="$MIME_TYPE">
    <comment>LENS worksheet</comment>
    <sub-class-of type="text/plain"/>
    <icon name="application-x-laconic-lens"/>
    <glob pattern="*.lens"/>
  </mime-type>
</mime-info>
MIME
chmod 644 "$MIME_XML"
# The example worksheets also ship inside the program; put plain copies in the install folder.
"$BIN" --export-examples "$APP_DIR/examples" >/dev/null
# Icon is the absolute path, not the theme name: a name has to be found through the user's
# hicolor theme and its icon cache, which some desktops do not rescan, leaving a blank icon.
# StartupWMClass is how the panel and window list tell a LENS window from any other browser
# window and show this icon for it; LENS opens its window with that class (see _app_args in
# laconic/__main__.py).
cat > "$DESKTOP" <<DESK
[Desktop Entry]
Type=Application
Name=LENS
GenericName=Engineering calculation worksheet
Comment=Laconic engineering notation worksheet
Exec="$BIN" --window %f
Icon=$ICON
Terminal=false
Categories=Education;Science;Engineering;
StartupWMClass=lens
MimeType=$MIME_TYPE;
DESK
chmod 644 "$DESKTOP"
refresh
# Make LENS the program a double-clicked .lens file opens (else a text editor might be).
command -v xdg-mime >/dev/null 2>&1 && xdg-mime default laconic-lens.desktop "$MIME_TYPE" 2>/dev/null || true

echo "LENS installed to $APP_DIR; find it in your application menu. .lens files open in it."
echo "Example worksheets: $APP_DIR/examples"
echo "Remove it with: $0 --uninstall"
