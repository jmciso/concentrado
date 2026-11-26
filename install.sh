#!/usr/bin/env bash
# Installs Tomate for the current user (no sudo needed).
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$DIR/tomate.py"
mkdir -p ~/.local/bin ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps
ln -sf "$DIR/tomate.py" ~/.local/bin/tomate
ICON_NAME=app.tomate.Pomodoro
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
cat > ~/.local/share/applications/app.tomate.Pomodoro.desktop <<DESK
[Desktop Entry]
Type=Application
Name=Tomate
Comment=Pomodoro timer with active breaks
Comment[pt]=Temporizador Pomodoro com pausas ativas
Exec=$DIR/tomate.py
Icon=$DIR/icons/app.svg
StartupWMClass=app.tomate.Pomodoro
Categories=Utility;
Keywords=pomodoro;timer;focus;foco;
StartupNotify=false
DESK
gtk-update-icon-cache -q ~/.local/share/icons/hicolor 2>/dev/null || true
update-desktop-database ~/.local/share/applications 2>/dev/null || true
echo "Tomate installed. Launch it from the app grid or run: tomate"
