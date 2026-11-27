# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for migration: carrying settings over from the app's former name, Tomate."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import migration  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.config = Path(self._tmp.name) / "config"
        self.data = Path(self._tmp.name) / "data"
        (self.config / "tomate" / "lessons").mkdir(parents=True)
        (self.config / "tomate" / "config.json").write_text('{"focus_min": 2}')
        (self.config / "tomate" / "lessons" / "mine.json").write_text("{}")
        (self.data / "tomate").mkdir(parents=True)
        (self.data / "tomate" / "state.json").write_text('{"stats": {"2026-11-26": 2}}')

    def tearDown(self):
        self._tmp.cleanup()


class CopyDirs(Base):
    def test_copies_everything_and_keeps_the_old(self):
        copied, errors = migration.copy_old_dirs(self.config, self.data, "concentrado")
        self.assertEqual(errors, [])
        self.assertEqual(sorted(copied), sorted([self.config / "concentrado", self.data / "concentrado"]))
        self.assertEqual((self.config / "concentrado" / "config.json").read_text(), '{"focus_min": 2}')
        self.assertTrue((self.config / "concentrado" / "lessons" / "mine.json").exists())
        self.assertEqual((self.data / "concentrado" / "state.json").read_text(), '{"stats": {"2026-11-26": 2}}')
        # nothing old is removed
        self.assertTrue((self.config / "tomate" / "config.json").exists())
        self.assertTrue((self.data / "tomate" / "state.json").exists())

    def test_never_overwrites_existing_new_dirs(self):
        (self.config / "concentrado").mkdir()
        (self.config / "concentrado" / "config.json").write_text('{"focus_min": 50}')
        copied, _ = migration.copy_old_dirs(self.config, self.data, "concentrado")
        self.assertEqual(copied, [self.data / "concentrado"])
        self.assertEqual((self.config / "concentrado" / "config.json").read_text(), '{"focus_min": 50}')

    def test_second_run_does_nothing(self):
        migration.copy_old_dirs(self.config, self.data, "concentrado")
        self.assertEqual(migration.copy_old_dirs(self.config, self.data, "concentrado"), ([], []))

    def test_nothing_to_migrate(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(migration.copy_old_dirs(Path(d) / "c", Path(d) / "d", "concentrado"), ([], []))

    def test_folders_of_another_app_named_tomate_are_not_copied(self):
        with tempfile.TemporaryDirectory() as d:
            config, data = Path(d) / "c", Path(d) / "d"
            (config / "tomate" / "plugins").mkdir(parents=True)  # e.g. tomate-gtk: no config.json/state.json
            (config / "tomate" / "tomate.conf").write_text("[Timer]\n")
            (data / "tomate").mkdir(parents=True)
            self.assertEqual(migration.copy_old_dirs(config, data, "concentrado"), ([], []))
            self.assertFalse((config / "concentrado").exists())

    def test_failed_copy_leaves_nothing_and_is_retried(self):
        real = migration.shutil.copytree
        def broken(src, dst, **kw):
            Path(dst).mkdir()
            (Path(dst) / "half.json").write_text("{}")
            raise OSError("disk full")
        migration.shutil.copytree = broken
        try:
            copied, errors = migration.copy_old_dirs(self.config, self.data, "concentrado")
        finally:
            migration.shutil.copytree = real
        self.assertEqual(copied, [])
        self.assertEqual(len(errors), 2, "both folders attempted despite the first failing")
        self.assertFalse((self.config / "concentrado").exists())
        self.assertFalse(any(p.name.startswith(".concentrado") for p in self.config.iterdir()), "temp left behind")
        copied, errors = migration.copy_old_dirs(self.config, self.data, "concentrado")  # next start retries
        self.assertEqual((len(copied), errors), (2, []))

    def test_symlinked_files_are_copied_not_linked(self):
        target = Path(self._tmp.name) / "dotfiles-state.json"
        target.write_text('{"stats": {}}')
        (self.data / "tomate" / "state.json").unlink()
        (self.data / "tomate" / "state.json").symlink_to(target)
        migration.copy_old_dirs(self.config, self.data, "concentrado")
        new = self.data / "concentrado" / "state.json"
        self.assertFalse(new.is_symlink())
        self.assertEqual(new.read_text(), '{"stats": {}}')


class OldLaunchers(Base):
    def autostart(self, text):
        path = self.config / "autostart" / "tomate.desktop"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_recognises_tomate_autostart(self):
        for text in ["[Desktop Entry]\nType=Application\nName=Tomate\nExec=/usr/bin/python3 /src/tomate/tomate.py --hidden\n",
                     '[Desktop Entry]\nName=Tomate\nExec="/src/my dir/tomate.py" --hidden\n',
                     f'[Desktop Entry]\nName=Tomate\nExec="/x/My Apps/Tomate-1.AppImage" --hidden\n{migration.OLD_APPIMAGE_MARK}\n']:
            with self.subTest(text=text):
                path = self.autostart(text)
                self.assertEqual(migration.old_autostart(self.config), path)

    def test_ignores_other_autostart_files_with_that_name(self):
        for text in ["[Desktop Entry]\nName=Tomate Garden\nExec=/usr/bin/tomate-gtk\n",   # another app
                     "[Desktop Entry]\nName=Tomate\nExec=/usr/bin/tomate-gtk\n",           # tomate-gtk itself
                     "[Desktop Entry]\nComment=Name=Tomate\nExec=/x/tomate.py\n",          # Name= only in a value
                     "[Desktop Entry]\nName=Tomate\nExec=/opt/foo-tomate.py --x\n",        # not exactly tomate.py
                     "[Desktop Entry]\nName=Tomate\nExec=/opt/Other.AppImage\n",           # AppImage without the mark
                     b"\xff\xfe not a desktop file"]:
            with self.subTest(text=text):
                path = self.config / "autostart" / "tomate.desktop"
                path.parent.mkdir(parents=True, exist_ok=True)
                (path.write_bytes if isinstance(text, bytes) else path.write_text)(text)
                self.assertIsNone(migration.old_autostart(self.config))
        (self.config / "autostart" / "tomate.desktop").unlink()
        self.assertIsNone(migration.old_autostart(self.config))

    def test_old_appimage_menu_entry_needs_the_old_mark(self):
        entry = self.data / "applications" / "app.tomate.Pomodoro.desktop"
        entry.parent.mkdir(parents=True)
        entry.write_text("[Desktop Entry]\nName=Tomate\nExec=/src/tomate.py\n")  # e.g. from install.sh
        self.assertIsNone(migration.old_appimage_menu_entry(self.data))
        entry.write_text(f"[Desktop Entry]\nName=Tomate\nExec=/a/T.AppImage\n{migration.OLD_APPIMAGE_MARK}\n")
        self.assertEqual(migration.old_appimage_menu_entry(self.data), entry)


if __name__ == "__main__":
    unittest.main()
