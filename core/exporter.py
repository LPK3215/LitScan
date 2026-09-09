"""
LitScan 导出模块
将文章列表导出为 Markdown 收藏 / BibTeX / CSV / 纯文本
纯函数，不发网络请求，便于测试
"""

import csv
import io
import os
import re
from datetime import datetime
from typing import Optional

logger_name = "litscan.exporter"

# CSV 字段与 output.py 保持一致
CSV_FIELDS = ["title", "source", "sources", "year", "venue", "doi", "url", "citation_count", "authors", "abstract"]


def _s(value) -> str:
    """None 安全转字符串"""
    return str(value).strip() if value is not None else ""


def _safe_filename(keywords: str, max_len: int = 40) -> str:
    """关键词 → 安全文件名片段"""
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", keywords.strip())
    return s[:max_len].strip("_") or "export"


def to_markdown(articles: list[dict], keywords: str = "") -> str:
    """导出为 Markdown 文献收藏（标题/元信息/链接/摘要）"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = ["# LitScan 文献收藏", ""]
    header = f"> 导出时间: {now} · 共 {len(articles)} 篇"
    if keywords:
        header = f"> 关键词: {keywords} · " + header
    lines += [header, ""]

    for i, a in enumerate(articles, 1):
        title = _s(a.get("title")) or "(无标题)"
        lines.append(f"## {i}. {title}")
        lines.append("")

        # 元信息行
        meta = []
        if a.get("source"):
            meta.append(f"`{a['source']}`")
        if a.get("year"):
            meta.append(str(a["year"]))
        if a.get("venue"):
            meta.append(_s(a["venue"]))
        if a.get("citation_count") is not None:
            meta.append(f"{a['citation_count']} 引用")
        if meta:
            lines.append(" · ".join(meta))
            lines.append("")

        if a.get("authors"):
            lines.append(f"**作者**: {_s(a['authors'])}")
            lines.append("")

        # 链接
        links = []
        if a.get("url"):
            links.append(f"[原文]({_s(a['url'])})")
        if a.get("doi"):
            links.append(f"[DOI](https://doi.org/{_s(a['doi'])})")
        if links:
            lines.append(" | ".join(links))
            lines.append("")

        if a.get("abstract"):
            lines.append(f"> {_s(a['abstract'])}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _bibtex_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("&", "\\&")


def _bibtex_key(a: dict, used: set) -> str:
    """生成唯一 citation key: 姓+年+标题首词"""
    authors = _s(a.get("authors"))
    first_lastname = "unknown"
    if authors:
        first = authors.split(";")[0].split(",")[0].strip()
        parts = first.split()
        first_lastname = parts[-1] if parts else first
    year = _s(a.get("year")) or "nd"
    title_word = re.sub(r"[^a-zA-Z]", "", (_s(a.get("title")).split() or ["x"])[0]).lower() or "x"
    base = f"{first_lastname}{year}{title_word}".lower()
    base = re.sub(r"[^a-z0-9]", "", base) or "entry"
    key, n = base, 2
    while key in used:
        key = f"{base}{n}"
        n += 1
    used.add(key)
    return key


def to_bibtex(articles: list[dict]) -> str:
    """导出为 BibTeX（有 venue 用 @article，否则 @misc）"""
    used: set = set()
    entries = []
    for a in articles:
        key = _bibtex_key(a, used)
        entry_type = "article" if _s(a.get("venue")) else "misc"
        fields = [
            ("title", _s(a.get("title"))),
            ("author", re.sub(r";\s*", " and ", _s(a.get("authors")))),
            ("year", _s(a.get("year"))),
            ("journal", _s(a.get("venue"))),
            ("doi", _s(a.get("doi"))),
            ("url", _s(a.get("url"))),
        ]
        lines = [f"@{entry_type}{{{key},"]
        for name, value in fields:
            if value:
                lines.append(f"  {name} = {{{_bibtex_escape(value)}}},")
        lines.append("}")
        entries.append("\n".join(lines))
    return "\n\n".join(entries) + ("\n" if entries else "")


def to_ris(articles: list[dict]) -> str:
    """
    导出为 RIS (EndNote / Zotero / Mendeley 通用) 格式
    有 venue 用 JOUR，否则用 GEN
    """
    blocks = []
    for a in articles:
        lines = [f"TY  - {'JOUR' if _s(a.get('venue')) else 'GEN'}"]
        if a.get("title"):
            lines.append(f"TI  - {_s(a['title'])}")
        for author in [x.strip() for x in _s(a.get("authors")).split(";") if x.strip()]:
            lines.append(f"AU  - {author}")
        if a.get("year"):
            lines.append(f"PY  - {a['year']}")
        if a.get("venue"):
            lines.append(f"JO  - {_s(a['venue'])}")
        if a.get("doi"):
            lines.append(f"DO  - {_s(a['doi'])}")
        if a.get("url"):
            lines.append(f"UR  - {_s(a['url'])}")
        if a.get("abstract"):
            lines.append(f"AB  - {_s(a['abstract'])}")
        lines.append("ER  - ")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def to_text(articles: list[dict]) -> str:
    """导出为纯文本列表（适合直接复制到笔记）"""
    lines = []
    for a in articles:
        parts = []
        title = _s(a.get("title")) or "(无标题)"
        meta = []
        if a.get("year"):
            meta.append(str(a["year"]))
        if a.get("venue"):
            meta.append(_s(a["venue"]))
        prefix = f" ({', '.join(meta)})" if meta else ""
        link = _s(a.get("url")) or (f"https://doi.org/{a['doi']}" if a.get("doi") else "")
        suffix = f" — {link}" if link else ""
        lines.append(f"- {title}{prefix}{suffix}")
    return "\n".join(lines) + ("\n" if lines else "")


def to_csv_bytes(articles: list[dict]) -> bytes:
    """导出为 CSV 字节流（utf-8-sig，Excel 友好）"""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for a in articles:
        writer.writerow({k: a.get(k) for k in CSV_FIELDS})
    return buf.getvalue().encode("utf-8-sig")


# 各格式对应的文件扩展名与 MIME
FORMAT_META = {
    "markdown": {"ext": "md", "mime": "text/markdown; charset=utf-8"},
    "bibtex": {"ext": "bib", "mime": "application/x-bibtex; charset=utf-8"},
    "endnote": {"ext": "ris", "mime": "application/x-research-info-systems; charset=utf-8"},
    "csv": {"ext": "csv", "mime": "text/csv; charset=utf-8"},
    "text": {"ext": "txt", "mime": "text/plain; charset=utf-8"},
}


def build_export(format_name: str, articles: list[dict], keywords: str = "") -> bytes:
    """按格式生成导出内容（统一入口，返回字节流）"""
    if format_name == "csv":
        return to_csv_bytes(articles)
    if format_name == "bibtex":
        text = to_bibtex(articles)
    elif format_name == "endnote":
        text = to_ris(articles)
    elif format_name == "text":
        text = to_text(articles)
    elif format_name == "markdown":
        text = to_markdown(articles, keywords)
    else:
        raise ValueError(f"不支持的导出格式: {format_name}")
    return text.encode("utf-8")


def save_export(content: bytes, format_name: str, export_dir: str, keywords: str = "") -> str:
    """保存导出文件到 out/exports/，返回文件路径"""
    meta = FORMAT_META.get(format_name, {"ext": "txt"})
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{ts}_{_safe_filename(keywords)}.{meta['ext']}"
    os.makedirs(export_dir, exist_ok=True)
    filepath = os.path.join(export_dir, name)
    with open(filepath, "wb") as f:
        f.write(content)
    return filepath
