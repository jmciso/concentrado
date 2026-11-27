#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 João Mendes
"""Tomate: a Pomodoro timer with active breaks (stretching challenges and mini language lessons)."""

import importlib
import json
import math
import os
import random
import sys
import time
from datetime import date
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i18n  # noqa: E402
from i18n import t  # noqa: E402
import tray  # noqa: E402
import desktop_integration as di  # noqa: E402


def _optional(namespace, version):
    try:
        gi.require_version(namespace, version)
        return importlib.import_module("gi.repository." + namespace)
    except (ValueError, ImportError):
        return None


Notify = _optional("Notify", "0.7")
Gst = _optional("Gst", "1.0")
if Gst:
    Gst.init(None)

APP_ID = "app.tomate.Pomodoro"
BASE = Path(__file__).resolve().parent
CONTENT_DIR = BASE / "content"
ICON_DIR = BASE / "icons"
APP_ICON = str(ICON_DIR / "app.svg")
CONFIG_DIR = Path(GLib.get_user_config_dir()) / "tomate"
DATA_DIR = Path(GLib.get_user_data_dir()) / "tomate"
CONFIG_FILE = CONFIG_DIR / "config.json"
STATE_FILE = DATA_DIR / "state.json"
AUTOSTART_FILE = Path(GLib.get_user_config_dir()) / "autostart" / "tomate.desktop"
SOUND_DIR = Path("/usr/share/sounds/freedesktop/stereo")
QUIZ_HISTORY_MAX = 2000  # quiz results kept for progress stats
DATA_HOME = Path(GLib.get_user_data_dir())

# Running from an AppImage? The runtime sets APPIMAGE (the file) and APPDIR (its temporary mount).
# Both are checked, because APPIMAGE alone can leak in from a parent process that is itself an AppImage.
_appdir = os.environ.get("APPDIR")
IN_APPIMAGE = bool(os.environ.get("APPIMAGE") and _appdir and Path(os.environ["APPIMAGE"]).is_absolute()
                   and BASE.is_relative_to(Path(_appdir).resolve()))
APPIMAGE_FILE = os.environ.get("APPIMAGE") if IN_APPIMAGE else None

DEFAULTS = {
    "ui_language": "",  # empty = follow the system language
    "focus_min": 25,
    "short_break_min": 5,
    "long_break_min": 15,
    "cycles_before_long": 4,
    "auto_start_breaks": True,
    "auto_start_focus": False,
    "overlay_short": True,
    "overlay_long": True,
    "short_break_activity": "alternate",  # exercise | language | alternate | random | rest
    "language": "es",
    "sound": True,
    "tray_label": True,
}

ACTIVITIES = ["alternate", "exercise", "language", "random", "rest"]
FOCUS, SHORT, LONG = "focus", "short", "long"


def phase_name(phase):
    return t("phase." + phase)


CSS = b"""
.phase-label { font-size: 13px; font-weight: bold; letter-spacing: 2px; opacity: 0.7; }
.time-label { font-size: 64px; font-weight: 300; font-feature-settings: "tnum"; }
.focus .time-label { color: #e5484d; }
.break .time-label { color: #2fb37a; }
.dots { font-size: 18px; letter-spacing: 6px; }
.dim { opacity: 0.6; }

window.overlay { background-color: rgba(13, 15, 22, 0.95); }
.overlay label { color: #ececf1; }
.overlay .ov-phase { font-size: 15px; font-weight: bold; letter-spacing: 3px; color: #2fb37a; }
.overlay .ov-time { font-size: 104px; font-weight: 200; font-feature-settings: "tnum"; }
.overlay .ov-message { font-size: 20px; }
.overlay .card { background-color: rgba(255, 255, 255, 0.06); border-radius: 18px; }
.overlay .card-tag { font-size: 12px; font-weight: bold; letter-spacing: 2px; color: #ffd479; }
.overlay .card-title { font-size: 26px; font-weight: bold; }
.overlay .step { font-size: 16px; opacity: 0.75; }
.overlay .step.current { opacity: 1; color: #ffd479; font-weight: bold; }
.overlay .step.done { opacity: 0.35; }
.overlay .step-now { font-size: 22px; font-weight: bold; color: #ffd479; }
.overlay .term { font-size: 18px; font-weight: bold; color: #ffd479; }
.overlay .example { font-style: italic; opacity: 0.6; }
.overlay .question { font-size: 24px; font-weight: bold; }
.overlay button {
  background-image: none; background-color: rgba(255, 255, 255, 0.10);
  color: #ffffff; border: none; border-radius: 12px; box-shadow: none;
  padding: 10px 20px; font-size: 15px; text-shadow: none;
}
.overlay button:hover { background-color: rgba(255, 255, 255, 0.18); }
.overlay button.primary { background-color: #2f7cf6; }
.overlay button.primary:hover { background-color: #4a8ff8; }
.overlay button.correct, .overlay button.correct:disabled { background-color: #2e8b57; color: #ffffff; }
.overlay button.wrong, .overlay button.wrong:disabled { background-color: #c0392b; color: #ffffff; }
.overlay button:disabled { color: rgba(255, 255, 255, 0.5); }
.overlay button.close { border-radius: 999px; padding: 12px; }
.overlay progressbar trough { background-color: rgba(255, 255, 255, 0.1); min-height: 6px; border-radius: 3px; border: none; }
.overlay progressbar progress { background-color: #ffd479; min-height: 6px; border-radius: 3px; border: none; }
"""


# ---------------------------------------------------------------- helpers

def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def fmt(seconds):
    s = max(0, int(math.ceil(seconds)))
    return f"{s // 60:02d}:{s % 60:02d}"


def fmt_human(seconds):
    m, s = divmod(int(seconds), 60)
    return t("duration", m=m, s=s) if m else t("duration.short", s=s)


def _label(text, css=None, wrap=False, xalign=0.0):
    lbl = Gtk.Label(label=text, xalign=xalign)
    if wrap:
        lbl.set_line_wrap(True)
        lbl.set_max_width_chars(70)
    if css:
        lbl.get_style_context().add_class(css)
    return lbl


