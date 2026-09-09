"""
LitScan 输出模块
- 原始响应存档
- 合并 CSV
- 检索日志
"""

import csv
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .adapters import Article

logger = logging.getLogger("litscan.output")


def ensure_dir(path: str) -> str:
    """确保目录存在，返回路径"""
    os.makedirs(path, exist_ok=True)
    return path


def save_raw(raw_content: bytes, source_name: str, output_dir: str) -> str:
    """保存原始响应到 out/raw/"""
    raw_dir = ensure_dir(os.path.join(output_dir, "raw"))
    ext = "xml" if source_name == "arxiv" else "json"
    filepath = os.path.join(raw_dir, f"{source_name}.{ext}")
    with open(filepath, "wb") as f:
        f.write(raw_content)
    logger.info(f"原始响应已保存: {filepath}")
    return filepath


def save_csv(articles: list[Article], output_dir: str, filename: str = "articles.csv") -> str:
    """保存标准化 CSV"""
    ensure_dir(output_dir)
    filepath = os.path.join(output_dir, filename)

    fieldnames = ["title", "source", "year", "venue", "doi", "url", "citation_count", "authors", "abstract"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for a in articles:
            writer.writerow(a.to_dict())

    logger.info(f"CSV 已保存: {filepath} ({len(articles)} 篇)")
    return filepath


def append_log(
    log_path: str,
    keywords: str,
    sources: list[str],
    results: dict[str, int],
    total: int,
):
    """追加检索日志"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)

    file_exists = os.path.exists(log_path)
    with open(log_path, "a", encoding="utf-8") as f:
        if not file_exists:
            f.write("# LitScan 检索日志\n\n")
            f.write("| 日期 | 关键词 | 检索源 | 各源命中 | 总命中 |\n")
            f.write("|------|--------|--------|----------|--------|\n")

        sources_str = ", ".join(sources)
        results_str = " + ".join(f"{k}={v}" for k, v in results.items())
        f.write(f"| {now} | {keywords} | {sources_str} | {results_str} | {total} |\n")

    logger.info(f"日志已追加: {log_path}")
