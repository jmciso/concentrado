#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 João Mendes
#
# Builds the light Tomate AppImage (system Python + GTK; see AppRun).
#
#   packaging/appimage/build.sh               # AppDir + AppImage in dist/
#   packaging/appimage/build.sh --appdir-only # just the AppDir (runnable as dist/Tomate.AppDir/AppRun)
#
# Packing needs appimagetool (https://github.com/AppImage/appimagetool/releases, "continuous").
# Point APPIMAGETOOL at it, or place it at ~/.cache/tomate-build/tools/appimagetool-x86_64.AppImage.
# If packaging/appimage/appimagetool.sha256 exists, the tool is checked against it before running.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/packaging/appimage"
OUT="$(realpath -m "${OUT:-$ROOT/dist}")"
APPDIR="$OUT/Tomate.AppDir"
APP_ID="$(sed -n 's/^APP_ID = "\(.*\)"$/\1/p' "$ROOT/tomate.py")"
[ -n "$APP_ID" ] || { echo "Couldn't read APP_ID from tomate.py" >&2; exit 1; }

if [ -e "$APPDIR" ] && [ ! -e "$APPDIR/AppRun" ]; then
    echo "$APPDIR exists but doesn't look like a Tomate AppDir; refusing to delete it" >&2; exit 1
fi
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/share/tomate"

# Files known to git (tracked, or new and not ignored): no caches, no local leftovers.
FILES=(tomate.py tray.py i18n.py desktop_integration.py content icons LICENSE LICENSES README.md)
untracked="$(cd "$ROOT" && git ls-files --others --exclude-standard -- "${FILES[@]}")"
if [ -n "$untracked" ]; then
    echo "warning: including files not committed to git (fine for testing, not for a release):" >&2
    printf '%s\n' "$untracked" | sed 's/^/  /' >&2
fi
(cd "$ROOT" && git ls-files -z --cached --others --exclude-standard -- "${FILES[@]}") \
    | (cd "$ROOT" && xargs -0 cp --parents -t "$APPDIR/usr/share/tomate")

install -m 755 "$HERE/AppRun" "$APPDIR/AppRun"
cp "$ROOT/icons/app.svg" "$APPDIR/$APP_ID.svg"
ln -s "$APP_ID.svg" "$APPDIR/.DirIcon"
cat > "$APPDIR/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Tomate
Comment=Pomodoro timer with active breaks
Comment[pt]=Temporizador Pomodoro com pausas ativas
Exec=AppRun
Icon=$APP_ID
StartupWMClass=$APP_ID
Categories=Utility;
Keywords=pomodoro;timer;focus;foco;
StartupNotify=false
EOF
if command -v desktop-file-validate >/dev/null; then
    desktop-file-validate "$APPDIR/$APP_ID.desktop"
else
    echo "warning: desktop-file-validate not installed; the .desktop file wasn't checked" >&2
fi
echo "AppDir ready: $APPDIR"

[ "${1:-}" = "--appdir-only" ] && exit 0

TOOL="${APPIMAGETOOL:-$HOME/.cache/tomate-build/tools/appimagetool-x86_64.AppImage}"
if [ ! -x "$TOOL" ]; then
    echo "appimagetool not found at $TOOL" >&2
    echo "Download it from https://github.com/AppImage/appimagetool/releases (continuous), make it executable," >&2
    echo "and either put it there or set APPIMAGETOOL. Then run this script again." >&2
    exit 2
fi
if [ -f "$HERE/appimagetool.sha256" ]; then
    echo "$(cat "$HERE/appimagetool.sha256")  $TOOL" | sha256sum -c --quiet - \
        || { echo "appimagetool checksum mismatch: refusing to run it" >&2; exit 3; }
else
    echo "warning: no packaging/appimage/appimagetool.sha256, so appimagetool runs unverified." >&2
    echo "         Its checksum: $(sha256sum "$TOOL" | cut -d' ' -f1) (commit it once you trust this download)" >&2
fi

VERSION="$(cd "$ROOT" && git describe --tags --always --dirty)"
TARGET="$OUT/Tomate-$VERSION-x86_64.AppImage"
# Update info lets appimageupdatetool fetch new releases from GitHub (once the repo is public).
ARCH=x86_64 VERSION="$VERSION" APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" \
    -u "gh-releases-zsync|jmciso|tomate|latest|Tomate-*x86_64.AppImage.zsync" \
    "$APPDIR" "$TARGET"
echo "Built: $TARGET"