class Content:
    """Exercises and lessons for the current UI language, plus the user's own files in ~/.config/tomate/."""

    def __init__(self, ui_lang):
        base = CONTENT_DIR / ui_lang
        if not base.is_dir():
            base = CONTENT_DIR / "en"
        self.exercises = load_json(base / "exercises.json", [])
        self.exercises += load_json(CONFIG_DIR / "exercises.json", [])
        self.languages = {}
        for folder in (base / "lessons", CONFIG_DIR / "lessons"):
            if not folder.is_dir():
                continue
            for f in sorted(folder.glob("*.json")):
                data = load_json(f, None)
                if not isinstance(data, dict) or "code" not in data:
                    continue
                lang = self.languages.setdefault(data["code"], {
                    "code": data["code"],
                    "name": data.get("name", data["code"]),
                    "flag": data.get("flag", ""),
                    "lessons": [],
                })
                lang["lessons"].extend(l for l in data.get("lessons", []) if len(l.get("items", [])) >= 2)


# ---------------------------------------------------------------- timer

class Timer:
    def __init__(self, cfg, on_phase_change, demo=False):
        self.cfg = cfg
        self.on_phase_change = on_phase_change
        self.demo = demo  # minutes count as seconds, for testing
        self.phase = FOCUS
        self.cycle = 0  # focus sessions completed in the current cycle
        self.running = False
        self.remaining = self.duration(FOCUS)
        self._end = None

    def duration(self, phase):
        key = {FOCUS: "focus_min", SHORT: "short_break_min", LONG: "long_break_min"}[phase]
        minutes = float(self.cfg[key])
        return minutes if self.demo else minutes * 60

    def start(self):
        if not self.running:
            self._end = time.monotonic() + self.remaining
            self.running = True

    def pause(self):
        if self.running:
            self.remaining = max(0.0, self._end - time.monotonic())
            self.running = False

    def toggle(self):
        self.pause() if self.running else self.start()

    def reset(self):
        self.running = False
        self.remaining = self.duration(self.phase)

    def add(self, seconds):
        self.remaining += seconds
        if self.running:
            self._end += seconds

    def skip(self):
        self._advance(natural=False)

    def is_fresh(self):
        return not self.running and abs(self.remaining - self.duration(self.phase)) < 1

    def tick(self):
        if self.running:
            self.remaining = max(0.0, self._end - time.monotonic())
            if self.remaining <= 0:
                self._advance(natural=True)

    def _advance(self, natural):
        prev, was_running = self.phase, self.running
        if prev == FOCUS:
            self.cycle += 1
            nxt = LONG if self.cycle >= int(self.cfg["cycles_before_long"]) else SHORT
        else:
            if prev == LONG:
                self.cycle = 0
            nxt = FOCUS
        self.phase = nxt
        self.running = False
        self.remaining = self.duration(nxt)
        auto = self.cfg["auto_start_focus"] if nxt == FOCUS else self.cfg["auto_start_breaks"]
        if auto or (not natural and was_running):
            self.start()
        self.on_phase_change(prev, nxt, natural)


# ---------------------------------------------------------------- break activities

class ExerciseView(Gtk.Box):
    def __init__(self, exercise, sound):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.sound = sound
        self.steps = exercise.get("steps", [])
        self._src = None
        self._idx = -1

        total = sum(s.get("seconds", 0) for s in self.steps)
        self.pack_start(_label(t("ex.header", kind=exercise.get("kind", "").upper(), duration=fmt_human(total)),
                               "card-tag"), False, False, 0)
        self.pack_start(_label(exercise["title"], "card-title"), False, False, 0)
        if exercise.get("intro"):
            self.pack_start(_label(exercise["intro"], wrap=True), False, False, 4)

        self.step_labels = []
        steps_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=8)
        for i, step in enumerate(self.steps, 1):
            lbl = _label(f"{i}.  {step['text']}  ({step['seconds']}s)", "step", wrap=True)
            self.step_labels.append(lbl)
            steps_box.pack_start(lbl, False, False, 0)
        self.pack_start(steps_box, False, False, 0)

        self.now_label = _label("", "step-now", wrap=True, xalign=0.5)
        self.progress = Gtk.ProgressBar()
        self.pack_start(self.now_label, False, False, 6)
        self.pack_start(self.progress, False, False, 0)
        self.progress.set_no_show_all(True)

        self.start_btn = Gtk.Button(label=t("ex.start"), halign=Gtk.Align.CENTER, margin_top=6)
        self.start_btn.get_style_context().add_class("primary")
        self.start_btn.connect("clicked", lambda *_: self.start())
        self.pack_start(self.start_btn, False, False, 0)
        self.connect("destroy", lambda *_: self.stop())

    def start(self):
        self.start_btn.hide()
        self.progress.show()
        self._idx = -1
        self._next_step()

    def stop(self):
        if self._src:
            GLib.source_remove(self._src)
            self._src = None

    def _next_step(self):
        if 0 <= self._idx < len(self.step_labels):
            ctx = self.step_labels[self._idx].get_style_context()
            ctx.remove_class("current")
            ctx.add_class("done")
        self._idx += 1
        if self._idx >= len(self.steps):
            self._src = None
            self.progress.hide()
            self.now_label.set_text(t("ex.done"))
            self.sound.play("complete")
            return False
        step = self.steps[self._idx]
        self.step_labels[self._idx].get_style_context().add_class("current")
        if self._idx > 0:
            self.sound.play("message")
        self._step_len = float(step["seconds"])
        self._step_end = time.monotonic() + self._step_len
        self._update(step)
        self._src = GLib.timeout_add(200, self._tick)
        return False

    def _update(self, step):
        rem = max(0.0, self._step_end - time.monotonic())
        self.now_label.set_text(f"{step['text']}  ·  {int(math.ceil(rem))}s")
        self.progress.set_fraction(1 - rem / self._step_len if self._step_len else 1)
        return rem

    def _tick(self):
        if self._update(self.steps[self._idx]) <= 0:
            self._src = None
            self._next_step()
            return False
        return True


