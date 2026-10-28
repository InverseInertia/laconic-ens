#!/bin/sh
# Installs LENS for the current user: unpacks the program and copies the icons under ~/.local, adds a
# launcher entry (.desktop file) to the application menu, and makes .lens files open in LENS
# with an icon of their own. Any earlier install is removed first, and a LENS still running from
# it is stopped, so running it again updates.
#
#   sh lens-install-linux-v2.sh                    install the latest release of LENS
#   sh lens-install-linux-v2.sh --release 0.3.5    install that release instead
#   sh lens-install-linux-v2.sh --uninstall        remove LENS and its launcher
#   sh lens-install-linux-v2.sh --version          print this installer's version
#
# The latest release is looked up on GitHub when the script runs. Files of that release already
# beside the script (lens-<version>-linux-x64.tar.gz, lens-<version>-icon.png,
# lens-<version>-file-icon.png) are used as they are; missing ones are downloaded. Offline, it
# installs the newest release whose files are beside it. A build of your own
# (lens-linux-x64.tar.gz, lens-icon.png and lens-file-icon.png beside it) is installed without
# asking GitHub. The archive holds the folder PyInstaller builds: lens/lens and lens/_internal.
# No root needed; XDG_DATA_HOME is honoured.
set -eu

# The installer's own version, numbered apart from LENS's: bump it when this script changes
# (see wiki/Releases-and-Packaging.md).
INSTALLER_VERSION="2.1.0"
REPO="inverseinertia/laconic-ens"
LATEST_API="${LENS_RELEASE_API:-https://api.github.com/repos/$REPO/releases/latest}"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA/laconic-lens"
BIN="$APP_DIR/lens"   # the program, beside its _internal folder
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

stop_running() {
    # A LENS left running from the install folder would take every new launch over (instance.py),
    # so the menu entry would keep showing the old release. Its program may already be deleted
    # (/proc then shows "<path> (deleted)"), so match the folder, not the file.
    stopped=""
    for exe in /proc/[0-9]*/exe; do
        target="$(readlink "$exe" 2>/dev/null)" || continue
        case "$target" in "$APP_DIR"/*) ;; *) continue ;; esac
        pid="${exe#/proc/}"; pid="${pid%/exe}"
        if kill "$pid" 2>/dev/null; then stopped="$stopped $pid"; fi
    done
    [ -n "$stopped" ] || return 0
    echo "Stopped the LENS that was running."
    for _ in 1 2 3 4 5; do  # give it up to 5 s to let go of its port
        alive=""
        for pid in $stopped; do if [ -d "/proc/$pid" ]; then alive=1; fi; done
        [ -n "$alive" ] || return 0
        sleep 1
    done
    for pid in $stopped; do kill -9 "$pid" 2>/dev/null || true; done
}

remove_existing() {
    stop_running
    rm -f "$DESKTOP" "$ICON" "$MIME_XML" "$FILE_ICON"
    rm -rf "$APP_DIR"
    # the command-line link, only if it points at our binary
    if [ -L "$LINK" ] && [ "$(readlink "$LINK")" = "$BIN" ]; then rm -f "$LINK"; fi
    refresh
}

RELEASE=""
case "${1:-}" in
    --uninstall)
        remove_existing
        rm -rf "$BROWSER_PROFILE"
        echo "LENS removed."
        exit 0 ;;
    --version) echo "LENS installer $INSTALLER_VERSION"; exit 0 ;;
    --release)
        RELEASE="${2:-}"; RELEASE="${RELEASE#v}"
        if [ -z "$RELEASE" ]; then echo "--release needs a version, e.g. --release 0.3.5" >&2; exit 2; fi ;;
    "") ;;
    *) echo "Unknown option $1 (try --release VERSION, --uninstall or --version)." >&2; exit 2 ;;
esac

HERE="$(cd "$(dirname "$0")" && pwd)"
get() {  # get <url> <file>: download, failing within a reasonable time when offline
    if command -v curl >/dev/null 2>&1; then curl -fsSL --connect-timeout 15 --retry 2 "$1" -o "$2"
    elif command -v wget >/dev/null 2>&1; then wget -q -T 15 -t 3 "$1" -O "$2"
    else return 127; fi
}
latest_release() {  # the latest release's version (0.3.5) from the GitHub API, or nothing
    reply="$(mktemp)"
    if get "$LATEST_API" "$reply" 2>/dev/null; then
        # "tag_name": "v0.3.5" appears once in the reply, at the top level
        tr ',{}' '\n\n\n' < "$reply" | sed -n 's/^[[:space:]]*"tag_name"[[:space:]]*:[[:space:]]*"v\{0,1\}\([0-9][0-9A-Za-z.+-]*\)"[[:space:]]*$/\1/p' | head -n 1
    fi
    rm -f "$reply"
}
newest_beside() {  # the newest version with a lens-<version>-linux-x64.tar.gz beside the script, or nothing
    for f in "$HERE"/lens-*-linux-x64.tar.gz; do
        [ -f "$f" ] || continue
        v="${f##*/lens-}"; echo "${v%-linux-x64.tar.gz}"
    done | sort -t. -k1,1n -k2,2n -k3,3n | tail -n 1
}

