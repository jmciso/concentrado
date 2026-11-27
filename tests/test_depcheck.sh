#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Tests the real dependency check in packaging/appimage/AppRun, with no test-only code paths: AppRun runs
# under `env -i` with a PATH holding only stand-in programs:
#   zenity   logs every dialog (text in zenity.log, one line per dialog in dialogs.log);
#            a --question is answered from $STUB_DIR/answer
#   pkexec   logs its arguments; exits with $STUB_DIR/pkexec_rc; on success it "installs", i.e. creates
#            $STUB_DIR/installed (unless $STUB_DIR/install_has_no_effect exists)
#   python3  the GTK probe succeeds only once $STUB_DIR/installed exists; running the app records argv
# plus the few real tools AppRun needs (sed, tr, readlink, dirname). Nothing is ever really installed.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APPRUN="$ROOT/packaging/appimage/AppRun"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
failures=0
C=""

new_case() {
    C="$T/case-$RANDOM$RANDOM"
    mkdir -p "$C/bin" "$C/sysbin" "$C/cwd"
    for tool in sed tr readlink dirname cat touch; do ln -s "$(command -v "$tool")" "$C/sysbin/$tool"; done
    cat > "$C/bin/zenity" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$STUB_DIR/zenity.log"   # full text (multi-line)
printf '%s\n' "$1" >> "$STUB_DIR/dialogs.log"  # one line per dialog shown
case "$1" in
    --question) [ "$(cat "$STUB_DIR/answer" 2>/dev/null)" = yes ] ;;
    *) exit 0 ;;
esac
EOF
    cat > "$C/bin/pkexec" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$STUB_DIR/pkexec.log"
rc="$(cat "$STUB_DIR/pkexec_rc" 2>/dev/null || echo 0)"
if [ "$rc" = 0 ] && [ ! -e "$STUB_DIR/install_has_no_effect" ]; then touch "$STUB_DIR/installed"; fi
exit "$rc"
EOF
    cat > "$C/bin/python3" <<'EOF'
#!/bin/sh
if [ "$1" = "-I" ] && [ "$2" = "-c" ]; then [ -e "$STUB_DIR/installed" ]; exit; fi
for a in "$@"; do printf '[%s]\n' "$a"; done > "$STUB_DIR/launched"
EOF
    chmod +x "$C/bin/"*
}

os_release() { printf '%s\n' "$@" > "$C/os-release"; }

# run [VAR=value ...] -- [app args ...]   (stdin is never a terminal)
run() {
    local envs=()
    while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do envs+=("$1"); shift; done
    [ "${1:-}" = "--" ] && shift
    OUT="$(cd "$C/cwd" && env -i PATH="$C/bin:$C/sysbin" HOME="$C" STUB_DIR="$C" LANG=en_US.UTF-8 \
        CONCENTRADO_OS_RELEASE="$C/os-release" CONCENTRADO_SYSTEM_PYTHON="$C/bin/python3" "${envs[@]}" \
        /bin/sh "$APPRUN" "$@" 2>&1 </dev/null)"
    RC=$?
}

# Assertions: each records a failure reason; `done_case` prints the verdict.
REASONS=()
want_rc()      { [ "$RC" = "$1" ] || REASONS+=("exit $RC, wanted $1"); }
file_has()     { grep -qF -- "$2" "$C/$1" 2>/dev/null || REASONS+=("$1 lacks: $2"); }
file_is()      { [ "$(cat "$C/$1" 2>/dev/null)" = "$2" ] || REASONS+=("$1 is '$(cat "$C/$1" 2>/dev/null)', wanted '$2'"); }
no_file()      { [ ! -e "$C/$1" ] || REASONS+=("$1 exists: $(head -c 200 "$C/$1")"); }
lines_in()     { [ "$(wc -l < "$C/$1" 2>/dev/null || echo 0)" = "$2" ] || REASONS+=("$1 has $(wc -l < "$C/$1" 2>/dev/null || echo 0) lines, wanted $2"); }
output_has()   { printf '%s' "$OUT" | grep -qF -- "$1" || REASONS+=("output lacks: $1"); }
done_case() {
    if [ "${#REASONS[@]}" = 0 ]; then echo "ok    $1"; else
        echo "FAIL  $1"; printf '      - %s\n' "${REASONS[@]}"; printf '%s\n' "$OUT" | sed 's/^/      | /' | head -8
        failures=$((failures + 1))
    fi
    REASONS=()
}