class LessonView(Gtk.Box):
    QUESTIONS = 4

    def __init__(self, language, lesson, on_done):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.language = language
        self.lesson = lesson
        self.on_done = on_done
        self._src = None
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vhomogeneous=False)
        self.pack_start(self.stack, True, True, 0)
        self.stack.add_named(self._build_lesson(), "lesson")
        self.quiz_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.stack.add_named(self.quiz_box, "quiz")
        self.connect("destroy", lambda *_: self._src and GLib.source_remove(self._src))

    def _build_lesson(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        lang = self.language
        box.pack_start(_label(t("lesson.header", flag=lang["flag"], language=lang["name"].upper()), "card-tag"),
                       False, False, 0)
        box.pack_start(_label(self.lesson["title"], "card-title"), False, False, 0)
        if self.lesson.get("tip"):
            box.pack_start(_label("💡 " + self.lesson["tip"], wrap=True), False, False, 4)

        grid = Gtk.Grid(column_spacing=24, row_spacing=4, margin_top=8)
        row = 0
        for item in self.lesson["items"]:
            grid.attach(_label(item["term"], "term", wrap=True), 0, row, 1, 1)
            grid.attach(_label(item["translation"], wrap=True), 1, row, 1, 1)
            row += 1
            if item.get("example"):
                grid.attach(_label(item["example"], "example", wrap=True), 0, row, 2, 1)
                row += 1
            grid.attach(Gtk.Box(margin_bottom=6), 0, row, 2, 1)
            row += 1
        box.pack_start(grid, False, False, 0)

        btn = Gtk.Button(label=t("lesson.quiz"), halign=Gtk.Align.CENTER, margin_top=6)
        btn.get_style_context().add_class("primary")
        btn.connect("clicked", lambda *_: self._start_quiz())
        box.pack_start(btn, False, False, 0)
        return box

    def _start_quiz(self):
        items = self.lesson["items"]
        chosen = random.sample(items, min(self.QUESTIONS, len(items)))
        self.questions = []
        for i, item in enumerate(chosen):
            if i % 2 == 0:
                prompt, key = t("quiz.meaning", term=item["term"]), "translation"
            else:
                prompt, key = t("quiz.say", translation=item["translation"], language=self.language["name"]), "term"
            answer = item[key]
            others = list({it[key] for it in items if it[key] != answer})
            options = [answer] + random.sample(others, min(3, len(others)))
            random.shuffle(options)
            self.questions.append((prompt, answer, options))
        self.q_idx, self.score = 0, 0
        self._show_question()
        self.stack.set_visible_child_name("quiz")

    def _clear_quiz(self):
        for child in self.quiz_box.get_children():
            child.destroy()

    def _show_question(self):
        self._clear_quiz()
        prompt, answer, options = self.questions[self.q_idx]
        self.quiz_box.pack_start(_label(t("quiz.header", n=self.q_idx + 1, total=len(self.questions)), "card-tag"),
                                 False, False, 0)
        self.quiz_box.pack_start(_label(prompt, "question", wrap=True), False, False, 4)
        self.buttons = []
        for opt in options:
            b = Gtk.Button(label=opt)
            b.connect("clicked", self._on_answer, opt, answer)
            self.buttons.append(b)
            self.quiz_box.pack_start(b, False, False, 0)
        self.quiz_box.show_all()

    def _on_answer(self, button, chosen, answer):
        for b in self.buttons:
            b.set_sensitive(False)
            if b.get_label() == answer:
                b.get_style_context().add_class("correct")
        if chosen == answer:
            self.score += 1
        else:
            button.get_style_context().add_class("wrong")
        self._src = GLib.timeout_add(1100, self._next_question)

    def _next_question(self):
        self._src = None
        self.q_idx += 1
        if self.q_idx < len(self.questions):
            self._show_question()
        else:
            self._show_result()
        return False

    def _show_result(self):
        self._clear_quiz()
        n = len(self.questions)
        emoji = "🏆" if self.score == n else "🎉" if self.score >= n / 2 else "📚"
        msg = t("quiz.perfect") if self.score == n else t("quiz.good") if self.score >= n / 2 else t("quiz.retry")
        self.quiz_box.pack_start(_label(t("quiz.score", emoji=emoji, score=self.score, total=n), "card-title",
                                        xalign=0.5), False, False, 0)
        self.quiz_box.pack_start(_label(msg, wrap=True, xalign=0.5), False, False, 0)
        again = Gtk.Button(label=t("quiz.review"), halign=Gtk.Align.CENTER)
        again.connect("clicked", lambda *_: self.stack.set_visible_child_name("lesson"))
        self.quiz_box.pack_start(again, False, False, 8)
        self.quiz_box.show_all()
        self.on_done(self.score, n)


class RestView(Gtk.Box):
    def __init__(self, long_break):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.pack_start(_label(t("rest.suggestions") if long_break else t("rest.rest"), "card-tag"), False, False, 0)
        ideas = random.sample(t("rest.ideas"), 3) if long_break else [t("rest.short")]
        for idea in ideas:
            self.pack_start(_label("•  " + idea, "step", wrap=True), False, False, 0)


# ---------------------------------------------------------------- break overlay

class BreakOverlay(Gtk.Window):
    def __init__(self, app, phase):
        super().__init__(title=t("overlay.title"))
        self.app = app
        self.seq = -1
        self.set_application(app)
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)
        self.get_style_context().add_class("overlay")
        self.connect("key-press-event", self._on_key)
        self.connect("destroy", self._on_destroy)

        layer = Gtk.Overlay()
        self.add(layer)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        layer.add(scroller)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                        halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, margin=48)
        outer.set_size_request(min(720, screen.get_width() - 96) if screen.get_width() > 200 else 600, -1)
        scroller.add(outer)

        self.phase_label = _label(phase_name(phase).upper(), "ov-phase", xalign=0.5)
        self.time_label = _label("", "ov-time", xalign=0.5)
        msg = t("overlay.long_msg") if phase == LONG else random.choice(t("overlay.short_msgs"))
        self.message = _label(msg, "ov-message", wrap=True, xalign=0.5)
        outer.pack_start(self.phase_label, False, False, 0)
        outer.pack_start(self.time_label, False, False, 0)
        outer.pack_start(self.message, False, False, 0)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=10)
        card.get_style_context().add_class("card")
        activity = app.make_activity(phase)
        activity.set_margin_top(28)
        activity.set_margin_bottom(28)
        activity.set_margin_start(32)
        activity.set_margin_end(32)
        card.pack_start(activity, False, False, 0)
        outer.pack_start(card, False, False, 0)

        self.actions = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER, margin_top=12)
        plus = Gtk.Button(label=t("overlay.add_minute"))
        plus.connect("clicked", lambda *_: app.timer.add(60))
        skip = Gtk.Button(label=t("overlay.end_break"))
        skip.connect("clicked", lambda *_: app.skip())
        hide = Gtk.Button(label=t("overlay.hide"))
        hide.connect("clicked", lambda *_: self.destroy())
        for b in (plus, skip, hide):
            self.actions.pack_start(b, False, False, 0)
        outer.pack_start(self.actions, False, False, 0)

        close = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        close.set_tooltip_text(t("overlay.close_tip"))
        close.set_halign(Gtk.Align.END)
        close.set_valign(Gtk.Align.START)
        close.set_margin_top(24)
        close.set_margin_end(24)
        close.get_style_context().add_class("close")
        close.connect("clicked", lambda *_: self.destroy())
        layer.add_overlay(close)

        self.update()
        self.fullscreen()
        self.show_all()
        self.present()

    def update(self):
        timer = self.app.timer
        if timer.phase != FOCUS:
            self.time_label.set_text(fmt(timer.remaining) + ("" if timer.running else "  ⏸"))

    def break_finished(self, focus_running):
        if focus_running:
            self.destroy()
            return
        self.phase_label.set_text(t("overlay.over"))
        self.time_label.set_text("00:00")
        self.message.set_text(t("overlay.ready"))
        for child in self.actions.get_children():
            child.destroy()
        go = Gtk.Button(label=t("overlay.start_focus"))
        go.get_style_context().add_class("primary")
        go.connect("clicked", lambda *_: (self.app.timer.start(), self.app.refresh(), self.destroy()))
        later = Gtk.Button(label=t("overlay.close"))
        later.connect("clicked", lambda *_: self.destroy())
        self.actions.pack_start(go, False, False, 0)
        self.actions.pack_start(later, False, False, 0)
        self.actions.show_all()
        go.grab_focus()

    def _on_key(self, _w, event):
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False

    def _on_destroy(self, *_):
        if self.app.overlay is self:
            self.app.overlay = None


