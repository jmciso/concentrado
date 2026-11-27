# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 João Mendes
"""App-menu and autostart entries for the AppImage, and the command line that relaunches Concentrado.

AppImages don't add themselves to the app menu, so Concentrado offers to do it. Every entry Concentrado writes
for the AppImage carries the MARK line; Concentrado only ever rewrites or deletes entries carrying it, so an
entry made by install.sh, a distro package or the user is never touched. A marked entry *is* rewritten
when the AppImage moves (e.g. after an update), so hand edits to a marked entry don't survive that.
"""

import shutil
from pathlib import Path

MARK = "X-Concentrado-AppImage=true"


def desktop_path(app_id, data_home):
    return Path(data_home) / "applications" / f"{app_id}.desktop"


def icon_path(data_home):
    return Path(data_home) / "concentrado" / "appimage-icon.svg"


_RESERVED = set(' \t"\'\\><~|&;$*?#()`')


def launchable_path(path):
    """GNOME can't launch an Exec= whose program path contains % (GIO checks the program exists before
    undoing %%) or control characters (they break the .desktop line). Such paths get no entry."""
    p = str(path)
    return bool(p) and Path(p).is_absolute() and "%" not in p and not any(ord(c) < 32 for c in p)


def quote_exec_arg(arg):
    """Quote one argument for a .desktop Exec= line, per the freedesktop Desktop Entry spec:
    reserved characters need double quotes; inside them \\ " ` $ get a backslash; then the general
    string escaping doubles every backslash; and a literal % is written %% (field-code escaping)."""
    arg = str(arg)
    if arg and not any(c in _RESERVED for c in arg):
        return arg.replace("%", "%%")
    quoted = "".join("\\" + c if c in '\\"`$' else c for c in arg)
    quoted = quoted.replace("\\", "\\\\")
    return '"' + quoted.replace("%", "%%") + '"'


def exec_line(args):
    return " ".join(quote_exec_arg(a) for a in args)


def launcher_args(appimage, python, script):
    """Command that starts Concentrado again later (menu entry, autostart). Inside an AppImage, the
    script lives in a temporary mount that disappears on exit, so it must be the AppImage file."""
    return [appimage] if appimage else [python, str(script)]


def _read_lines(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None


def is_marked(path):
    lines = _read_lines(path)
    return lines is not None and MARK in lines


def exec_differs(path, args):
    """True when a marked entry's Exec= isn't exactly `args` (e.g. the AppImage moved)."""
    lines = _read_lines(path)
    if lines is None or MARK not in lines:
        return False
    return f"Exec={exec_line(args)}" not in lines


def write_entry(path, fields):
    """Write a marked .desktop entry atomically. `fields` is a list of (key, value)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    body = "[Desktop Entry]\n" + "".join(f"{k}={v}\n" for k, v in fields) + MARK + "\n"
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)


def ensure_icon(icon_src, data_home):
    """Copy the icon out of the AppImage mount (which disappears on exit) to a stable place."""
    icon = icon_path(data_home)
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(icon_src, icon)
    return icon


# ---------------------------------------------------------------- app-menu entry

def entry_exists(app_id, data_home):
    return desktop_path(app_id, data_home).exists()


def is_ours(app_id, data_home):
    return is_marked(desktop_path(app_id, data_home))


def integrate(app_id, appimage, icon_src, data_home, name, comment):
    """Create (or refresh) Concentrado's own menu entry. Returns False, writing nothing, if an entry that
    isn't ours exists or if GNOME couldn't launch this path."""
    path = desktop_path(app_id, data_home)
    if (path.exists() and not is_ours(app_id, data_home)) or not launchable_path(appimage):
        return False
    icon = ensure_icon(icon_src, data_home)
    write_entry(path, [
        ("Type", "Application"), ("Name", name), ("Comment", comment),
        ("Exec", exec_line([appimage])), ("Icon", str(icon)), ("StartupWMClass", app_id),
        ("Categories", "Utility;"), ("Keywords", "pomodoro;timer;focus;"), ("StartupNotify", "false"),
    ])
    return True


def needs_refresh(app_id, appimage, data_home):
    """True when our menu entry points at a different AppImage path (the file was moved or renamed)."""
    return exec_differs(desktop_path(app_id, data_home), [appimage])


def remove(app_id, data_home):
    """Delete Concentrado's own menu entry. Entries that aren't ours are left alone. The icon copy stays
    if a marked autostart entry still uses it."""
    path = desktop_path(app_id, data_home)
    if not is_marked(path):
        return False
    path.unlink()
    return True


def remove_icon_if_unused(data_home, *entries):
    """Delete the icon copy unless one of the given entry files (marked or not) still exists."""
    if not any(Path(e).exists() for e in entries):
        icon = icon_path(data_home)
        if icon.exists():
            icon.unlink()