APT="apt-get install -y python3 python3-gi gir1.2-gtk-3.0"
DNF="dnf install -y python3 python3-gobject gtk3"

# --- dependencies present ---------------------------------------------------------------------------
new_case; os_release 'ID=fedora'; touch "$C/installed"
run -- --hidden "two words"
want_rc 0; no_file zenity.log; no_file pkexec.log
file_is launched "[$ROOT/packaging/appimage/usr/share/concentrado/concentrado.py]
[--hidden]
[two words]"
done_case "deps present: launches at once, arguments intact"

new_case; os_release 'ID=fedora'
cat > "$C/bin/python3" <<'EOF'
#!/bin/sh
exit 1
EOF
mkdir -p "$C/good"; cat > "$C/good/python3" <<'EOF'
#!/bin/sh
if [ "$1" = "-I" ]; then exit 0; fi
echo good > "$STUB_DIR/launched"
EOF
chmod +x "$C/bin/python3" "$C/good/python3"
run CONCENTRADO_SYSTEM_PYTHON="$C/good/python3" --
want_rc 0; no_file zenity.log; file_is launched "good"
done_case "python3 on PATH without GTK: falls back to the system python"

# --- consent and installation -----------------------------------------------------------------------
new_case; os_release 'ID=ubuntu' 'ID_LIKE=debian'; echo yes > "$C/answer"
run
want_rc 0; lines_in dialogs.log 1; file_has zenity.log "sudo apt-get update; sudo $APT"; file_has zenity.log "--no-markup"
file_is pkexec.log "sh -c apt-get update; $APT"; file_has launched "concentrado.py"
done_case "ubuntu: asks (plain text), installs via pkexec (with apt-get update), then launches"

new_case; os_release 'ID=fedora'; echo no > "$C/answer"
run
want_rc 1; lines_in dialogs.log 1; file_has zenity.log "--question"; no_file pkexec.log; no_file launched
done_case "user says no: nothing installed, nothing launched"

new_case; os_release 'ID=fedora'; echo yes > "$C/answer"; echo 126 > "$C/pkexec_rc"
run
want_rc 1; lines_in dialogs.log 1; no_file launched
done_case "password prompt dismissed (pkexec 126): no second dialog"

new_case; os_release 'ID=fedora'; echo yes > "$C/answer"; echo 127 > "$C/pkexec_rc"
run
want_rc 1; file_has zenity.log "--info"; file_has zenity.log "permission"; file_has zenity.log "sudo $DNF"; no_file launched
done_case "not authorised (pkexec 127): explains and shows the manual command"

new_case; os_release 'ID=fedora'; echo yes > "$C/answer"; rm "$C/bin/pkexec"
run
want_rc 1; lines_in dialogs.log 1; file_has zenity.log "--info"; file_has zenity.log "Run this in a terminal"; no_file launched
done_case "no pkexec at all: doesn't ask, shows the manual command"

new_case; os_release 'ID=fedora'; echo yes > "$C/answer"; echo 1 > "$C/pkexec_rc"
run
want_rc 1; file_has zenity.log "didn't complete"; no_file launched
done_case "install fails: explains, exits 1"

new_case; os_release 'ID=fedora'; echo yes > "$C/answer"; touch "$C/install_has_no_effect"
run
want_rc 1; file_has pkexec.log "$DNF"; file_has zenity.log "didn't complete"; no_file launched
done_case "install 'succeeds' but GTK still missing: explains, doesn't launch"

