#!/usr/bin/env python3
"""
generate_banner.py — LitScan README banner generator.

Generates docs/assets/banner.svg (dark theme, 1200x280).

Usage:
    python docs/scripts/generate_banner.py

Output: docs/assets/banner.svg
Dependencies: stdlib only.
"""

from pathlib import Path

# ── Editable stats (keep in sync with the codebase) ──
STATS = [
    ("7", "Data Sources"),
    ("20", "API Endpoints"),
    ("240", "Edge Tests"),
    ("3.2k+", "Lines of Python"),
]

OUT = Path(__file__).resolve().parent.parent / "assets" / "banner.svg"


def chips() -> str:
    """Render stat chips centered under the title."""
    total_w = len(STATS) * 190
    x = (1200 - total_w) / 2
    parts = []
    for i, (num, label) in enumerate(STATS):
        cx = x + i * 190
        parts.append(f"""
  <g transform="translate({cx:.0f},186)">
    <rect x="0" y="0" width="170" height="64" rx="12" fill="#161e33"
          stroke="#2a3a5f" stroke-width="1"/>
    <text x="85" y="28" text-anchor="middle" font-size="22" font-weight="700"
          fill="#5b9dff">{num}</text>
    <text x="85" y="50" text-anchor="middle" font-size="11"
          fill="#8b9cc0">{label}</text>
  </g>""")
    return "\n".join(parts)


SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 280" font-family="'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0b1020"/>
      <stop offset="1" stop-color="#141b33"/>
    </linearGradient>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#5b9dff"/>
      <stop offset="1" stop-color="#9d6bff"/>
    </linearGradient>
  </defs>

  <rect width="1200" height="280" fill="url(#bg)"/>

  <!-- decorative book/search glyph -->
  <g transform="translate(96,88)" opacity="0.9">
    <circle cx="0" cy="0" r="34" fill="none" stroke="#5b9dff" stroke-width="4"/>
    <line x1="24" y1="24" x2="46" y2="46" stroke="#9d6bff" stroke-width="6" stroke-linecap="round"/>
    <path d="M -14 -8 L 14 -8 M -14 0 L 14 0 M -14 8 L 6 8" stroke="#5b9dff"
          stroke-width="3" stroke-linecap="round"/>
  </g>

  <text x="170" y="112" font-size="54" font-weight="800" fill="#f0f4ff">LitScan</text>
  <rect x="172" y="128" width="220" height="5" rx="2.5" fill="url(#accent)"/>
  <text x="170" y="162" font-size="17" fill="#aab8d8">学术文献多库检索 · 开放全文 PDF 下载 · Multi-Database Literature Scanner</text>

{chips()}
</svg>
"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(SVG, encoding="utf-8")
print(f"written: {OUT}")
