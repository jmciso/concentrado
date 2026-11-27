#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# End-to-end check of the AppImage contents without packing them: builds the AppDir and runs its real
# AppRun the way the AppImage runtime would (APPIMAGE + APPDIR set). Headless and isolated: GTK's
# Broadway backend (HTTP side on a Unix socket, no network port), a private D-Bus session, throwaway
# XDG dirs, and a clean environment. On failure the temp dir and app logs are kept for inspection.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
for tool in broadwayd dbus-run-session gdbus desktop-file-validate; do
    command -v "$tool" >/dev/null || { echo "SKIP  test_appdir: $tool not installed"; exit 1; }
done

T="$(mktemp -d)"
BW=""
failures=0
cleanup() {
    [ -n "$BW" ] && kill "$BW" 2>/dev/null
    if [ "$failures" = 0 ]; then rm -rf "$T"; else echo "      (kept $T for inspection)"; fi
}
trap cleanup EXIT
ok()   { echo "ok    $1"; }
fail() { echo "FAIL  $1"; failures=$((failures + 1)); [ -n "${2:-}" ] && [ -f "$2" ] && sed 's/^/      | /' "$2" | tail -15; }

OUT="$T/dist" "$ROOT/packaging/appimage/build.sh" --appdir-only >"$T/build.log" 2>&1 || { fail "AppDir build" "$T/build.log"; exit 1; }
APPDIR="$T/dist/Tomate.AppDir"
APP_ID="$(sed -n 's/^APP_ID = "\(.*\)"$/\1/p' "$ROOT/tomate.py")"

# --- layout ---------------------------------------------------------------------------------------------
for f in AppRun "$APP_ID.desktop" "$APP_ID.svg" .DirIcon usr/share/tomate/tomate.py usr/share/tomate/desktop_integration.py \
         usr/share/tomate/content/en/exercises.json usr/share/tomate/LICENSE; do
    [ -e "$APPDIR/$f" ] && ok "AppDir has $f" || fail "AppDir is missing $f"
done
[ -x "$APPDIR/AppRun" ] && ok "AppRun is executable" || fail "AppRun not executable"
if find "$APPDIR" -name '__pycache__' -o -name '*.pyc' | grep -q .; then fail "AppDir contains caches"; else ok "no caches in AppDir"; fi

# --- headless display -------------------------------------------------------------------------------------
N=$((90 + RANDOM % 9))
broadwayd -u "$T/broadway-http.sock" ":$N" >"$T/broadwayd.log" 2>&1 &
BW=$!
for _ in $(seq 50); do [ -S "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/broadway$((N + 1)).socket" ] && break; sleep 0.1; done
kill -0 "$BW" 2>/dev/null || { fail "broadwayd didn't start" "$T/broadwayd.log"; exit 1; }

FAKE_APPIMAGE="$T/My Apps/Tomate-test.AppImage"   # a path with a space, on purpose
mkdir -p "$(dirname "$FAKE_APPIMAGE")"
printf '#!/bin/sh\nexit 0\n' > "$FAKE_APPIMAGE"; chmod +x "$FAKE_APPIMAGE"

# A script run inside one private D-Bus session. Clean environment: nothing from the developer's shell.
session() {  # session SCRIPT_BODY  -> runs it with run_app() and wait_ready() defined
    cat > "$T/session.sh" <<EOF
run_app() {
    env -i PATH="/usr/bin:/bin" HOME="$T/home" DBUS_SESSION_BUS_ADDRESS="\$DBUS_SESSION_BUS_ADDRESS" \\
        XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" LANG=en_US.UTF-8 \\
        GDK_BACKEND=broadway BROADWAY_DISPLAY=":$N" \\
        XDG_CONFIG_HOME="$T/config" XDG_DATA_HOME="$T/data" XDG_CACHE_HOME="$T/cache" XDG_STATE_HOME="$T/state" \\
        "\$@"
}
wait_ready() {  # until the app owns its bus name, max 15 s
    for _ in \$(seq 150); do
        gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \\
            --method org.freedesktop.DBus.NameHasOwner "$APP_ID" 2>/dev/null | grep -q true && return 0
        sleep 0.1
    done
    return 1
}
$1
EOF
    timeout 60 dbus-run-session -- bash "$T/session.sh"
}
APPIMAGE_ENV="APPIMAGE=\"$FAKE_APPIMAGE\" APPDIR=\"$APPDIR\""
start_and_quit='
run_app '"$APPIMAGE_ENV"' "'"$APPDIR"'/AppRun" --hidden >"'"$T"'/app.log" 2>&1 &
pid=$!
wait_ready || { echo "app never became ready"; kill $pid; exit 2; }
start=$(date +%s)
run_app '"$APPIMAGE_ENV"' "'"$APPDIR"'/AppRun" --quit >>"'"$T"'/app.log" 2>&1
wait $pid; rc=$?
[ $(( $(date +%s) - start )) -le 5 ] || { echo "quit took too long"; exit 3; }
exit $rc'

