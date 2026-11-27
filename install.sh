#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 João Mendes
# Installs Concentrado for the current user (no sudo needed).
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$DIR/concentrado.py"

# Clean up an install of the app's former name (Tomate), but only files that install.sh itself created:
# the launcher symlink to tomate.py and the menu entry named Tomate that runs tomate.py.
if [ -L ~/.local/bin/tomate ] && [[ "$(readlink ~/.local/bin/tomate)" == */tomate.py ]]; then
    rm ~/.local/bin/tomate
fi
old_entry=~/.local/share/applications/app.tomate.Pomodoro.desktop
if [ -f "$old_entry" ] && grep -qx 'Name=Tomate' "$old_entry" && grep -q '^Exec=.*/tomate\.py$' "$old_entry"; then
    rm "$old_entry"
    find ~/.local/share/icons/hicolor -name 'app.tomate.Pomodoro.*' -delete 2>/dev/null || true
fi
mkdir -p ~/.local/bin ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps
ln -sf "$DIR/concentrado.py" ~/.local/bin/concentrado
ICON_NAME=io.github.jmciso.Concentrado
cp "$DIR/icons/app.svg" ~/.local/share/icons/hicolor/scalable/apps/$ICON_NAME.svg
# PNG renders too: some shells/docks only pick up raster sizes
python3 - "$DIR/icons/app.svg" "$ICON_NAME" <<'PY'
import sys, os
import gi; gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf
svg, name = sys.argv[1:]
for size in (16, 24, 32, 48, 64, 128, 256, 512):
    d = os.path.expanduser(f"~/.local/share/icons/hicolor/{size}x{size}/apps")
    os.makedirs(d, exist_ok=True)
    GdkPixbuf.Pixbuf.new_from_file_at_size(svg, size, size).savev(f"{d}/{name}.png", "png", [], [])
PY
# bump directory mtimes so GNOME Shell notices replaced icons
touch ~/.local/share/icons/hicolor ~/.local/share/icons/hicolor/*/apps
cat > ~/.local/share/applications/io.github.jmciso.Concentrado.desktop <<DESK
[Desktop Entry]
Type=Application
Name=Concentrado
Comment=Pomodoro timer with active breaks
Comment[pt]=Temporizador Pomodoro com pausas ativas
Exec=$DIR/concentrado.py
Icon=$DIR/icons/app.svg
StartupWMClass=io.github.jmciso.Concentrado
Categories=Utility;
Keywords=pomodoro;timer;focus;foco;
StartupNotify=false
DESK
gtk-update-icon-cache -q ~/.local/share/icons/hicolor 2>/dev/null || true
update-desktop-database ~/.local/share/applications 2>/dev/null || true
echo "Concentrado installed. Launch it from the app grid or run: concentrado"
