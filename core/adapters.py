"""
LitScan 各库适配器
每个库一个适配器：build_url + parse
"""

import logging
from typing import Optional
from dataclasses import dataclass, field, asdict

import requests
from xml.etree import ElementTree as ET

from .fetcher import fetch

logger = logging.getLogger("litscan.adapters")


@dataclass
class Article:
    title: str
    source: str
    year: Optional[int] = None
    venue: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    citation_count: Optional[int] = None
    abstract: Optional[str] = None
    authors: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def arxiv_adapter(keywords: str, limit: int = 30, **kwargs) -> list[Article]:
    query = " AND ".join(f'abs:{w}' for w in keywords.split())
    params = {"search_query": query, "max_results": limit, "sortBy": "relevance"}
    resp = fetch("https://export.arxiv.org/api/query", params=params, **kwargs)
    articles = []
    root = ET.fromstring(resp.content)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("atom:entry", ns):
        title = entry.findtext("atom:title", "", ns).strip().replace("\n", " ")
        url = entry.find("atom:id", ns).text if entry.find("atom:id", ns) is not None else None
        summary = entry.findtext("atom:summary", "", ns).strip().replace("\n", " ")[:500]
        author_names = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]
        authors = "; ".join(author_names) if author_names else None
        published = entry.findtext("atom:published", "", ns)
        year = int(published[:4]) if published and len(published) >= 4 else None
        articles.append(Article(title=title, source="arxiv", year=year, url=url, abstract=summary, authors=authors))
    logger.info(f"arxiv: {len(articles)} 篇")
    return articles


def semanticscholar_adapter(keywords: str, limit: int = 30, year_from: Optional[int] = None, **kwargs) -> list[Article]:
    params = {"query": keywords, "limit": limit, "fields": "title,year,venue,externalIds,citationCount,abstract,authors"}
    if year_from:
        params["year"] = f"{year_from}-"
    resp = fetch("https://api.semanticscholar.org/graph/v1/paper/search", params=params, **kwargs)
    articles = []
    for item in resp.json().get("data", []):
        ext_ids = item.get("externalIds", {}) or {}
        authors_list = item.get("authors", []) or []
        authors = "; ".join(a.get("name", "") for a in authors_list if a.get("name")) or None
        articles.append(Article(
            title=item.get("title", ""),
            source="semanticscholar",
            year=item.get("year"),
            venue=item.get("venue"),
            doi=ext_ids.get("DOI"),
            citation_count=item.get("citationCount"),
            abstract=(item.get("abstract") or "")[:500],
            authors=authors,
        ))
    logger.info(f"semanticscholar: {len(articles)} 篇")
    return articles


def crossref_adapter(keywords: str, limit: int = 30, year_from: Optional[int] = None, **kwargs) -> list[Article]:
    params = {"query": keywords, "rows": limit, "select": "title,DOI,issued,container-title,is-referenced-by-count,author"}
    if year_from:
        params["filter"] = f"from-pub-date:{year_from}"
    resp = fetch("https://api.crossref.org/works", params=params, **kwargs)
    articles = []
    for item in resp.json().get("message", {}).get("items", []):
        issued = item.get("issued", {}) or {}
        date_parts = issued.get("date-parts", [[]])
        year = date_parts[0][0] if date_parts and date_parts[0] else None
        container = item.get("container-title", [])
        venue = container[0] if container else None
        authors_list = item.get("author", []) or []
        authors = "; ".join(f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors_list if a.get("family")) or None
        title = " ".join(item.get("title", [])) if isinstance(item.get("title"), list) else (item.get("title") or "")
        articles.append(Article(
            title=title, source="crossref", year=year, venue=venue,
            doi=item.get("DOI"), citation_count=item.get("is-referenced-by-count"),
            authors=authors,
        ))
    logger.info(f"crossref: {len(articles)} 篇")
    return articles


