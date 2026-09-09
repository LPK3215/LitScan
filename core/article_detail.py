"""
LitScan 文章详情回源模块
按 source + url/doi 回源拉取完整信息（全量摘要、作者、字段），供站内快速预览
带 TTL 内存缓存，避免重复请求
"""

import re
import time
import logging
from xml.etree import ElementTree as ET

from .fetcher import fetch

logger = logging.getLogger("litscan.detail")

CACHE_TTL = 1800  # 30 分钟
_cache: dict[str, tuple[float, dict]] = {}


class DetailNotSupported(Exception):
    """该源不支持详情回源"""


class DetailNotFound(Exception):
    """回源后未找到该文章"""


def _cache_get(key: str):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return dict(hit[1])
    return None


def _cache_put(key: str, data: dict):
    _cache[key] = (time.time(), dict(data))


def _strip_jats(s: str) -> str:
    """去掉 Crossref 摘要里的 JATS XML 标签"""
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def detail_arxiv(url: str, doi: str) -> dict:
    """arXiv: 通过 abs 链接提取 id，拉取完整 Atom 条目"""
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+)", url or "")
    arxiv_id = m.group(1) if m else None
    if not arxiv_id and doi and doi.startswith("10.48550/arXiv."):
        arxiv_id = doi.split("arXiv.", 1)[1]
    if not arxiv_id:
        raise DetailNotFound("无法从链接解析 arXiv ID")

    resp = fetch("https://export.arxiv.org/api/query",
                 params={"id_list": arxiv_id, "max_results": 1},
                 source_name="arxiv-detail")
    root = ET.fromstring(resp.content)
    ns = {"atom": "http://www.w3.org/2005/Atom",
          "arxiv": "http://arxiv.org/schemas/atom"}
    entry = root.find("atom:entry", ns)
    if entry is None:
        raise DetailNotFound(f"arXiv 未返回条目: {arxiv_id}")

    authors = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]
    categories = [c.get("term") for c in entry.findall("atom:category", ns) if c.get("term")]
    pdf_link = None
    for link in entry.findall("atom:link", ns):
        if link.get("title") == "pdf":
            pdf_link = link.get("href")

    return {
        "source": "arxiv",
        "identifier": arxiv_id,
        "title": (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " "),
        "abstract": (entry.findtext("atom:summary", "", ns) or "").strip(),
        "authors": [a for a in authors if a],
        "published": entry.findtext("atom:published", None, ns),
        "updated": entry.findtext("atom:updated", None, ns),
        "doi": entry.findtext("arxiv:doi", None, ns),
        "comment": entry.findtext("arxiv:comment", None, ns),
        "journal_ref": entry.findtext("arxiv:journal_ref", None, ns),
        "categories": categories,
        "pdf_url": pdf_link,
        "url": url or f"https://arxiv.org/abs/{arxiv_id}",
        "extra": {
            "primary_category": (entry.find("arxiv:primary_category", ns) or {}).get("term")
            if entry.find("arxiv:primary_category", ns) is not None else None,
        },
    }


def detail_crossref(url: str, doi: str) -> dict:
    """Crossref: 按 DOI 拉取完整 works 记录"""
    if not doi:
        raise DetailNotFound("Crossref 详情需要 DOI")
    resp = fetch(f"https://api.crossref.org/works/{doi}",
                 source_name="crossref-detail")
    item = resp.json().get("message", {})

    issued = item.get("issued", {}) or {}
    date_parts = issued.get("date-parts", [[]])
    year = date_parts[0][0] if date_parts and date_parts[0] else None
    container = item.get("container-title", []) or []
    authors = [
        f"{a.get('given', '')} {a.get('family', '')}".strip()
        for a in (item.get("author", []) or []) if a.get("family")
    ]

    return {
        "source": "crossref",
        "identifier": doi,
        "title": " ".join(item.get("title", []) or []),
        "abstract": _strip_jats(item.get("abstract", "")),
        "authors": authors,
        "year": year,
        "venue": container[0] if container else None,
        "publisher": item.get("publisher"),
        "type": item.get("type"),
        "volume": item.get("volume"),
        "issue": item.get("issue"),
        "pages": item.get("page"),
        "citation_count": item.get("is-referenced-by-count"),
        "references_count": item.get("references-count"),
        "url": item.get("URL") or url or f"https://doi.org/{doi}",
        "extra": {"license": (item.get("license") or [{}])[0].get("URL")},
    }


def detail_semanticscholar(url: str, doi: str) -> dict:
    """Semantic Scholar: 按 DOI 或 paperId 拉取完整记录"""
    fields = "title,abstract,year,venue,externalIds,citationCount,referenceCount,influentialCitationCount,authors,tldr,publicationTypes,openAccessPdf"
    paper_id = None
    if doi:
        paper_id = f"DOI:{doi}"
    elif url:
        m = re.search(r"semanticscholar\.org/paper/[^/]*?-?([0-9a-f]{40})", url)
        if m:
            paper_id = m.group(1)
    if not paper_id:
        raise DetailNotFound("Semantic Scholar 详情需要 DOI 或 paperId 链接")

    resp = fetch("https://api.semanticscholar.org/graph/v1/paper/" + paper_id,
                 params={"fields": fields}, source_name="semanticscholar-detail")
    item = resp.json()
    if not item or item.get("error"):
        raise DetailNotFound(str(item.get("error", "未找到论文")))

    ext_ids = item.get("externalIds", {}) or {}
    tldr = (item.get("tldr") or {}).get("text")
    return {
        "source": "semanticscholar",
        "identifier": paper_id,
        "title": item.get("title", ""),
        "abstract": item.get("abstract"),
        "authors": [a.get("name") for a in (item.get("authors", []) or []) if a.get("name")],
        "year": item.get("year"),
        "venue": item.get("venue"),
        "doi": ext_ids.get("DOI"),
        "citation_count": item.get("citationCount"),
        "references_count": item.get("referenceCount"),
        "url": url or (f"https://doi.org/{doi}" if doi else None),
        "pdf_url": (item.get("openAccessPdf") or {}).get("url"),
        "extra": {
            "tldr": tldr,
            "influential_citations": item.get("influentialCitationCount"),
            "publication_types": item.get("publicationTypes"),
        },
    }