# ---------------------------------------------------------------- main window

class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Tomate")
        self.app = app
        self.set_default_size(340, 380)
        self.set_icon_from_file(APP_ICON)

        header = Gtk.HeaderBar(show_close_button=True, title="Tomate")
        settings = Gtk.Button.new_from_icon_name("emblem-system-symbolic", Gtk.IconSize.BUTTON)
        settings.set_tooltip_text(t("win.settings"))
        settings.connect("clicked", lambda *_: app.open_settings())
        header.pack_end(settings)
        progress = Gtk.Button.new_from_icon_name("accessories-dictionary-symbolic", Gtk.IconSize.BUTTON)
        progress.set_tooltip_text(t("prog.title"))
        progress.connect("clicked", lambda *_: app.open_progress())
        header.pack_end(progress)
        self.set_titlebar(header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, border_width=24, valign=Gtk.Align.CENTER)
        self.box = box
        self.phase = _label("", "phase-label", xalign=0.5)
        self.time = _label("", "time-label", xalign=0.5)
        self.dots = _label("", "dots", xalign=0.5)
        for w in (self.phase, self.time, self.dots):
            box.pack_start(w, False, False, 0)

        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, margin_top=12)
        reset_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        reset_btn.set_tooltip_text(t("win.reset_tip"))
        reset_btn.connect("clicked", lambda *_: app.reset())
        self.toggle_btn = Gtk.Button(label=t("btn.start"))
        self.toggle_btn.set_size_request(120, -1)
        self.toggle_btn.get_style_context().add_class("suggested-action")
        self.toggle_btn.connect("clicked", lambda *_: app.toggle())
        skip_btn = Gtk.Button.new_from_icon_name("media-skip-forward-symbolic", Gtk.IconSize.BUTTON)
        skip_btn.set_tooltip_text(t("win.skip_tip"))
        skip_btn.connect("clicked", lambda *_: app.skip())
        for b in (reset_btn, self.toggle_btn, skip_btn):
            buttons.pack_start(b, False, False, 0)
        box.pack_start(buttons, False, False, 0)

        self.today = _label("", "dim", xalign=0.5)
        box.pack_start(self.today, False, False, 12)
        self.add(box)
        self.connect("delete-event", lambda *_: app.close_to_tray())

    def update(self):
        timer, cfg = self.app.timer, self.app.cfg
        ctx = self.box.get_style_context()
        ctx.remove_class("focus")
        ctx.remove_class("break")
        ctx.add_class("focus" if timer.phase == FOCUS else "break")
        suffix = "" if timer.running or timer.is_fresh() else t("win.paused_suffix")
        self.phase.set_text(phase_name(timer.phase).upper() + suffix)
        self.time.set_text(fmt(timer.remaining))
        n = int(cfg["cycles_before_long"])
        done = min(timer.cycle, n)
        self.dots.set_text("●" * done + "○" * (n - done))
        self.toggle_btn.set_label(self.app.toggle_label())
        count = self.app.today_count()
        self.today.set_text(t("win.today", n=count, plural="" if count == 1 else "s"))


# ---------------------------------------------------------------- settings