entry="$T/data/applications/$APP_ID.desktop"
autostart="$T/config/autostart/tomate.desktop"
exec_of() {  # the argv of a .desktop Exec=, as GLib parses it, one per line
    python3 -I - "$1" <<'EOF'
import sys
from gi.repository import GLib
kf = GLib.KeyFile(); kf.load_from_file(sys.argv[1], GLib.KeyFileFlags.NONE)
print("\n".join(GLib.shell_parse_argv(kf.get_string("Desktop Entry", "Exec"))[1]))
EOF
}
seed() {  # seed KIND PATH ARGS...  -> a Tomate-marked entry (KIND=menu|autostart) pointing at ARGS
    python3 -I - "$ROOT" "$@" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import desktop_integration as di
kind, path, args = sys.argv[2], sys.argv[3], sys.argv[4:]
di.write_entry(path, [("Type", "Application"), ("Name", "Tomate"), ("Exec", di.exec_line(args))])
EOF
}

# --- 1. --help prints usage and exits ------------------------------------------------------------------------
session 'run_app '"$APPIMAGE_ENV"' "'"$APPDIR"'/AppRun" --help' >"$T/help.log" 2>&1
rc=$?
[ "$rc" = 0 ] && grep -q "usage: tomate" "$T/help.log" && ok "--help prints usage and exits" \
    || fail "--help (exit $rc)" "$T/help.log"

# --- 2. moved AppImage: Tomate's own menu + autostart entries follow it ---------------------------------------
seed menu "$entry" "/old/place/Tomate.AppImage"
seed autostart "$autostart" "/old/place/Tomate.AppImage" "--hidden"
session "$start_and_quit" >"$T/s2.log" 2>&1; rc=$?
[ "$rc" = 0 ] && ok "app starts and quits cleanly" || fail "start/quit (exit $rc)" "$T/app.log"
[ "$(exec_of "$entry")" = "$FAKE_APPIMAGE" ] && ok "menu entry follows the moved AppImage" \
    || fail "menu entry not refreshed: $(exec_of "$entry")"
[ "$(exec_of "$autostart")" = "$FAKE_APPIMAGE
--hidden" ] && ok "autostart entry follows the moved AppImage" || fail "autostart not refreshed: $(exec_of "$autostart" | tr '\n' ' ')"

# --- 3. entries without Tomate's mark are never touched ------------------------------------------------------
foreign="[Desktop Entry]
Type=Application
Name=Tomate
Exec=/src/tomate.py"
printf '%s\n' "$foreign" > "$entry"; printf '%s\n' "$foreign --hidden" > "$autostart"
session "$start_and_quit" >"$T/s3.log" 2>&1; rc=$?
[ "$rc" = 0 ] && [ "$(cat "$entry")" = "$foreign" ] && [ "$(cat "$autostart")" = "$foreign --hidden" ] \
    && ok "foreign menu and autostart entries untouched" || fail "foreign entries were modified (exit $rc)" "$T/app.log"

# --- 4. APPIMAGE leaking in from a parent process doesn't switch on AppImage mode ----------------------------
seed menu "$entry" "/old/place/Tomate.AppImage"
leak='
run_app APPIMAGE="'"$FAKE_APPIMAGE"'" python3 "'"$APPDIR"'/usr/share/tomate/tomate.py" --hidden >"'"$T"'/app.log" 2>&1 &
pid=$!
wait_ready || { kill $pid; exit 2; }
run_app python3 "'"$APPDIR"'/usr/share/tomate/tomate.py" --quit; wait $pid'
session "$leak" >"$T/s4.log" 2>&1; rc=$?
[ "$rc" = 0 ] && [ "$(exec_of "$entry")" = "/old/place/Tomate.AppImage" ] \
    && ok "APPIMAGE without APPDIR is ignored" || fail "leaked APPIMAGE changed the entry (exit $rc)" "$T/app.log"

# --- 5. saving Settings without touching the autostart switch leaves a foreign autostart entry alone --------
printf '%s\n' "$foreign --hidden" > "$autostart"
rm -f "$entry"
settings='
run_app '"$APPIMAGE_ENV"' python3 -I - >"'"$T"'/app.log" 2>&1 <<PY
import sys
sys.path.insert(0, "'"$APPDIR"'/usr/share/tomate")
sys.argv = ["tomate", "--hidden"]
import tomate
from gi.repository import GLib
app = tomate.TomateApp()
def save():
    assert tomate.IN_APPIMAGE
    app.apply_settings(dict(app.cfg), None, None)   # what OK does when only other settings changed
    app.quit()
GLib.timeout_add(500, save)
sys.exit(app.run(sys.argv))
PY'
session "$settings" >"$T/s5.log" 2>&1; rc=$?
[ "$rc" = 0 ] && [ "$(cat "$autostart")" = "$foreign --hidden" ] \
    && ok "saving Settings leaves a foreign autostart entry alone" || fail "Settings save touched autostart (exit $rc)" "$T/app.log"

echo
[ "$failures" = 0 ] && echo "appdir: all passed" || echo "appdir: $failures failed"
[ "$failures" = 0 ]
