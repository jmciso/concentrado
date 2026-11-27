# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 João Mendes
"""Generates the Concentrado icons: a tin of tomato paste ("concentrado de tomate").

app.svg is the app icon; concentrado-{focus,break,paused}.svg are the top-bar variants (tighter crop,
label colour per state).
"""
import math
from pathlib import Path

OUT = Path(__file__).resolve().parent / "icons"

# Tin geometry: a cylinder seen from slightly above.
CX, RX, RY = 64, 38, 9
LEFT, RIGHT = CX - RX, CX + RX
TOP, BOTTOM = 30, 110
LABEL_TOP, LABEL_BOTTOM, BAND = 45, 99, 8


def band(y0, y1):
    """Front face of the cylinder between heights y0 and y1 (edges curve down, like the rim)."""
    return (f"M{LEFT} {y0} A{RX} {RY} 0 0 0 {RIGHT} {y0} L{RIGHT} {y1} "
            f"A{RX} {RY} 0 0 1 {LEFT} {y1} Z")


def calyx(cx, cy, r, n=5, rot=-90):
    parts = []
    for i in range(n):
        a = math.radians(rot + i * 360 / n + 8 * (i % 2))
        tip = (cx + r * math.cos(a), cy + r * 0.5 * math.sin(a) + 7)
        w = math.radians(30)
        c1 = (cx + r * 0.7 * math.cos(a - w), cy + r * 0.35 * math.sin(a - w) - 1)
        c2 = (cx + r * 0.7 * math.cos(a + w), cy + r * 0.35 * math.sin(a + w) + 3)
        parts.append(f"M{cx:.1f} {cy:.1f} Q{c1[0]:.1f} {c1[1]:.1f} {tip[0]:.1f} {tip[1]:.1f} "
                     f"Q{c2[0]:.1f} {c2[1]:.1f} {cx:.1f} {cy:.1f}Z")
    return " ".join(parts)


TOMATO = ("M64 36 C50 26 30 29 20 44 C10 59 12 86 26 101 C38 114 52 118 64 118 "
          "C76 118 90 114 102 101 C116 86 118 59 108 44 C98 29 78 26 64 36Z")


def svg(label, label_dark, fruit, fruit_light, fruit_dark, leaf, leaf_dark, tray=False):
    s = 0.33  # tomato emblem scale; its own drawing is centred on (64, 72)
    ex, ey = CX - 64 * s, (LABEL_TOP + LABEL_BOTTOM) / 2 + 4 - 74 * s
    view = "18 17 92 106" if tray else "0 0 128 128"
    if tray:
        # Small sizes: the whole label in the state colour, with a white tomato, readable at 16 px.
        s = 0.40
        ex, ey = CX - 64 * s, (LABEL_TOP + LABEL_BOTTOM) / 2 + 3 - 74 * s
        label_art = f'''<path d="{band(LABEL_TOP, LABEL_BOTTOM)}" fill="{label}"/>
  <g transform="translate({ex:.2f} {ey:.2f}) scale({s})">
    <path d="{TOMATO}" fill="#fff"/>
    <path d="{calyx(64, 38, 33)}" fill="#fff" stroke="{label_dark}" stroke-width="3" stroke-linejoin="round"/>
  </g>'''
    else:
        label_art = f'''<path d="{band(LABEL_TOP, LABEL_BOTTOM)}" fill="#fbf4e6"/>
  <path d="{band(LABEL_TOP, LABEL_TOP + BAND)}" fill="{label}"/>
  <path d="{band(LABEL_BOTTOM - BAND, LABEL_BOTTOM)}" fill="{label}"/>
  <path d="{band(LABEL_TOP + BAND, LABEL_TOP + BAND + 1.5)}" fill="{label_dark}" opacity="0.6"/>
  <path d="{band(LABEL_BOTTOM - BAND - 1.5, LABEL_BOTTOM - BAND)}" fill="{label_dark}" opacity="0.6"/>
  <g transform="translate({ex:.2f} {ey:.2f}) scale({s})">
    <path d="{TOMATO}" fill="url(#fruit)"/>
    <ellipse cx="42" cy="58" rx="13" ry="8" fill="#fff" opacity="0.5" transform="rotate(-38 42 58)"/>
    <path d="{calyx(64, 38, 33)}" fill="{leaf}" stroke="{leaf_dark}" stroke-width="2" stroke-linejoin="round"/>
    <path d="M60.5 38 C60 32 61 27 64 22 C65.5 19.5 69.5 20 69 23 C67 27 67.5 32 68 38Z" fill="{leaf}" stroke="{leaf_dark}" stroke-width="2"/>
  </g>'''
    shadow = "" if tray else f'<ellipse cx="{CX}" cy="{BOTTOM + 8}" rx="{RX + 4}" ry="5" fill="#000" opacity="0.18"/>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="{view}">
  <defs>
    <linearGradient id="metal" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#7c838c"/><stop offset="0.3" stop-color="#eef1f4"/>
      <stop offset="0.55" stop-color="#c3c9d0"/><stop offset="1" stop-color="#6b727b"/>
    </linearGradient>
    <linearGradient id="lid" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#f4f6f8"/><stop offset="1" stop-color="#9ba2ab"/>
    </linearGradient>
    <linearGradient id="shade" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#000" stop-opacity="0.35"/><stop offset="0.3" stop-color="#fff" stop-opacity="0.18"/>
      <stop offset="0.6" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.4"/>
    </linearGradient>
    <radialGradient id="fruit" cx="0.38" cy="0.36" r="0.75">
      <stop offset="0" stop-color="{fruit_light}"/><stop offset="0.55" stop-color="{fruit}"/>
      <stop offset="1" stop-color="{fruit_dark}"/>
    </radialGradient>
  </defs>
  {shadow}
  <path d="M{LEFT} {TOP} L{LEFT} {BOTTOM} A{RX} {RY} 0 0 0 {RIGHT} {BOTTOM} L{RIGHT} {TOP} Z" fill="url(#metal)"/>
  <path d="{band(BOTTOM - 5, BOTTOM - 3)}" fill="#000" opacity="0.18"/>
  {label_art}
  <path d="{band(LABEL_TOP, LABEL_BOTTOM)}" fill="url(#shade)"/>
  <ellipse cx="{CX}" cy="{TOP}" rx="{RX}" ry="{RY}" fill="url(#lid)" stroke="#6b727b" stroke-width="1"/>
  <ellipse cx="{CX}" cy="{TOP}" rx="{RX - 5}" ry="{RY - 2.2}" fill="none" stroke="#8a919a" stroke-width="1.2" opacity="0.8"/>
  <ellipse cx="{CX - 12}" cy="{TOP - 2}" rx="12" ry="2.2" fill="#fff" opacity="0.6"/>
</svg>
'''


RED = ("#d9302a", "#8f1512", "#e8362c", "#ff8a75", "#a3161b", "#6cc24a", "#2f7d32")
GREEN = ("#3e9b45", "#1d5e22", "#6cc24a", "#c8f08a", "#2f7d32", "#3c9a3c", "#1d5e22")
GREY = ("#8e939b", "#5f646b", "#9a9aa4", "#d6d6dc", "#5f5f69", "#b5b5bd", "#6f6f78")

if __name__ == "__main__":
    (OUT / "app.svg").write_text(svg(*RED))
    for name, colors in {"focus": RED, "break": GREEN, "paused": GREY}.items():
        (OUT / f"concentrado-{name}.svg").write_text(svg(*colors, tray=True))
    print("ok")
