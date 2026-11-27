#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Smoke test of a *packed* AppImage through the real AppImage runtime (FUSE mount, APPIMAGE/APPDIR set by
# the runtime itself). Headless and isolated like test_appdir.sh.
#
#   bash tests/test_appimage.sh [path/to/Concentrado-*.AppImage]   # default: newest in dist/
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:-$(ls -t "$ROOT"/dist/Concentrado-*-x86_64.AppImage 2>/dev/null | head -1)}"
[ -n "$SRC" ] && [ -f "$SRC" ] || { echo "SKIP  test_appimage: no AppImage built (run packaging/appimage/build.sh)"; exit 0; }
for tool in broadwayd dbus-run-session gdbus; do
    command -v "$tool" >/dev/null || { echo "SKIP  test_appimage: $tool not installed"; exit 1; }
done
APP_ID="$(sed -n 's/^APP_ID = "\(.*\)"$/\1/p' "$ROOT/concentrado.py")"

T="$(mktemp -d)"; BW=""; failures=0
cleanup() {
    [ -n "$BW" ] && kill "$BW" 2>/dev/null
    if [ "$failures" = 0 ]; then rm -rf "$T"; else echo "      (kept $T for inspection)"; fi
}
trap cleanup EXIT
ok()   { echo "ok    $1"; }
fail() { echo "FAIL  $1"; failures=$((failures + 1)); [ -n "${2:-}" ] && [ -f "$2" ] && sed 's/^/      | /' "$2" | tail -15; }

APPIMAGE="$T/My Apps/Concentrado.AppImage"
mkdir -p "$(dirname "$APPIMAGE")" && cp "$SRC" "$APPIMAGE" && chmod +x "$APPIMAGE"
echo "testing $(basename "$SRC")"

N=$((90 + RANDOM % 9))
broadwayd -u "$T/broadway-http.sock" ":$N" >"$T/broadwayd.log" 2>&1 &
BW=$!
for _ in $(seq 50); do [ -S "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/broadway$((N + 1)).socket" ] && break; sleep 0.1; done

cat > "$T/session.sh" <<EOF
run_app() {
    env -i PATH="/usr/bin:/bin" HOME="$T/home" DBUS_SESSION_BUS_ADDRESS="\$DBUS_SESSION_BUS_ADDRESS" \\
        XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" LANG=en_US.UTF-8 \\
        GDK_BACKEND=broadway BROADWAY_DISPLAY=":$N" \\
        XDG_CONFIG_HOME="$T/config" XDG_DATA_HOME="$T/data" XDG_CACHE_HOME="$T/cache" XDG_STATE_HOME="$T/state" \\
        "$APPIMAGE" "\$@"
}
wait_ready() {
    for _ in \$(seq 150); do
        gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \\
            --method org.freedesktop.DBus.NameHasOwner "$APP_ID" 2>/dev/null | grep -q true && return 0
        sleep 0.1
    done
    return 1
}
case "\$1" in
    help) run_app --help ;;
    cycle)
        run_app --hidden >"$T/app.log" 2>&1 &
        pid=\$!
        wait_ready || { echo "never ready"; kill \$pid; exit 2; }
        run_app --quit >>"$T/app.log" 2>&1
        wait \$pid ;;
esac
EOF

timeout 60 dbus-run-session -- bash "$T/session.sh" help >"$T/help.log" 2>&1; rc=$?
[ "$rc" = 0 ] && grep -q "usage: concentrado" "$T/help.log" && ok "packed AppImage runs (--help)" || fail "--help (exit $rc)" "$T/help.log"

# A stale Concentrado-made menu entry must be pointed at this AppImage's real path by the runtime-provided APPIMAGE.
entry="$T/data/applications/$APP_ID.desktop"
python3 -I - "$ROOT" "$entry" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import desktop_integration as di
di.write_entry(sys.argv[2], [("Type", "Application"), ("Name", "Concentrado"), ("Exec", di.exec_line(["/old/Concentrado.AppImage"]))])
EOF
timeout 60 dbus-run-session -- bash "$T/session.sh" cycle >"$T/cycle.log" 2>&1; rc=$?
[ "$rc" = 0 ] && ok "starts and quits cleanly" || fail "start/quit (exit $rc)" "$T/app.log"
got="$(python3 -I - "$entry" <<'EOF'
import sys
from gi.repository import GLib
kf = GLib.KeyFile(); kf.load_from_file(sys.argv[1], GLib.KeyFileFlags.NONE)
print("\n".join(GLib.shell_parse_argv(kf.get_string("Desktop Entry", "Exec"))[1]))
EOF
)"
[ "$got" = "$APPIMAGE" ] && ok "menu entry points at the real AppImage path" || fail "menu entry Exec is '$got'"
[ -f "$T/data/concentrado/appimage-icon.svg" ] && ok "icon copied out of the mount" || fail "icon not copied"

sleep 0.5
if grep -q "$T/My Apps" /proc/mounts 2>/dev/null || mount | grep -qF ".mount_Concen"; then
    mount | grep -F ".mount_Concen" | sed 's/^/      | /'
    fail "AppImage mount left behind"
else
    ok "no AppImage mount left behind"
fi

echo
[ "$failures" = 0 ] && echo "appimage: all passed" || echo "appimage: $failures failed"
[ "$failures" = 0 ]