def openreview_adapter(keywords: str, limit: int = 30, **kwargs) -> list[Article]:
    params = {"term": keywords, "limit": limit, "content": "all"}
    resp = fetch("https://api2.openreview.net/notes/search", params=params, **kwargs)
    articles = []
    for note in resp.json().get("notes", []):
        c = note.get("content", {}) or {}
        t = c.get("title", {}) or {}
        title = t.get("value", "") if isinstance(t, dict) else ""
        v = c.get("venue", {}) or {}
        venue = v.get("value", "") if isinstance(v, dict) else ""
        year = c.get("year", {}).get("value") if isinstance(c.get("year"), dict) else None
        abstract = c.get("abstract", {}).get("value", "")[:500] if isinstance(c.get("abstract"), dict) else ""
        articles.append(Article(title=title, source="openreview", year=year, venue=venue, abstract=abstract))
    logger.info(f"openreview: {len(articles)} 篇")
    return articles


def openaire_adapter(keywords: str, limit: int = 30, **kwargs) -> list[Article]:
    params = {"keywords": keywords, "size": limit, "format": "json"}
    resp = fetch("https://api.openaire.eu/search/publications", params=params, **kwargs)
    articles = []
    data = resp.json()
    results = data.get("response", {}).get("results", {})
    # result 可能是 dict（单条）或 list（多条）
    result_list = results.get("result", [])
    if isinstance(result_list, dict):
        result_list = [result_list]
    for item in result_list:
        metadata = item.get("metadata", {}) or {}
        entity = metadata.get("oaf:entity", {}) or {}
        result_data = entity.get("oaf:result", {}) or {}
        # title
        title_obj = result_data.get("title", {})
        title = title_obj.get("$", "") if isinstance(title_obj, dict) else ""
        # date
        date_obj = result_data.get("dateofacceptance", {})
        date_str = date_obj.get("$", "") if isinstance(date_obj, dict) else ""
        year = int(date_str[:4]) if date_str and len(date_str) >= 4 and date_str[:4].isdigit() else None
        articles.append(Article(title=title, source="openaire", year=year))
    logger.info(f"openaire: {len(articles)} 篇")
    return articles


def doaj_adapter(keywords: str, limit: int = 30, **kwargs) -> list[Article]:
    resp = fetch(f"https://doaj.org/api/search/articles/{keywords}", params={"pageSize": limit}, **kwargs)
    articles = []
    for r in resp.json().get("results", []):
        bib = r.get("bibjson", {}) or {}
        year = bib.get("year")
        journal = bib.get("journal", {}) or {}
        venue = journal.get("title") if isinstance(journal, dict) else None
        articles.append(Article(
            title=bib.get("title", ""), source="doaj",
            year=int(year) if year and str(year).isdigit() else None,
            venue=venue,
        ))
    logger.info(f"doaj: {len(articles)} 篇")
    return articles


def europepmc_adapter(keywords: str, limit: int = 30, **kwargs) -> list[Article]:
    params = {"query": keywords, "format": "json", "pageSize": limit}
    resp = fetch("https://www.ebi.ac.uk/europepmc/webservices/rest/search", params=params, **kwargs)
    articles = []
    for r in resp.json().get("resultList", {}).get("result", []) or []:
        journal_info = r.get("journalInfo", {}) or {}
        journal = journal_info.get("journal", {}) or {}
        articles.append(Article(
            title=r.get("title", ""), source="europepmc",
            year=int(r["pubYear"]) if r.get("pubYear") and r["pubYear"].isdigit() else None,
            venue=journal.get("title"),
            doi=r.get("doi"),
        ))
    logger.info(f"europepmc: {len(articles)} 篇")
    return articles


ADAPTERS = {
    "arxiv": arxiv_adapter,
    "semanticscholar": semanticscholar_adapter,
    "crossref": crossref_adapter,
    "openreview": openreview_adapter,
    "openaire": openaire_adapter,
    "doaj": doaj_adapter,
    "europepmc": europepmc_adapter,
}