new_case; os_release 'ID=fedora'; rm "$C/bin/zenity"
run
want_rc 1; no_file pkexec.log; output_has "Run this in a terminal"; output_has "sudo $DNF"
done_case "no dialog tool and no terminal: prints the command, installs nothing"

new_case; os_release 'ID=fedora'; echo no > "$C/answer"; rm "$C/bin/python3"
run CONCENTRADO_SYSTEM_PYTHON="$C/nonexistent" --
want_rc 1; file_has zenity.log "sudo $DNF"
done_case "no python3 at all: offers to install it"

# --- distro mapping (answer yes, check what pkexec was asked to run) ---------------------------------
mapping() {  # NAME EXPECTED_PKEXEC_ARGS os-release-lines...
    local name="$1" want="$2"; shift 2
    new_case; os_release "$@"; echo yes > "$C/answer"
    run
    want_rc 0; file_is pkexec.log "$want"
    done_case "$name"
}
mapping "debian (ID only)"       "sh -c apt-get update; $APT" 'ID=debian'
mapping "mint (quoted ID_LIKE)"  "sh -c apt-get update; $APT" 'ID=linuxmint' 'ID_LIKE="ubuntu debian"'
mapping "fedora"                 "sh -c $DNF" 'ID=fedora'
mapping "rocky (rhel-like)"      "sh -c $DNF" 'ID="rocky"' 'ID_LIKE="rhel centos fedora"'
mapping "centos"                 "sh -c $DNF" 'ID="centos"' 'ID_LIKE="rhel fedora"'
mapping "opensuse tumbleweed"    "sh -c zypper --non-interactive install python3 python3-gobject python3-gobject-Gdk typelib-1_0-Gtk-3_0" 'ID="opensuse-tumbleweed"' 'ID_LIKE="opensuse suse"'
mapping "sles"                   "sh -c zypper --non-interactive install python3 python3-gobject python3-gobject-Gdk typelib-1_0-Gtk-3_0" 'ID="sles"'
mapping "arch"                   "sh -c pacman -S --needed --noconfirm python python-gobject gtk3" 'ID=arch'
mapping "manjaro"                "sh -c pacman -S --needed --noconfirm python python-gobject gtk3" 'ID=manjaro' 'ID_LIKE=arch'

new_case; os_release 'ID=nixos'; echo yes > "$C/answer"
run
want_rc 1; file_has zenity.log "--info"; file_has zenity.log "package manager"; no_file pkexec.log
done_case "unknown distro: explains, never asks or installs"

new_case; echo yes > "$C/answer"   # no os-release file at all
run
want_rc 1; file_has zenity.log "package manager"; no_file pkexec.log
done_case "no os-release: explains, never asks or installs"

# --- language ------------------------------------------------------------------------------------------
new_case; os_release 'ID=fedora'; echo no > "$C/answer"
run LANG=pt_PT.UTF-8 --
file_has zenity.log "O Concentrado precisa de Python 3 com GTK 3"
done_case "portuguese via LANG"

new_case; os_release 'ID=fedora'; echo no > "$C/answer"
run LANG=en_US.UTF-8 LC_ALL=pt_PT.UTF-8 --
file_has zenity.log "O Concentrado precisa"
done_case "LC_ALL wins over LANG"

# --- os-release is data --------------------------------------------------------------------------------
new_case; os_release "ID=\$(touch $C/pwned)" "ID_LIKE=\`touch $C/pwned2\`"; echo yes > "$C/answer"
run
want_rc 1; no_file pwned; no_file pwned2; no_file pkexec.log
done_case "os-release content is never executed"

new_case; os_release 'ID=*'; echo yes > "$C/answer"; touch "$C/cwd/fedora"
run
want_rc 1; no_file pkexec.log; file_has zenity.log "package manager"
done_case "os-release words are never glob-expanded"

echo
[ "$failures" = 0 ] && echo "depcheck: all passed" || echo "depcheck: $failures failed"
[ "$failures" = 0 ]