class SettingsDialog(Gtk.Dialog):
    def __init__(self, app):
        super().__init__(title=t("set.title"), transient_for=app.window, modal=True)
        self.add_buttons(t("set.cancel"), Gtk.ResponseType.CANCEL, t("set.save"), Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        cfg = app.cfg

        grid = Gtk.Grid(column_spacing=18, row_spacing=10, border_width=18)
        self.get_content_area().add(grid)
        self.widgets = {}
        row = 0

        def section(title):
            nonlocal row
            lbl = Gtk.Label(xalign=0, margin_top=6 if row else 0)
            lbl.set_markup(f"<b>{GLib.markup_escape_text(title)}</b>")
            grid.attach(lbl, 0, row, 2, 1)
            row += 1

        def add(key, text, widget):
            nonlocal row
            grid.attach(Gtk.Label(label=text, xalign=0), 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)
            if key:
                self.widgets[key] = widget
            row += 1
            return widget

        def spin(key, text, lo, hi):
            w = Gtk.SpinButton.new_with_range(lo, hi, 1)
            w.set_value(cfg[key])
            add(key, text, w)

        def switch(key, text, active=None):
            return add(key, text, Gtk.Switch(active=bool(cfg.get(key)) if active is None else active,
                                             halign=Gtk.Align.END))

        def combo(key, text, choices, current):
            w = Gtk.ComboBoxText()
            for cid, name in choices:
                w.append(cid, name)
            if not w.set_active_id(str(current)):
                w.set_active(0)
            add(key, text, w)

        section(t("set.periods"))
        spin("focus_min", t("set.focus"), 1, 180)
        spin("short_break_min", t("set.short"), 1, 60)
        spin("long_break_min", t("set.long"), 1, 120)
        spin("cycles_before_long", t("set.cycles"), 1, 12)
        section(t("set.behaviour"))
        switch("auto_start_breaks", t("set.auto_breaks"))
        switch("auto_start_focus", t("set.auto_focus"))
        switch("overlay_short", t("set.overlay_short"))
        switch("overlay_long", t("set.overlay_long"))
        switch("sound", t("set.sound"))
        switch("tray_label", t("set.tray_label"))
        section(t("set.short_breaks"))
        combo("short_break_activity", t("set.activity"), [(a, t("activity." + a)) for a in ACTIVITIES],
              cfg["short_break_activity"])
        langs = sorted(app.content.languages.values(), key=lambda l: l["name"])
        combo("language", t("set.learn"), [(l["code"], f"{l['flag']} {l['name']}") for l in langs] or [("es", "es")],
              cfg["language"])
        section(t("set.system"))
        combo("ui_language", t("set.ui_language"), i18n.LANGUAGES, i18n.current())
        self.autostart = switch(None, t("set.autostart"), active=AUTOSTART_FILE.exists())
        self.autostart_initial = self.autostart.get_active()
        if IN_APPIMAGE and not self.autostart_initial and not di.launchable_path(APPIMAGE_FILE):
            self.autostart.set_sensitive(False)
            self.autostart.set_tooltip_text(t("set.app_menu_bad_path"))
        self.app_menu = None
        if IN_APPIMAGE:
            ours = di.is_ours(APP_ID, DATA_HOME)
            self.app_menu = switch(None, t("set.app_menu"), active=ours)
            # an entry from another install (install.sh, a distro package) isn't ours to change
            if not ours and di.entry_exists(APP_ID, DATA_HOME):
                self.app_menu.set_sensitive(False)
                self.app_menu.set_tooltip_text(t("set.app_menu_other"))
            elif not ours and not di.launchable_path(APPIMAGE_FILE):
                self.app_menu.set_sensitive(False)
                self.app_menu.set_tooltip_text(t("set.app_menu_bad_path"))
        self.show_all()

    def collect(self):
        out = {}
        for key, w in self.widgets.items():
            if isinstance(w, Gtk.SpinButton):
                out[key] = int(w.get_value())
            elif isinstance(w, Gtk.Switch):
                out[key] = w.get_active()
            else:
                out[key] = w.get_active_id()
        app_menu = (self.app_menu.get_active()
                    if self.app_menu is not None and self.app_menu.get_sensitive() else None)
        # None = leave as is: only an actual flip of the switch touches the autostart file
        autostart = self.autostart.get_active()
        autostart = None if autostart == self.autostart_initial or not self.autostart.get_sensitive() else autostart
        return out, autostart, app_menu


# ---------------------------------------------------------------- language progress

class ProgressDialog(Gtk.Dialog):
    """Per-language progress: summary, lesson list (click = make it the next lesson), restart, switch language."""

    def __init__(self, app):
        super().__init__(title=t("prog.title"), modal=False)
        self.app = app
        self.set_default_size(480, 560)
        self.set_icon_from_file(APP_ICON)
        if app.window.get_visible():
            self.set_transient_for(app.window)
        self.add_button(t("prog.close"), Gtk.ResponseType.CLOSE)
        self.connect("response", lambda *_: self.destroy())

        box = self.get_content_area()
        box.set_spacing(12)
        box.set_border_width(18)

        self.combo = Gtk.ComboBoxText()
        for lang in sorted(app.content.languages.values(), key=lambda l: l["name"]):
            self.combo.append(lang["code"], f"{lang['flag']} {lang['name']}")
        if not self.combo.set_active_id(app.cfg["language"]):
            self.combo.set_active(0)
        self.combo.connect("changed", lambda *_: self.refresh())
        box.pack_start(self.combo, False, False, 0)

        self.summary = Gtk.Grid(column_spacing=14, row_spacing=6)
        box.pack_start(self.summary, False, False, 0)

        self.learning = Gtk.Box(spacing=8)
        box.pack_start(self.learning, False, False, 0)

        box.pack_start(_label(t("prog.hint"), "dim", wrap=True), False, False, 0)
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.listbox.connect("row-activated", self._on_row)
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_shadow_type(Gtk.ShadowType.IN)
        scroller.add(self.listbox)
        box.pack_start(scroller, True, True, 0)

        restart = Gtk.Button(label=t("prog.restart"), halign=Gtk.Align.START)
        restart.get_style_context().add_class("destructive-action")
        restart.connect("clicked", lambda *_: self._restart())
        box.pack_start(restart, False, False, 0)

        self.refresh()
        self.show_all()

    def code(self):
        return self.combo.get_active_id()

    def refresh(self):
        code = self.code()
        if not code:
            return
        lang = self.app.content.languages[code]
        st = self.app.lesson_stats(code)
        n = len(st["lessons"])

        for child in self.summary.get_children():
            child.destroy()
        current = st["lessons"][st["current"]]["title"] if n else "—"
        rows = [
            (t("prog.next"), t("prog.next_v", n=st["current"] + 1, total=n, title=current)),
            (t("prog.completed"), t("prog.completed_v", done=len(st["passed"]), total=n)),
            (t("prog.accuracy"), t("prog.accuracy_v", pct=round(100 * st["correct"] / st["answered"]),
                                   correct=st["correct"], answered=st["answered"])
             if st["answered"] else t("prog.no_quizzes")),
            (t("prog.last"), st["last"] or t("prog.never")),
        ]
        for i, (key, value) in enumerate(rows):
            k = Gtk.Label(xalign=0)
            k.set_markup(f"<b>{GLib.markup_escape_text(key)}</b>")
            self.summary.attach(k, 0, i, 1, 1)
            self.summary.attach(_label(value, wrap=True), 1, i, 1, 1)

        for child in self.learning.get_children():
            child.destroy()
        if code == self.app.cfg["language"]:
            self.learning.pack_start(_label("✔  " + t("prog.learning"), "dim"), False, False, 0)
        else:
            btn = Gtk.Button(label=t("prog.learn_this", language=lang["name"]))
            btn.get_style_context().add_class("suggested-action")
            btn.connect("clicked", lambda *_: (self.app.set_learning_language(code), self.refresh()))
            self.learning.pack_start(btn, False, False, 0)

        for row in self.listbox.get_children():
            row.destroy()
        for i, lesson in enumerate(st["lessons"]):
            best = st["best"].get(i)
            mark = "✔" if i in st["passed"] else ("◐" if best else "○")
            detail = t("prog.best", score=best[0], total=best[1]) if best else t("prog.not_tried")
            row_box = Gtk.Box(spacing=10, border_width=8)
            row_box.pack_start(_label(mark), False, False, 0)
            title = Gtk.Label(xalign=0)
            text = GLib.markup_escape_text(f"{i + 1}. {lesson['title']}")
            title.set_markup(f"<b>{text}</b>" if i == st["current"] else text)
            row_box.pack_start(title, True, True, 0)
            if i == st["current"]:
                row_box.pack_start(_label("▶ " + t("prog.next_tag")), False, False, 0)
            row_box.pack_end(_label(detail, "dim"), False, False, 0)
            row = Gtk.ListBoxRow()
            row.lesson_index = i
            row.add(row_box)
            self.listbox.add(row)
        self.summary.show_all()
        self.learning.show_all()
        self.listbox.show_all()

    def _on_row(self, _listbox, row):
        self.app.set_next_lesson(self.code(), row.lesson_index)
        self.refresh()

    def _restart(self):
        lang = self.app.content.languages[self.code()]
        dlg = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                                buttons=Gtk.ButtonsType.NONE, text=t("prog.restart_q", language=lang["name"]))
        dlg.format_secondary_text(t("prog.restart_body"))
        dlg.add_buttons(t("set.cancel"), Gtk.ResponseType.CANCEL, t("prog.restart_yes"), Gtk.ResponseType.OK)
        if dlg.run() == Gtk.ResponseType.OK:
            self.app.restart_language(lang["code"])
            self.refresh()
        dlg.destroy()


