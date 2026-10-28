#!/bin/sh
# Not the LENS program: each release attaches this, stamped with its version, as
# lens-<version>-linux-x64, the single-file program installer 1.x (lens-install-linux.sh, from
# v0.3.6 and earlier) still downloads. That installer puts it where the program goes and runs it
# with --export-examples. It then installs this release with installer 2, which replaces it with
# the real program, and runs that with the same arguments, so copies of installer 1.x keep
# updating LENS (#101). Installer 1.x hides stdout, so everything here goes to stderr.
set -eu
VERSION="@VERSION@"
URL="https://github.com/inverseinertia/laconic-ens/releases/download/v$VERSION/lens-install-linux-v2.sh"
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

echo "LENS $VERSION needs installer 2; running it (keep lens-install-linux-v2.sh for future updates) ..." >&2
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp "$SELF" "$STAGE/bridge"
if command -v curl >/dev/null 2>&1; then curl -fsSL --connect-timeout 15 --retry 2 "$URL" -o "$STAGE/install.sh"
elif command -v wget >/dev/null 2>&1; then wget -q -T 15 -t 3 "$URL" -O "$STAGE/install.sh"
else echo "Need curl or wget to download $URL" >&2; exit 1; fi
sh "$STAGE/install.sh" --release "$VERSION" >&2

# Installer 2 put the program where this file was; run it, unless this file is somehow still here.
if [ ! -x "$SELF" ] || cmp -s "$SELF" "$STAGE/bridge"; then
    echo "Installer 2 did not replace $SELF; install LENS with lens-install-linux-v2.sh." >&2
    exit 1
fi
rm -rf "$STAGE"
exec "$SELF" "$@"