if [ -z "$RELEASE" ] && [ -f "$HERE/lens-linux-x64.tar.gz" ]; then
    PREFIX="lens"  # a build of your own, unversioned: nothing to look up or download
    BASE=""
    echo "Installing the LENS build beside this script (installer $INSTALLER_VERSION) ..."
else
    if [ -z "$RELEASE" ]; then
        echo "Looking up the latest LENS release ..."
        RELEASE="$(latest_release)"
        if [ -z "$RELEASE" ]; then
            RELEASE="$(newest_beside)"
            if [ -z "$RELEASE" ]; then
                echo "Could not look up the latest release (offline, or GitHub did not answer)." >&2
                echo "Try again later, or put lens-<version>-linux-x64.tar.gz, lens-<version>-icon.png and" >&2
                echo "lens-<version>-file-icon.png from https://github.com/$REPO/releases beside this script." >&2
                exit 1
            fi
            echo "Could not look up the latest release; installing $RELEASE from the files beside this script."
        fi
    fi
    PREFIX="lens-$RELEASE"
    BASE="https://github.com/$REPO/releases/download/v$RELEASE"
    WAS=""
    [ -f "$APP_DIR/version" ] && WAS="$(cat "$APP_DIR/version")"
    if [ -z "$WAS" ]; then echo "Installing LENS $RELEASE (installer $INSTALLER_VERSION) ..."
    elif [ "$WAS" = "$RELEASE" ]; then echo "Reinstalling LENS $RELEASE (installer $INSTALLER_VERSION) ..."
    else echo "Updating LENS $WAS -> $RELEASE (installer $INSTALLER_VERSION) ..."; fi
fi

fetch() {  # fetch <file name> <to>: use the copy beside the script, else download it
    if [ -f "$HERE/$1" ]; then cp "$HERE/$1" "$2"; return; fi
    if [ -z "$BASE" ]; then echo "Need $1 next to this script." >&2; exit 1; fi
    echo "Downloading $1 ..."
    get "$BASE/$1" "$2" && return
    if [ $? -eq 127 ]; then echo "Need $1 next to this script, or curl/wget to download it." >&2
    else echo "Could not download $BASE/$1 (offline, or no such release?); nothing was changed." >&2; fi
    exit 1
}
is_png() {  # a proxy or captive portal can hand back an HTML page instead of the file
    [ "$(head -c 4 "$1" | od -An -c | tr -d ' \n')" = "211PNG" ]
}

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
fetch "$PREFIX-linux-x64.tar.gz" "$STAGE/lens.tar.gz"
fetch "$PREFIX-icon.png" "$STAGE/icon.png"
fetch "$PREFIX-file-icon.png" "$STAGE/file-icon.png"
for f in icon.png file-icon.png; do
    if ! is_png "$STAGE/$f"; then
        echo "$PREFIX-$f is not a PNG image (download failed?); not installing." >&2
        exit 1
    fi
done
mkdir "$STAGE/app"
if ! tar -xzf "$STAGE/lens.tar.gz" -C "$STAGE/app" 2>/dev/null || [ ! -x "$STAGE/app/lens/lens" ]; then
    echo "$PREFIX-linux-x64.tar.gz is not a LENS program archive (download failed?); not installing." >&2
    exit 1
fi

remove_existing
mkdir -p "$APP_DIR" "$(dirname "$ICON")" "$(dirname "$DESKTOP")" "$(dirname "$MIME_XML")" "$(dirname "$FILE_ICON")"
cp -R "$STAGE/app/lens/." "$APP_DIR/"
if [ -n "$BASE" ]; then echo "$RELEASE" > "$APP_DIR/version"; fi  # what the next run updates from
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

echo "LENS ${RELEASE:-(own build)} installed to $APP_DIR; find it in your application menu. .lens files open in it."
echo "Example worksheets: $APP_DIR/examples"
echo "Run this script again to update to the latest release; remove LENS with: $0 --uninstall"
