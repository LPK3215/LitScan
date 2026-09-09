"""
LitScan 去重与排序模块

去重：DOI 主键匹配优先，无 DOI 时用「归一化标题 + 年份」兜底。
重复条目合并到信息更全的那条，并把所有命中来源记录到 sources 字段。

排序：relevance(保留原始顺序) / citations(引用数) / year(年份)
"""

import re
import logging
from typing import Optional

from .adapters import Article

logger = logging.getLogger("litscan.dedup")

# 每条记录的信息完整度权重（字段越多、值越全的条目优先保留）
_FIELDS = ("title", "year", "venue", "doi", "url", "citation_count", "abstract", "authors")


def _norm_doi(doi: Optional[str]) -> Optional[str]:
    """DOI 归一化：去前缀、小写、去尾部标点"""
    if not doi:
        return None
    s = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "https://dx.doi.org/"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s.rstrip(".") or None


def _norm_title(title: Optional[str]) -> Optional[str]:
    """标题归一化：小写、只留字母数字、去前后缀空格"""
    if not title:
        return None
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9一-鿿]+", " ", s)
    s = re.sub(r"^the\s+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _completeness(a: Article) -> int:
    """字段完整度打分"""
    score = 0
    for f in _FIELDS:
        v = getattr(a, f, None)
        if v not in (None, "", []):
            score += 2
    if a.abstract:
        score += min(len(a.abstract) // 100, 3)  # 摘要越长越完整
    return score


def _source_set(a: Article) -> set:
    """已有来源集合（含历史合并结果）"""
    s = set()
    raw = getattr(a, "sources", None) or a.source
    if raw:
        for part in str(raw).split(";"):
            part = part.strip()
            if part:
                s.add(part)
    return s


def _merge(kept: Article, dup: Article):
    """把 dup 的信息合并进 kept（只补缺失字段，取更大引用数，合并来源）"""
    changed = False
    for f in _FIELDS:
        if f in ("title", "source"):
            continue
        old = getattr(kept, f, None)
        new = getattr(dup, f, None)
        if old in (None, "", []) and new not in (None, "", []):
            setattr(kept, f, new)
            changed = True
    # 引用数取更大值
    if dup.citation_count is not None:
        if kept.citation_count is None or dup.citation_count > kept.citation_count:
            kept.citation_count = dup.citation_count
            changed = True
    # 合并来源
    merged = _source_set(kept) | _source_set(dup)
    if merged:
        kept.sources = "; ".join(sorted(merged))
    return changed


def deduplicate(articles: list[Article]) -> tuple[list[Article], dict]:
    """
    跨库去重，返回 (去重后列表, 统计信息)
    统计: {"removed": n, "by_doi": x, "by_title": y, "original": m}
    """
    by_doi: dict[str, Article] = {}
    by_title: dict[tuple, Article] = {}
    kept: list[Article] = []
    stats = {"original": len(articles), "removed": 0, "by_doi": 0, "by_title": 0}

    for a in articles:
        dkey = _norm_doi(a.doi)
        tkey = (_norm_title(a.title), a.year) if _norm_title(a.title) else None

        target = None
        reason = None
        if dkey and dkey in by_doi:
            target, reason = by_doi[dkey], "by_doi"
        elif tkey and tkey in by_title:
            target, reason = by_title[tkey], "by_title"

        if target is not None:
            # 保留信息更全的那条作为主条目
            if _completeness(a) > _completeness(target):
                _merge(a, target)
                if target in kept:
                    kept[kept.index(target)] = a
                for k, v in list(by_doi.items()):
                    if v is target:
                        by_doi[k] = a
                for k, v in list(by_title.items()):
                    if v is target:
                        by_title[k] = a
                if dkey:
                    by_doi[dkey] = a
                if tkey:
                    by_title[tkey] = a
            else:
                _merge(target, a)
            stats["removed"] += 1
            stats[reason] += 1
            continue

        kept.append(a)
        if dkey:
            by_doi[dkey] = a
        if tkey:
            by_title[tkey] = a

    # 未重复条目也补上 sources，保证字段一致
    for a in kept:
        if not getattr(a, "sources", None):
            a.sources = _source_set(a) and "; ".join(sorted(_source_set(a))) or a.source

    if stats["removed"]:
        logger.info(f"去重: {stats['original']} → {len(kept)} 篇 (DOI {stats['by_doi']} / 标题 {stats['by_title']})")
    return kept, stats


def sort_articles(articles: list[Article], by: str = "relevance", desc: bool = True) -> list[Article]:
    """
    排序
    - relevance: 保持检索相关度原始顺序
    - citations: 按引用数（缺失记 -1）
    - year: 按年份（缺失记 0）
    """
    if by == "citations":
        return sorted(articles, key=lambda a: (a.citation_count if a.citation_count is not None else -1), reverse=desc)
    if by == "year":
        return sorted(articles, key=lambda a: (a.year or 0), reverse=desc)
    return list(articles)