# ---------------------------------------------------------------- top bar

class Tray:
    def __init__(self, app):
        self.app = app
        self.status = tray.MenuItem(enabled=False)
        self.toggle = tray.MenuItem(callback=app.toggle)
        self.skip = tray.MenuItem(callback=app.skip)
        self.reset = tray.MenuItem(callback=app.reset)
        self.show_break = tray.MenuItem(callback=lambda: app.show_overlay(force=True))
        self.open = tray.MenuItem(callback=app.show_window)
        self.progress = tray.MenuItem(callback=app.open_progress)
        self.settings = tray.MenuItem(callback=app.open_settings)
        self.quit = tray.MenuItem(callback=app.quit)
        items = [self.status, tray.separator(), self.toggle, self.skip, self.reset, self.show_break,
                 tray.separator(), self.open, self.progress, self.settings, tray.separator(), self.quit]
        self.icon = tray.StatusIcon("tomate", "Tomate", str(ICON_DIR / "tomate-paused.svg"), items,
                                    on_activate=app.show_window, on_secondary=app.toggle)
        self.relabel()

    @property
    def available(self):
        return self.icon.available

    def relabel(self):
        self.skip.set_label(t("tray.skip"))
        self.reset.set_label(t("tray.reset"))
        self.show_break.set_label(t("tray.show_break"))
        self.open.set_label(t("tray.open"))
        self.progress.set_label(t("prog.title") + "…")
        self.settings.set_label(t("tray.settings"))
        self.quit.set_label(t("tray.quit"))

    def update(self):
        timer = self.app.timer
        name = "tomate-paused" if not timer.running else ("tomate" if timer.phase == FOCUS else "tomate-break")
        self.icon.set_icon(str(ICON_DIR / f"{name}.svg"))
        text = fmt(timer.remaining)
        self.icon.set_label(text if self.app.cfg["tray_label"] else "", "00:00")
        state = "running" if timer.running else "stopped" if timer.is_fresh() else "paused"
        status = f"{phase_name(timer.phase)} · {text} · {t('tray.state.' + state)}"
        self.icon.set_tooltip(status)
        self.status.set_label(status)
        self.toggle.set_label(self.app.toggle_label())
        self.show_break.set_visible(timer.phase != FOCUS and self.app.overlay is None)


class Sound:
    def __init__(self, app):
        self.app = app
        self.player = Gst.ElementFactory.make("playbin", None) if Gst else None

    def play(self, name):
        if not self.app.cfg["sound"]:
            return
        path = SOUND_DIR / f"{name}.oga"
        if self.player and path.exists():
            self.player.set_state(Gst.State.NULL)
            self.player.set_property("uri", path.as_uri())
            self.player.set_state(Gst.State.PLAYING)


# ---------------------------------------------------------------- application

class TomateApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None
        self.overlay = None
        self.progress_dialog = None
        self.tray = None
        self.timer = None
        self._started = False

    # -- lifecycle
    def do_startup(self):
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.cfg = {**DEFAULTS, **load_json(CONFIG_FILE, {})}
        i18n.set_language(self.cfg["ui_language"] or i18n.system_language())
        self.state = load_json(STATE_FILE, {})
        self.content = Content(i18n.current())
        self.sound = Sound(self)
        self.notification = None
        if Notify and Notify.init("Tomate"):
            self.notification = Notify.Notification.new("Tomate", "", APP_ICON)
        self._break_seq = 0
        self._overlay_shown_for = -1
        self._last_text = None

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Ctrl>q"])

        self.window = MainWindow(self)
        try:
            self.tray = Tray(self)
        except Exception as exc:  # no session bus, etc. The app still works, just without the icon
            print("Tomate: top-bar icon unavailable:", exc, file=sys.stderr)
        self.hold()  # keep running when the window is closed

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        first = not self._started
        if first:
            self._started = True
            self.timer = Timer(self.cfg, self._on_phase_change, demo="--demo" in args)
            GLib.timeout_add(250, self._tick)
        actions = {"--toggle": self.toggle, "--skip": self.skip, "--reset": self.reset,
                   "--show": self.show_window, "--quit": self.quit}
        handled = False
        for a in args:
            if a in actions:
                actions[a]()
                handled = True
            elif a in ("-h", "--help"):
                usage = "usage: tomate [--hidden] [--toggle|--skip|--reset|--show|--quit] [--demo]\n"
                if hasattr(command_line, "print_literal"):  # GLib >= 2.80; the varargs print() isn't bound
                    command_line.print_literal(usage)
                else:
                    print(usage, end="")
                handled = True
                if first:  # nothing else asked for: don't leave an instance running in the background
                    self.quit()
                    return 0
        if not handled and not (first and "--hidden" in args):
            self.show_window()
        if first and IN_APPIMAGE:
            self._appimage_refresh()
            if not handled and "--hidden" not in args:  # only ask when the user is actually looking
                GLib.idle_add(self._appimage_offer_menu)
        self.refresh()
        return 0

    # -- actions
    def toggle(self):
        self.timer.toggle()
        self.refresh()

    def skip(self):
        self.timer.skip()
        self.refresh()

    def reset(self):
        self.timer.reset()
        self.refresh()

    def toggle_label(self):
        timer = self.timer
        return t("btn.pause") if timer.running else (t("btn.start") if timer.is_fresh() else t("btn.resume"))

    def show_window(self):
        self.window.show_all()
        self.window.deiconify()
        self.window.present()

    def close_to_tray(self):
        """Closing the window keeps Tomate running in the top bar (or minimised if there's no tray host)."""
        if self.tray and self.tray.available:
            self.window.hide()
            if not self.state.get("close_hint_shown"):
                self.state["close_hint_shown"] = True
                self._save_state()
                self._notify(t("notify.still_running"), t("notify.still_running_body"))
        else:
            self.window.iconify()
        return True

    def open_settings(self):
        dlg = SettingsDialog(self)
        response = dlg.run()
        values, autostart, app_menu = dlg.collect()
        dlg.destroy()
        if response == Gtk.ResponseType.OK:
            self.apply_settings(values, autostart, app_menu)

    def apply_settings(self, values, autostart=None, app_menu=None):
        """Save settings. `autostart` / `app_menu`: True or False to change them, None to leave them alone."""
        ui_changed = values["ui_language"] != i18n.current()
        self.cfg.update(values)
        save_json(CONFIG_FILE, {k: self.cfg[k] for k in DEFAULTS})
        try:
            if autostart is not None:
                self._set_autostart(autostart)
            if app_menu is not None and app_menu != di.is_ours(APP_ID, DATA_HOME):
                self._set_app_menu(app_menu)
        except OSError as exc:  # e.g. a full disk: report it, don't lose the rest of the save
            print("Tomate: couldn't update the menu/autostart entry:", exc, file=sys.stderr)
        if self.timer.is_fresh():
            self.timer.reset()
        if ui_changed:
            self._apply_ui_language()
        self.refresh()

    def _apply_ui_language(self):
        i18n.set_language(self.cfg["ui_language"])
        self.content = Content(i18n.current())
        if self.progress_dialog:  # its contents are in the old language
            self.progress_dialog.destroy()
        old, was_visible = self.window, self.window.get_visible()
        self.window = MainWindow(self)
        if was_visible:
            self.show_window()
        old.destroy()
        if self.tray:
            self.tray.relabel()

    def _set_autostart(self, enabled):
        if not enabled:
            if AUTOSTART_FILE.exists():
                AUTOSTART_FILE.unlink()
            if IN_APPIMAGE:
                di.remove_icon_if_unused(DATA_HOME, di.desktop_path(APP_ID, DATA_HOME))
            return
        args = di.launcher_args(APPIMAGE_FILE, sys.executable, BASE / "tomate.py") + ["--hidden"]
        if IN_APPIMAGE:
            # Marked, so it's kept pointing at the AppImage when the file moves (see _appimage_refresh).
            di.write_entry(AUTOSTART_FILE, [
                ("Type", "Application"), ("Name", "Tomate"), ("Exec", di.exec_line(args)),
                ("Icon", str(di.ensure_icon(APP_ICON, DATA_HOME))), ("X-GNOME-Autostart-enabled", "true"),
            ])
        else:
            AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
            AUTOSTART_FILE.write_text(
                "[Desktop Entry]\nType=Application\nName=Tomate\n"
                f"Exec={di.exec_line(args)}\n"
                f"Icon={APP_ICON}\nX-GNOME-Autostart-enabled=true\n", encoding="utf-8")

    # -- AppImage: app-menu entry
    def _set_app_menu(self, enabled):
        if enabled:
            if not di.integrate(APP_ID, APPIMAGE_FILE, APP_ICON, DATA_HOME, "Tomate", t("appimage.comment")):
                self._notify(t("appimage.not_added"), t("set.app_menu_bad_path")
                             if not di.launchable_path(APPIMAGE_FILE) else t("set.app_menu_other"))
        elif di.remove(APP_ID, DATA_HOME):
            autostart_uses_icon = di.is_marked(AUTOSTART_FILE)
            di.remove_icon_if_unused(DATA_HOME, *([AUTOSTART_FILE] if autostart_uses_icon else []))

    def _appimage_refresh(self):
        """Keep Tomate's own entries pointing at this AppImage after it was moved or renamed (e.g. by an
        update). Entries without Tomate's mark are never touched. Never stops Tomate from starting."""
        if not di.launchable_path(APPIMAGE_FILE):
            return  # GNOME couldn't launch this path anyway; leave the existing entries as they are
        try:
            if di.needs_refresh(APP_ID, APPIMAGE_FILE, DATA_HOME):
                self._set_app_menu(True)
            if di.exec_differs(AUTOSTART_FILE, [APPIMAGE_FILE, "--hidden"]):
                self._set_autostart(True)
        except OSError as exc:
            print("Tomate: couldn't update the menu/autostart entry:", exc, file=sys.stderr)

    def _appimage_offer_menu(self):
        """First run of the AppImage: offer an app-menu entry, once."""
        if (self.state.get("appimage_menu_asked") or di.entry_exists(APP_ID, DATA_HOME)
                or not di.launchable_path(APPIMAGE_FILE)):
            return False
        self.state["appimage_menu_asked"] = True
        self._save_state()
        dlg = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.QUESTION,
                                buttons=Gtk.ButtonsType.NONE, text=t("appimage.ask_title"))
        dlg.format_secondary_text(t("appimage.ask_body"))
        dlg.add_buttons(t("appimage.not_now"), Gtk.ResponseType.NO, t("appimage.add"), Gtk.ResponseType.YES)
        dlg.set_default_response(Gtk.ResponseType.YES)
        if dlg.run() == Gtk.ResponseType.YES:
            self._set_app_menu(True)
        dlg.destroy()
        return False

    # -- ticking
    def _tick(self):
        self.timer.tick()
        if (fmt(self.timer.remaining), self.timer.running, self.timer.phase) != self._last_text:
            self.refresh()
        return True

    def refresh(self):
        timer = self.timer
        self._last_text = (fmt(timer.remaining), timer.running, timer.phase)
        if timer.phase != FOCUS and timer.running and self._overlay_shown_for != self._break_seq:
            self.show_overlay()
        self.window.update()
        if self.overlay:
            self.overlay.update()
        if self.tray:
            self.tray.update()

    def _on_phase_change(self, prev, nxt, natural):
        self._break_seq += 1
        if prev == FOCUS and natural:
            stats = self.state.setdefault("stats", {})
            today = date.today().isoformat()
            stats[today] = stats.get(today, 0) + 1
            self._save_state()
        if natural:
            self.sound.play("complete" if nxt != FOCUS else "bell")
            if nxt == FOCUS:
                self._notify(t("notify.break_over"),
                             t("notify.back") if self.timer.running else t("notify.press_start"))
            else:
                mins = int(self.timer.duration(nxt) // (1 if self.timer.demo else 60))
                self._notify(t("notify.break_time"), t("notify.break_body", phase=phase_name(nxt), mins=mins))
        if nxt == FOCUS and self.overlay:
            self.overlay.break_finished(self.timer.running)

    def show_overlay(self, force=False):
        timer = self.timer
        self._overlay_shown_for = self._break_seq
        if timer.phase == FOCUS:
            return
        if not force and not self.cfg["overlay_long" if timer.phase == LONG else "overlay_short"]:
            return
        if self.overlay and self.overlay.seq == self._break_seq:
            self.overlay.present()
            return
        if self.overlay:  # a screen from an earlier break is still open
            self.overlay.destroy()
        self.overlay = BreakOverlay(self, timer.phase)
        self.overlay.seq = self._break_seq

    def _notify(self, title, body):
        if self.notification:
            self.notification.update(title, body, APP_ICON)
            try:
                self.notification.show()
            except GLib.Error:
                pass

    # -- activities
    def make_activity(self, phase):
        if phase == LONG:
            return RestView(long_break=True)
        mode = self.cfg["short_break_activity"]
        if mode == "alternate":
            kind = "language" if self.state.get("last_activity") == "exercise" else "exercise"
        elif mode == "random":
            kind = random.choice(["exercise", "language"])
        else:
            kind = mode
        lang = self.content.languages.get(self.cfg["language"])
        if kind == "language" and not (lang and lang["lessons"]):
            kind = "exercise"
        if kind == "exercise" and not self.content.exercises:
            kind = "rest"
        self.state["last_activity"] = kind
        self._save_state()

        if kind == "exercise":
            return ExerciseView(self._pick_exercise(), self.sound)
        if kind == "language":
            progress = self.state.setdefault("lang_progress", {})
            idx = progress.get(lang["code"], 0) % len(lang["lessons"])
            return LessonView(lang, lang["lessons"][idx], lambda s, n: self._lesson_done(lang, idx, s, n))
        return RestView(long_break=False)

    def _pick_exercise(self):
        exercises = self.content.exercises
        recent = self.state.get("recent_exercises", [])
        pool = [e for e in exercises if e["title"] not in recent] or exercises
        ex = random.choice(pool)
        keep = max(0, min(5, len(exercises) - 1))
        self.state["recent_exercises"] = ([ex["title"]] + [r for r in recent if r != ex["title"]])[:keep]
        self._save_state()
        return ex

    def _lesson_done(self, lang, idx, score, total):
        self.state.setdefault("lang_progress", {})[lang["code"]] = idx + 1 if score >= total / 2 else idx
        self.state.setdefault("quiz_history", []).append(
            {"date": date.today().isoformat(), "lang": lang["code"], "lesson": idx, "score": score, "total": total})
        self.state["quiz_history"] = self.state["quiz_history"][-QUIZ_HISTORY_MAX:]
        self._save_state()
        if self.progress_dialog:
            self.progress_dialog.refresh()

    # -- language progress
    def lesson_stats(self, code):
        """Summary of a language's progress, derived from lang_progress and quiz_history."""
        lang = self.content.languages.get(code)
        lessons = lang["lessons"] if lang else []
        best, correct, answered, last = {}, 0, 0, None
        for h in self.state.get("quiz_history", []):
            if h.get("lang") != code or not h.get("total"):
                continue
            i = h.get("lesson")
            correct += h["score"]
            answered += h["total"]
            last = max(last or h["date"], h["date"])
            if i is not None and i < len(lessons):
                prev = best.get(i)
                if prev is None or h["score"] / h["total"] > prev[0] / prev[1]:
                    best[i] = (h["score"], h["total"])
        passed = {i for i, (s, n) in best.items() if s >= n / 2}
        current = self.state.get("lang_progress", {}).get(code, 0) % len(lessons) if lessons else 0
        return {"lessons": lessons, "current": current, "best": best, "passed": passed,
                "correct": correct, "answered": answered, "last": last}

    def set_next_lesson(self, code, idx):
        self.state.setdefault("lang_progress", {})[code] = idx
        self._save_state()

    def restart_language(self, code):
        self.state.setdefault("lang_progress", {})[code] = 0
        self.state["quiz_history"] = [h for h in self.state.get("quiz_history", []) if h.get("lang") != code]
        self._save_state()

    def set_learning_language(self, code):
        self.cfg["language"] = code
        save_json(CONFIG_FILE, {k: self.cfg[k] for k in DEFAULTS})

    def open_progress(self):
        if self.progress_dialog:
            self.progress_dialog.present()
            return
        self.progress_dialog = ProgressDialog(self)
        self.progress_dialog.connect("destroy", lambda *_: setattr(self, "progress_dialog", None))
        self.progress_dialog.present()

    def today_count(self):
        return self.state.get("stats", {}).get(date.today().isoformat(), 0)

    def _save_state(self):
        save_json(STATE_FILE, self.state)


def main():
    GLib.set_prgname(APP_ID)
    GLib.set_application_name("Tomate")
    return TomateApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
