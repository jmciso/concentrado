# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for desktop_integration: the AppImage's menu/autostart entries.

Exec= lines are checked the way GNOME uses them: GIO loads the entry (it hides entries whose program
it can't find) and launches it, and a recording script reports the argv it received.
"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import desktop_integration as di  # noqa: E402

import gi  # noqa: E402

try:
    gi.require_version("GioUnix", "2.0")
    from gi.repository import GioUnix as _gio_unix  # noqa: E402
    DesktopAppInfo = _gio_unix.DesktopAppInfo
except (ValueError, ImportError):  # older GLib
    from gi.repository import Gio  # noqa: E402
    DesktopAppInfo = Gio.DesktopAppInfo

APP_ID = "test.tomate.App"
ICON_SRC = Path(__file__).resolve().parent.parent / "icons" / "app.svg"
OTHER_APP = "[Desktop Entry]\nType=Application\nName=Other\nExec=/usr/bin/true\n"


def make_recorder(path, record):
    """An executable at `path` that writes its full argv ($0 included) to `record`, one [arg] per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\nfor a in \"$0\" \"$@\"; do printf '[%s]\\n' \"$a\"; done > '{record}'\n"
                    f"echo done >> '{record}'\n")
    path.chmod(0o755)


def gnome_launch(desktop_file, record, timeout=5.0):
    """Load and launch like GNOME does. Returns the recorded argv list, or None if GIO refused it."""
    info = DesktopAppInfo.new_from_filename(str(desktop_file))
    if info is None:
        return None
    if record.exists():
        record.unlink()
    assert info.launch([], None)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if record.exists() and record.read_text().endswith("done\n"):
            return [line[1:-1] for line in record.read_text().splitlines()[:-1]]
        time.sleep(0.05)
    raise AssertionError("launched program never ran")


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "data"
        self.apps = self.home / "applications"
        self.apps.mkdir(parents=True)
        # a neighbour that must survive everything Tomate does
        self.other = self.apps / "other.app.desktop"
        self.other.write_text(OTHER_APP)

    def tearDown(self):
        self.assertEqual(self.other.read_text(), OTHER_APP, "another app's menu entry was modified")
        self._tmp.cleanup()

    def integrate(self, appimage):
        return di.integrate(APP_ID, appimage, ICON_SRC, self.home, "Tomate", "Pomodoro")


class GnomeLaunchesEntries(Base):
    PATHS = ["dir with spaces", 'double"quote', "dollar$HOME", "back\\slash", "it's", "back`tick`",
             "semi;colon", "tilde~", "hash#", "star*", "joão Transferências"]

    def test_menu_entry_launches_the_appimage(self):
        for name in self.PATHS:
            with self.subTest(dir=name):
                appimage = self.tmp / name / "Tomate.AppImage"
                record = self.tmp / "record.txt"
                make_recorder(appimage, record)
                self.assertTrue(self.integrate(str(appimage)))
                self.assertEqual(gnome_launch(di.desktop_path(APP_ID, self.home), record), [str(appimage)])

    def test_autostart_style_entry_passes_arguments(self):
        appimage = self.tmp / "my apps" / "Tomate.AppImage"
        record = self.tmp / "record.txt"
        make_recorder(appimage, record)
        entry = self.tmp / "autostart" / "tomate.desktop"
        di.write_entry(entry, [("Type", "Application"), ("Name", "Tomate"),
                               ("Exec", di.exec_line([str(appimage), "--hidden", "two words", "50%", "a%%b"]))])
        self.assertEqual(gnome_launch(entry, record), [str(appimage), "--hidden", "two words", "50%", "a%%b"])

    def test_unlaunchable_paths_get_no_entry(self):
        for path in [str(self.tmp / "100%" / "Tomate.AppImage"), str(self.tmp / "line\nbreak" / "T.AppImage"),
                     "relative/Tomate.AppImage", ""]:
            with self.subTest(path=path):
                self.assertFalse(di.launchable_path(path))
                self.assertFalse(self.integrate(path))
                self.assertFalse(di.entry_exists(APP_ID, self.home))


class MenuEntry(Base):
    def test_integrate_writes_marked_entry_and_icon(self):
        self.assertTrue(self.integrate("/apps/Tomate.AppImage"))
        self.assertTrue(di.is_ours(APP_ID, self.home))
        self.assertEqual(di.icon_path(self.home).read_bytes(), ICON_SRC.read_bytes())
        self.assertIn(f"Icon={di.icon_path(self.home)}", di.desktop_path(APP_ID, self.home).read_text())

    def test_moved_appimage_is_detected_and_refreshed(self):
        self.integrate("/apps/Tomate.AppImage")
        self.assertFalse(di.needs_refresh(APP_ID, "/apps/Tomate.AppImage", self.home))
        self.assertTrue(di.needs_refresh(APP_ID, "/new place/Tomate-2.AppImage", self.home))
        self.integrate("/new place/Tomate-2.AppImage")
        self.assertFalse(di.needs_refresh(APP_ID, "/new place/Tomate-2.AppImage", self.home))
        self.assertIn('Exec="/new place/Tomate-2.AppImage"', di.desktop_path(APP_ID, self.home).read_text())

    def test_foreign_entry_is_never_touched(self):
        entry = di.desktop_path(APP_ID, self.home)
        original = "[Desktop Entry]\nType=Application\nName=Tomate\nExec=/src/tomate.py\n"
        entry.write_text(original)
        self.assertTrue(di.entry_exists(APP_ID, self.home))
        self.assertFalse(di.is_ours(APP_ID, self.home))
        self.assertFalse(self.integrate("/apps/Tomate.AppImage"))
        self.assertFalse(di.needs_refresh(APP_ID, "/apps/Tomate.AppImage", self.home))
        self.assertFalse(di.remove(APP_ID, self.home))
        self.assertEqual(entry.read_text(), original)
        self.assertFalse(di.icon_path(self.home).exists())

    def test_mark_in_a_value_does_not_count_as_ours(self):
        di.desktop_path(APP_ID, self.home).write_text(f"[Desktop Entry]\nName=Tomate\nComment=see {di.MARK}\nExec=/x\n")
        self.assertFalse(di.is_ours(APP_ID, self.home))

    def test_non_utf8_entry_is_handled(self):
        di.desktop_path(APP_ID, self.home).write_bytes(b"[Desktop Entry]\nName=Caf\xe9\nExec=/x\n")
        self.assertFalse(di.is_ours(APP_ID, self.home))
        self.assertFalse(di.needs_refresh(APP_ID, "/apps/Tomate.AppImage", self.home))
        self.assertFalse(self.integrate("/apps/Tomate.AppImage"))

    def test_remove_deletes_only_our_entry(self):
        self.integrate("/apps/Tomate.AppImage")
        state = self.home / "tomate" / "state.json"
        state.write_text("{}")
        self.assertTrue(di.remove(APP_ID, self.home))
        self.assertFalse(di.entry_exists(APP_ID, self.home))
        self.assertTrue(state.exists(), "user data next to the icon must survive")
        self.assertFalse(di.remove(APP_ID, self.home))

    def test_icon_kept_while_an_entry_uses_it(self):
        self.integrate("/apps/Tomate.AppImage")
        autostart = self.tmp / "autostart" / "tomate.desktop"
        di.write_entry(autostart, [("Exec", "/apps/Tomate.AppImage --hidden")])
        di.remove(APP_ID, self.home)
        di.remove_icon_if_unused(self.home, autostart)
        self.assertTrue(di.icon_path(self.home).exists())
        autostart.unlink()
        di.remove_icon_if_unused(self.home, autostart)
        self.assertFalse(di.icon_path(self.home).exists())


class Helpers(unittest.TestCase):
    def test_exec_differs_only_for_marked_entries(self):
        with tempfile.TemporaryDirectory() as d:
            marked = Path(d) / "a.desktop"
            di.write_entry(marked, [("Exec", di.exec_line(["/a/T.AppImage", "--hidden"]))])
            self.assertFalse(di.exec_differs(marked, ["/a/T.AppImage", "--hidden"]))
            self.assertTrue(di.exec_differs(marked, ["/b/T.AppImage", "--hidden"]))
            plain = Path(d) / "b.desktop"
            plain.write_text("[Desktop Entry]\nExec=/old/T.AppImage --hidden\n")
            self.assertFalse(di.exec_differs(plain, ["/b/T.AppImage", "--hidden"]))
            self.assertFalse(di.exec_differs(Path(d) / "missing.desktop", ["/b"]))

    def test_launcher_args(self):
        self.assertEqual(di.launcher_args("/a/T.AppImage", "/usr/bin/python3", "/s/tomate.py"), ["/a/T.AppImage"])
        self.assertEqual(di.launcher_args(None, "/usr/bin/python3", "/s/tomate.py"), ["/usr/bin/python3", "/s/tomate.py"])


if __name__ == "__main__":
    unittest.main()
