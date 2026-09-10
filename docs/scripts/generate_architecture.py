#!/usr/bin/env python3
"""
generate_architecture.py — LitScan architecture diagram generator.

Generates docs/assets/architecture.svg (dark theme, 1200x840), showing:
  clients (CLI / Web / API+SSE) -> FastAPI server -> Scanner
  -> Fetcher -> 7 source adapters
  -> full-text download pipeline (resolve PDF link -> download -> out/pdf/)
  -> outputs (CSV / log / history / exports / pdf / raw).

Usage:
    python docs/scripts/generate_architecture.py

Output: docs/assets/architecture.svg
Dependencies: stdlib only.
"""

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets" / "architecture.svg"

SOURCES = ["arXiv", "Semantic Scholar", "Crossref", "OpenReview", "OpenAIRE", "DOAJ", "Europe PMC"]


def box(x, y, w, h, title, sub, fill, stroke, title_fill="#f0f4ff", rx=10):
    sub_lines = sub.split("|")
    tspans = "".join(
        f'<tspan x="{x + w / 2:.0f}" dy="{18 if i else 0}">{s}</tspan>'
        for i, s in enumerate(sub_lines)
    )
    ty = y + (h / 2 - (len(sub_lines) - 1) * 9 + 4)
    return f"""
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>
  <text x="{x + w / 2:.0f}" y="{ty:.0f}" text-anchor="middle" font-size="15" font-weight="700" fill="{title_fill}">{title}</text>
  <text x="{x + w / 2:.0f}" y="{ty + 18:.0f}" text-anchor="middle" font-size="11" fill="#8b9cc0">{tspans}</text>"""


def arrow(x1, y1, x2, y2, color="#5b9dff", dashed=False):
    dash = ' stroke-dasharray="5,4"' if dashed else ""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
            f'stroke-width="1.6" marker-end="url(#ah)"{dash}/>')


# adapter grid: 2 rows
def adapters():
    parts = []
    w, h, gap = 172, 46, 22
    x0 = (1200 - 4 * w - 3 * gap) / 2
    for i, name in enumerate(SOURCES):
        row, col = divmod(i, 4)
        x = x0 + col * (w + gap)
        y = 450 + row * (h + 18)
        enabled = name != "Europe PMC"
        stroke = "#2a3a5f"
        tag = ""
        if not enabled:
            tag = ' <tspan fill="#e8b34b" font-size="9"> (opt)</tspan>'
        parts.append(
            f'<g><rect x="{x:.0f}" y="{y}" width="{w}" height="{h}" rx="8" fill="#141d36" stroke="{stroke}"/>'
            f'<text x="{x + w / 2:.0f}" y="{y + h / 2 + 4:.0f}" text-anchor="middle" '
            f'font-size="12" fill="#c6d4f0">{name}{tag}</text></g>'
        )
    return "\n".join(parts), x0


# outputs row: 6 cards
def outputs():
    items = [
        ("articles.csv", "统一格式结果"),
        ("log.md", "检索日志"),
        ("history.json", "搜索历史"),
        ("exports/", "导出留档"),
        ("pdf/", "开放全文 PDF"),
        ("raw/", "各库原始响应"),
    ]
    w, h, gap = 151, 58, 16
    x0 = 105
    y = 736
    hi = {"pdf/"}
    parts = []
    for i, (name, desc) in enumerate(items):
        x = x0 + i * (w + gap)
        fill = "#12203a" if name in hi else "#12182b"
        stroke = "#356bb0" if name in hi else "#24406e"
        parts.append(f"""
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fill}" stroke="{stroke}"/>
  <text x="{x + w / 2:.0f}" y="{y + 26:.0f}" text-anchor="middle" font-size="13" font-weight="700" fill="#d8e3ff">{name}</text>
  <text x="{x + w / 2:.0f}" y="{y + 45:.0f}" text-anchor="middle" font-size="10" fill="#8b9cc0">{desc}</text>""")
    return "\n".join(parts)


adp_svg, adp_x0 = adapters()
out_svg = outputs()

# core layer: 4 columns
CW, CGAP, CX0, CY, CH = 232, 20, 105, 316, 74
CORE_X = [CX0 + i * (CW + CGAP) for i in range(4)]

SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 840" font-family="'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0b1020"/>
      <stop offset="1" stop-color="#121a31"/>
    </linearGradient>
    <marker id="ah" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto">
      <polygon points="0 0, 9 3.5, 0 7" fill="#5b9dff"/>
    </marker>
  </defs>

  <rect width="1200" height="840" fill="url(#bg)"/>
  <text x="600" y="42" text-anchor="middle" font-size="21" font-weight="800" fill="#f0f4ff">LitScan Architecture</text>
  <text x="600" y="64" text-anchor="middle" font-size="12" fill="#8b9cc0">config.yaml driven · retry &amp; rate-limit aware · proxy supported · open-access full-text download</text>

  <!-- Layer 1: clients -->
  {box(105, 92, 300, 66, "CLI", "litscan.py · search / history / download", "#141d36", "#2a3a5f")}
  {box(450, 92, 300, 66, "Web UI", "Jinja2 · / /history /sources /logs", "#141d36", "#2a3a5f")}
  {box(795, 92, 300, 66, "REST API + SSE", "20 endpoints · streaming progress", "#141d36", "#2a3a5f")}

  {arrow(255, 158, 480, 206)}
  {arrow(600, 158, 600, 206)}
  {arrow(945, 158, 720, 206)}

  <!-- Layer 2: server -->
  {box(330, 206, 540, 70, "FastAPI Server", "server/main.py · routes &amp; templates · Pydantic models", "#182647", "#34508c")}

  {arrow(600, 276, 600, 316)}

  <!-- Layer 3: core -->
  {box(CORE_X[0], CY, CW, CH, "Scanner", "core/scanner.py | orchestration", "#182647", "#34508c")}
  {box(CORE_X[1], CY, CW, CH, "Fetcher", "core/fetcher.py | retry x4 · proxy", "#182647", "#34508c")}
  {box(CORE_X[2], CY, CW, CH, "Full-text", "core/fulltext.py | resolve + download", "#1b2b52", "#3f6bc0")}
  {box(CORE_X[3], CY, CW, CH, "History / Log", "core/history.py · core/logger.py", "#182647", "#34508c")}

  {arrow(255, 390, 400, 448)}
  {arrow(600, 390, 600, 448)}
  {arrow(945, 390, 800, 448)}

  <!-- Layer 4: adapters -->
  <text x="{adp_x0:.0f}" y="440" font-size="12" font-weight="700" fill="#8b9cc0">ADAPTERS · core/adapters.py (7) · results carry doi / url for resolution</text>
  {adp_svg}

  <!-- Download pipeline -->
  {arrow(600, 560, 600, 596)}
  {box(105, 596, 990, 76, "Full-text PDF Download Pipeline",
       "resolve PDF link: arXiv / OpenReview direct · Semantic Scholar / Europe PMC / DOAJ (open access) "
       "| DOI fallback: Unpaywall → OpenAlex · download: resume + %PDF magic + 20KB validation",
       "#152a4d", "#3f6bc0")}

  {arrow(600, 672, 600, 736)}

  <!-- Outputs -->
  <text x="105" y="726" font-size="12" font-weight="700" fill="#8b9cc0">OUTPUTS · out/</text>
  {out_svg}

  <text x="1178" y="826" text-anchor="end" font-size="10" fill="#5a6a8f">generated by docs/scripts/generate_architecture.py</text>
</svg>
"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(SVG, encoding="utf-8")
print(f"written: {OUT}")
