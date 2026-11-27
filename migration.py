# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 João Mendes
"""Carry settings and progress over from the app's former name, Tomate.

Non-destructive by design: the old folders are *copied*, never moved or deleted, so a downgrade or a
mistake loses nothing. The only files removed are Tomate's own launcher entries (its autostart file and
its AppImage menu entry), and only when they're recognisably Tomate's, because they point at an app that
no longer exists under that name. Another app also called Tomate (tomate-gtk) uses similar paths, so
every check looks for something only this app's former version wrote.
"""

import os
import shlex
import shutil
from pathlib import Path

OLD_NAME = "tomate"
OLD_APPIMAGE_MARK = "X-Tomate-AppImage=true"
OLD_APP_ID = "app.tomate.Pomodoro"
# A file only Tomate wrote in each folder: anything else there is not ours to migrate.
OLD_SIGNATURE = {"config": "config.json", "data": "state.json"}


def _lines(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None


def copy_old_dirs(config_home, data_home, new_name):
    """Copy ~/.config/tomate and ~/.local/share/tomate to the new names, if the new ones don't exist yet
    and the old ones look like Tomate's. The copy goes to a temporary sibling first and is renamed into
    place only once complete, so a failure halfway leaves nothing behind and is retried next start.
    Returns (copied, errors)."""
    copied, errors = [], []
    for kind, home in (("config", Path(config_home)), ("data", Path(data_home))):
        old, new = home / OLD_NAME, home / new_name
        if new.exists() or not (old / OLD_SIGNATURE[kind]).is_file():
            continue
        tmp = home / f".{new_name}.migrating"
        try:
            if tmp.exists():
                shutil.rmtree(tmp)
            shutil.copytree(old, tmp)  # follows symlinks: the new app gets its own copies
            os.replace(tmp, new)
            copied.append(new)
        except (OSError, shutil.Error) as exc:
            shutil.rmtree(tmp, ignore_errors=True)
            errors.append(f"{old}: {exc}")
    return copied, errors


def _runs_tomate_py(lines):
    for line in lines:
        if line.startswith("Exec="):
            try:
                argv = shlex.split(line[len("Exec="):])
            except ValueError:
                return False
            return any(Path(a).name == "tomate.py" for a in argv)
    return False


def old_autostart(config_home):
    """Tomate's autostart file, if Tomate wrote it: either the AppImage form (carries Tomate's mark) or
    the source form (Name=Tomate, running exactly tomate.py)."""
    path = Path(config_home) / "autostart" / f"{OLD_NAME}.desktop"
    lines = _lines(path)
    if lines is None:
        return None
    if OLD_APPIMAGE_MARK in lines or ("Name=Tomate" in lines and _runs_tomate_py(lines)):
        return path
    return None


def old_appimage_menu_entry(data_home):
    """Tomate's own AppImage menu entry (it carries Tomate's mark), if any."""
    path = Path(data_home) / "applications" / f"{OLD_APP_ID}.desktop"
    lines = _lines(path)
    return path if lines is not None and OLD_APPIMAGE_MARK in lines else None
