# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 João Mendes
"""Generates the Tomate icons (app icon + tray state variants)."""
import math
from pathlib import Path

OUT = Path(__file__).resolve().parent / "icons"

def calyx(cx, cy, r, n=5, rot=-90):
    parts = []
    for i in range(n):
        a = math.radians(rot + i * 360 / n + 8 * (i % 2))
        sy = 0.5
        tip = (cx + r * math.cos(a), cy + r * sy * math.sin(a) + 7)  # tips droop onto the fruit
        w = math.radians(30)
        c1 = (cx + r * 0.7 * math.cos(a - w), cy + r * 0.7 * sy * math.sin(a - w) - 1)
        c2 = (cx + r * 0.7 * math.cos(a + w), cy + r * 0.7 * sy * math.sin(a + w) + 3)
        parts.append(f"M{cx:.1f} {cy:.1f} Q{c1[0]:.1f} {c1[1]:.1f} {tip[0]:.1f} {tip[1]:.1f} "
                     f"Q{c2[0]:.1f} {c2[1]:.1f} {cx:.1f} {cy:.1f}Z")
    return " ".join(parts)

BODY = ("M64 36 C50 26 30 29 20 44 C10 59 12 86 26 101 C38 114 52 118 64 118 "
        "C76 118 90 114 102 101 C116 86 118 59 108 44 C98 29 78 26 64 36Z")

def svg(light, mid, dark, leaf, leaf_dark, shine=0.55, ribs=True, tray=False):
    rib = ("" if not ribs else
           '<path d="M64 36 C56 60 56 92 64 116 M64 36 C72 60 72 92 64 116 M40 38 C30 60 32 92 46 112 '
           'M88 38 C98 60 96 92 82 112" fill="none" stroke="%s" stroke-width="2" stroke-linecap="round" opacity="0.10"/>' % dark)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="{'10 16 108 106' if tray else '0 0 128 128'}">
  <defs>
    <radialGradient id="b" cx="0.38" cy="0.36" r="0.75">
      <stop offset="0" stop-color="{light}"/>
      <stop offset="0.55" stop-color="{mid}"/>
      <stop offset="1" stop-color="{dark}"/>
    </radialGradient>
    <linearGradient id="l" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{leaf}"/>
      <stop offset="1" stop-color="{leaf_dark}"/>
    </linearGradient>
  </defs>
  {'' if tray else '<ellipse cx="64" cy="121" rx="38" ry="4.5" fill="#000" opacity="0.16"/>'}
  <path d="{BODY}" fill="url(#b)"/>
  {rib}
  <ellipse cx="42" cy="58" rx="13" ry="8" fill="#fff" opacity="{shine}" transform="rotate(-38 42 58)"/>
  <ellipse cx="33" cy="74" rx="3.2" ry="2.2" fill="#fff" opacity="{shine * 0.7:.2f}" transform="rotate(-50 33 74)"/>
  <path d="{calyx(64, 38, 33)}" fill="url(#l)" stroke="{leaf_dark}" stroke-width="1" stroke-linejoin="round"/>
  <path d="M60.5 38 C60 32 61 27 64 22 C65.5 19.5 69.5 20 69 23 C67 27 67.5 32 68 38Z" fill="url(#l)" stroke="{leaf_dark}" stroke-width="1"/>
</svg>
'''

VARIANTS = {
    "tomate":        ("#ff8a75", "#e8362c", "#a3161b", "#7ed957", "#2f8f2f"),
    "tomate-break":  ("#c8f08a", "#6cc24a", "#2f7d32", "#3c9a3c", "#1d5e22"),
    "tomate-paused": ("#d6d6dc", "#9a9aa4", "#5f5f69", "#b5b5bd", "#6f6f78"),
}
for name, colors in VARIANTS.items():
    (OUT / f"{name}.svg").write_text(svg(*colors, tray=True))
(OUT / "app.svg").write_text(svg(*VARIANTS["tomate"]))
print("ok")