def detail_openreview(url: str, doi: str) -> dict:
    """OpenReview: 从 forum 链接提取 note id，拉取完整评审记录"""
    m = re.search(r"[?&]id=([\w-]+)", url or "")
    if not m:
        raise DetailNotFound("无法从链接解析 OpenReview note ID")
    note_id = m.group(1)
    resp = fetch(f"https://api2.openreview.net/notes/{note_id}",
                 source_name="openreview-detail")
    note = resp.json().get("notes", [None])[0] if resp.json().get("notes") else None
    if not note:
        raise DetailNotFound(f"OpenReview 未找到 note: {note_id}")

    c = note.get("content", {}) or {}

    def val(field):
        v = c.get(field, {})
        return v.get("value") if isinstance(v, dict) else v

    keywords = val("keywords")
    return {
        "source": "openreview",
        "identifier": note_id,
        "title": val("title") or "",
        "abstract": val("abstract"),
        "authors": val("authors") if isinstance(val("authors"), list) else (
            [val("authors")] if val("authors") else []),
        "year": val("year"),
        "venue": val("venue"),
        "url": url or f"https://openreview.net/forum?id={note_id}",
        "pdf_url": f"https://openreview.net/pdf?id={note_id}" if val("pdf") is not None else None,
        "extra": {
            "keywords": keywords if isinstance(keywords, list) else None,
            "decision": val("decision") or val("recommendation"),
        },
    }


def detail_europepmc(url: str, doi: str) -> dict:
    """Europe PMC: 按 DOI 检索完整记录"""
    query = f'DOI:"{doi}"' if doi else None
    if not query:
        raise DetailNotFound("Europe PMC 详情需要 DOI")
    resp = fetch("https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                 params={"query": query, "format": "json", "pageSize": 1, "resultType": "core"},
                 source_name="europepmc-detail")
    results = resp.json().get("resultList", {}).get("result", [])
    if not results:
        raise DetailNotFound("Europe PMC 未找到该 DOI")
    item = results[0]
    return {
        "source": "europepmc",
        "identifier": item.get("id"),
        "title": item.get("title", ""),
        "abstract": item.get("abstractText"),
        "authors": [a for a in (item.get("authorList", {}).get("author", []) or [])
                    if isinstance(a, dict) and a.get("fullName")] or
                   ([a.strip() for a in (item.get("authorString") or "").split(",") if a.strip()]),
        "year": item.get("pubYear"),
        "venue": item.get("journalInfo", {}).get("journal", {}).get("title"),
        "doi": item.get("doi") or doi,
        "citation_count": item.get("citedByCount"),
        "url": url or f"https://europepmc.org/article/{item.get('source', 'MED')}/{item.get('id', '')}",
        "extra": {"pmid": item.get("pmid"), "isOpenAccess": item.get("isOpenAccess")},
    }


def detail_doaj(url: str, doi: str) -> dict:
    """DOAJ: 按 DOI 检索完整记录"""
    if not doi:
        raise DetailNotFound("DOAJ 详情需要 DOI")
    resp = fetch("https://doaj.org/api/search/articles/doi:" + doi,
                 params={"pageSize": 1}, source_name="doaj-detail")
    results = resp.json().get("results", [])
    if not results:
        raise DetailNotFound("DOAJ 未找到该 DOI")
    bib = results[0].get("bibjson", {})
    return {
        "source": "doaj",
        "identifier": results[0].get("id"),
        "title": bib.get("title", ""),
        "abstract": bib.get("abstract"),
        "authors": [a.get("name") for a in (bib.get("author") or []) if a.get("name")],
        "year": bib.get("year"),
        "venue": (bib.get("journal") or {}).get("title"),
        "doi": doi,
        "url": (bib.get("link") or [{}])[0].get("url") or url,
        "extra": {"keywords": bib.get("keywords")},
    }


# 源名 → 详情函数
DETAIL_FETCHERS = {
    "arxiv": detail_arxiv,
    "crossref": detail_crossref,
    "semanticscholar": detail_semanticscholar,
    "openreview": detail_openreview,
    "europepmc": detail_europepmc,
    "doaj": detail_doaj,
}


def get_detail(source: str, url: str = None, doi: str = None) -> dict:
    """
    统一详情入口：带缓存
    - 不支持回源的源 → DetailNotSupported
    - 未找到 → DetailNotFound
    """
    if source not in DETAIL_FETCHERS:
        raise DetailNotSupported(f"该源 ({source}) 暂不支持详情回源，请点击原文链接查看")

    key = f"{source}|{url or ''}|{doi or ''}"
    cached = _cache_get(key)
    if cached is not None:
        cached["cached"] = True
        return cached

    data = DETAIL_FETCHERS[source](url, doi)
    data["cached"] = False
    _cache_put(key, data)
    logger.info(f"详情回源成功: {source} {url or doi}")
    return data
