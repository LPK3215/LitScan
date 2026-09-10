# -*- coding: utf-8 -*-
"""
LitScan 全文 PDF 下载模块

把检索结果的元数据解析成「可直接下载的 PDF 直链」并落盘，补上检索闭环的最后一环。

设计来源（借鉴，非搬运）：参考脚本 download_papers.py 的三个好设计被吸收进来——
  1. 断点续传：已存在且体积达标的文件跳过，可中断后重跑
  2. 有效性校验：%PDF 魔数 + 最小体积，避免把错误页/空壳当成 PDF
  3. 单次批量上限：避免一次性打爆网络、触发对方限流
差异：本模块不自己手写 HTTP 重试，而是复用 core.fetcher.fetch，
与检索共用代理 / 超时 / 重试 / 限流退避策略，避免两套逻辑各自维护。

直链可获得性（决定「为什么有些能下、有些下不了」）：
  arxiv           直链可推导（abs/pdf 链接或 DOI 里的 arXiv ID）→ 稳定
  openreview      直链可推导（forum/pdf 链接里的 note id）     → 稳定
  semanticscholar 需查 API 的 openAccessPdf 字段，仅开放获取版有
  europepmc       仅开放获取(OA)子集，需查 API
  doaj            取决于期刊是否在书目记录里给出 PDF 链接
  crossref        源本身只有元数据/DOI → 转由下方「DOI 兜底」查找合法 OA 版本
  openaire        聚合索引，未接入单条记录接口，定位不到直链 → 不下载

两条正规通道（只取已公开标注为开放获取的链接，不绕过任何付费墙）：
  1. 源专属解析器：能直接给出 PDF 直链的（arXiv / OpenReview 等）
  2. DOI 兜底：Unpaywall → OpenAlex，按 DOI 查作者自存档 / 预印本等 OA 版本
付费墙后没有 OA 版本的（含知网这类不可程序化检索/下载的库）一律放弃，不做任何绕过尝试。
"""

import os
import re
import csv
import time
import logging
from urllib.parse import quote
from typing import Optional, Callable

from .fetcher import fetch, FetchError

logger = logging.getLogger("litscan.fulltext")

MIN_BYTES = 20 * 1024        # 低于此体积视为失败残留，重下
DEFAULT_DELAY = 1.5          # 相邻下载之间的礼貌间隔（秒）
DEFAULT_LIMIT = 20           # 单次批量上限
DOWNLOAD_UA = "LitScan/1.1 (mailto:lpk.research@outlook.com)"

# 通用 DOI 兜底渠道需要联系邮箱（进入免费「礼貌池」，避免被限流）
# 可用环境变量 LITSCAN_CONTACT_EMAIL 覆盖
CONTACT_EMAIL = os.environ.get("LITSCAN_CONTACT_EMAIL", "lpk.research@outlook.com")


# ── 异常 ──

class FulltextError(Exception):
    """全文下载相关错误基类"""


class FulltextNotFound(FulltextError):
    """无法为该条目定位 PDF 直链"""


class FulltextUnsupported(FulltextError):
    """该数据源不支持直接下载"""


# ── 各源支持情况（同时用于前端展示「为什么不能下」）──

SOURCE_SUPPORT = {
    "arxiv": {
        "supported": True,
        "mode": "direct",
        "note": "arXiv 官方 PDF 直链，免费无上限，最稳定",
    },
    "openreview": {
        "supported": True,
        "mode": "direct",
        "note": "OpenReview 官方 PDF 直链（开放评审，均可下载）",
    },
    "semanticscholar": {
        "supported": True,
        "mode": "api",
        "note": "仅当该论文存在开放获取版本时提供 openAccessPdf 直链",
    },
    "europepmc": {
        "supported": True,
        "mode": "api",
        "note": "仅开放获取(OA)子集可从 Europe PMC 取到 PDF",
    },
    "doaj": {
        "supported": True,
        "mode": "api",
        "note": "DOAJ 收录开放获取期刊，PDF 直链取决于期刊是否在书目记录中给出",
    },
    "crossref": {
        "supported": True,
        "mode": "oa_lookup",
        "note": "Crossref 本身只有元数据与 DOI，不提供全文；" 
                "会通过 Unpaywall / OpenAlex 查找该 DOI 的合法开放获取版本，找到才下",
    },
    "openaire": {
        "supported": False,
        "mode": None,
        "note": "OpenAIRE 是聚合索引，未接入其单条记录接口，定位不到可下载的 PDF 直链",
    },
}


def support_table() -> list[dict]:
    """供 API / 前端展示的源支持表"""
    return [{"source": name, **info} for name, info in SOURCE_SUPPORT.items()]


def is_supported(source: str) -> bool:
    info = SOURCE_SUPPORT.get(source)
    return bool(info and info["supported"])


# ── 标识符解析（纯函数，可离线测试）──

def extract_arxiv_id(url: str = None, doi: str = None) -> Optional[str]:
    """从 arXiv 链接或 DOI(10.48550/arXiv.*) 中提取 arXiv ID（含老式 cs/0701001）"""
    text = " ".join(x for x in (url, doi) if x)
    if not text:
        return None
    aid = None
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+)", text, re.I)
    if m:
        aid = m.group(1)
    else:
        m = re.search(r"10\.48550/arxiv\.([^\s?#]+)", text, re.I)
        if m:
            aid = m.group(1)
        elif re.search(r"[a-z\-]+(?:\.[A-Z]{2})?/\d{7}", text):
            m = re.search(r"([a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)", text)
            aid = m.group(1) if m else None
        else:
            m = re.search(r"\b(\d{4}\.\d{4,5}(?:v\d+)?)\b", text)
            aid = m.group(1) if m else None
    if not aid:
        return None
    aid = aid.strip().strip("/")
    aid = re.sub(r"\.pdf$", "", aid, flags=re.I)
    return aid or None


def extract_openreview_id(url: str = None) -> Optional[str]:
    """从 OpenReview forum/pdf 链接中提取 note id（?id=XXXX）"""
    if not url:
        return None
    m = re.search(r"[?&]id=([\w\-]+)", url)
    return m.group(1) if m else None


def _safe_filename(name: str, max_len: int = 120) -> str:
    """文件名清洗，避免路径穿越与非法字符"""
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", (name or "").strip())
    return s[:max_len].strip("_") or "paper.pdf"


def _has_traversal(name: str) -> bool:
    return (".." in name) or ("/" in name) or ("\\" in name)


# ── 各源解析器：返回 {identifier, pdf_url, filename} ──

def _resolve_arxiv(url: str = None, doi: str = None, proxy: str = None) -> dict:
    aid = extract_arxiv_id(url, doi)
    if not aid:
        raise FulltextNotFound("无法从链接/DOI 解析出 arXiv ID")
    return {
        "identifier": aid,
        "pdf_url": f"https://arxiv.org/pdf/{aid}",
        "filename": _safe_filename(f"{aid}.pdf"),
    }


def _resolve_openreview(url: str = None, doi: str = None, proxy: str = None) -> dict:
    nid = extract_openreview_id(url)
    if not nid:
        raise FulltextNotFound("无法从链接解析出 OpenReview note ID")
    return {
        "identifier": nid,
        "pdf_url": f"https://openreview.net/pdf?id={nid}",
        "filename": _safe_filename(f"openreview_{nid}.pdf"),
    }


def _resolve_semanticscholar(url: str = None, doi: str = None, proxy: str = None) -> dict:
    paper_id = None
    if doi:
        paper_id = f"DOI:{doi}"
    elif url:
        m = re.search(r"semanticscholar\.org/paper/[^/]*?-?([0-9a-f]{40})", url)
        if m:
            paper_id = m.group(1)
    if not paper_id:
        raise FulltextNotFound("Semantic Scholar 需要 DOI 或 paperId 链接")

    resp = fetch("https://api.semanticscholar.org/graph/v1/paper/" + paper_id,
                 params={"fields": "title,openAccessPdf"},
                 source_name="s2-fulltext", proxy=proxy,
                 timeout=30, max_retries=2, retry_delay=4)
    item = resp.json() or {}
    pdf_url = (item.get("openAccessPdf") or {}).get("url")
    if not pdf_url:
        raise FulltextNotFound("该论文在 Semantic Scholar 无开放获取 PDF（可能是订阅论文）")
    ident = re.sub(r"[^\w.\-]+", "_", paper_id)
    return {
        "identifier": paper_id,
        "pdf_url": pdf_url,
        "filename": _safe_filename(f"s2_{ident}.pdf"),
    }


def _resolve_europepmc(url: str = None, doi: str = None, proxy: str = None) -> dict:
    if not doi:
        raise FulltextNotFound("Europe PMC 需要 DOI 才能定位全文")
    resp = fetch("https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                 params={"query": f'DOI:"{doi}"', "format": "json",
                         "pageSize": 1, "resultType": "core"},
                 source_name="epmc-fulltext", proxy=proxy,
                 timeout=30, max_retries=2, retry_delay=4)
    results = resp.json().get("resultList", {}).get("result", [])
    if not results:
        raise FulltextNotFound("Europe PMC 未找到该 DOI")
    item = results[0]
    if str(item.get("isOpenAccess", "")).upper() != "Y":
        raise FulltextNotFound("该论文在 Europe PMC 非开放获取")

    pdf_url = None
    for fu in (item.get("fullTextUrlList", {}) or {}).get("fullTextUrl", []) or []:
        if isinstance(fu, dict) and (fu.get("documentStyle") or "").lower() == "pdf" and fu.get("url"):
            pdf_url = fu["url"]
            break
    if not pdf_url:
        pmcid = item.get("pmcid")
        if pmcid:
            pdf_url = f"https://europepmc.org/articles/{pmcid}?pdf=render"
    if not pdf_url:
        raise FulltextNotFound("Europe PMC 未提供 PDF 直链（可能只有 HTML 全文）")

    ident = item.get("pmcid") or item.get("pmid") or item.get("id") or doi
    ident = re.sub(r"[^\w.\-]+", "_", str(ident))
    return {
        "identifier": ident,
        "pdf_url": pdf_url,
        "filename": _safe_filename(f"epmc_{ident}.pdf"),
    }


def _resolve_doaj(url: str = None, doi: str = None, proxy: str = None) -> dict:
    if not doi:
        raise FulltextNotFound("DOAJ 需要 DOI 才能定位全文")
    resp = fetch("https://doaj.org/api/search/articles/doi:" + doi,
                 params={"pageSize": 1},
                 source_name="doaj-fulltext", proxy=proxy,
                 timeout=30, max_retries=2, retry_delay=4)
    results = resp.json().get("results", [])
    if not results:
        raise FulltextNotFound("DOAJ 未找到该 DOI")
    bib = results[0].get("bibjson", {}) or {}

    pdf_url = None
    for link in bib.get("link", []) or []:
        if not isinstance(link, dict):
            continue
        u = link.get("url") or ""
        if not u:
            continue
        ctype = str(link.get("content_type") or link.get("content-type") or "").lower()
        if "pdf" in ctype or u.lower().split("?")[0].endswith(".pdf"):
            pdf_url = u
            break
    if not pdf_url:
        raise FulltextNotFound("该期刊未在 DOAJ 记录中提供 PDF 直链（可能只有 HTML 全文）")

    ident = results[0].get("id") or doi
    ident = re.sub(r"[^\w.\-]+", "_", str(ident))
    return {
        "identifier": ident,
        "pdf_url": pdf_url,
        "filename": _safe_filename(f"doaj_{ident}.pdf"),
    }


SOURCE_RESOLVERS = {
    "arxiv": _resolve_arxiv,
    "openreview": _resolve_openreview,
    "semanticscholar": _resolve_semanticscholar,
    "europepmc": _resolve_europepmc,
    "doaj": _resolve_doaj,
}

# 兼容旧引用
RESOLVERS = SOURCE_RESOLVERS


# ── 通用 DOI 兜底：对任何有 DOI 的条目查找「合法开放获取版本」──
# 这是解决「付费期刊但作者自存档/预印本可公开获取」的正规通道，
# 不绕过任何付费墙：只取第三方索引里已公开标注为 OA 的链接。

def _pdf_from_unpaywall(doi: str, proxy: str = None) -> Optional[str]:
    """Unpaywall: 只取明确标注为 PDF 的字段 url_for_pdf"""
    resp = fetch(f"https://api.unpaywall.org/v2/{quote(doi, safe='')}",
                 params={"email": CONTACT_EMAIL},
                 source_name="unpaywall", proxy=proxy,
                 timeout=30, max_retries=2, retry_delay=4)
    data = resp.json() or {}
    best = data.get("best_oa_location") or {}
    if best.get("url_for_pdf"):
        return best["url_for_pdf"]
    for loc in data.get("oa_locations") or []:
        if isinstance(loc, dict) and loc.get("url_for_pdf"):
            return loc["url_for_pdf"]
    return None


def _pdf_from_openalex(doi: str, proxy: str = None) -> Optional[str]:
    """OpenAlex: 只取 pdf_url（避免落到可能需登录的 landing page）"""
    resp = fetch(f"https://api.openalex.org/works/doi:{quote(doi, safe='')}",
                 params={"mailto": CONTACT_EMAIL},
                 source_name="openalex", proxy=proxy,
                 timeout=30, max_retries=2, retry_delay=4)
    data = resp.json() or {}
    best = data.get("best_oa_location") or {}
    if best.get("pdf_url"):
        return best["pdf_url"]
    for loc in data.get("locations") or []:
        if isinstance(loc, dict) and loc.get("pdf_url"):
            return loc["pdf_url"]
    return None


def _resolve_via_doi(doi: str, proxy: str = None) -> Optional[dict]:
    """依次尝试 DOI 兜底渠道，返回首个可用的 {identifier, pdf_url, filename, via}"""
    for name, fn in (("unpaywall", _pdf_from_unpaywall), ("openalex", _pdf_from_openalex)):
        try:
            pdf_url = fn(doi, proxy)
        except FetchError:
            logger.info(f"[{name}] {doi} 查询失败")
            continue
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[{name}] {doi} 查询异常: {e}")
            continue
        if pdf_url:
            ident = re.sub(r"[^\w.\-]+", "_", doi)
            return {
                "identifier": doi,
                "pdf_url": pdf_url,
                "filename": _safe_filename(f"doi_{ident}.pdf"),
                "via": name,
            }
    return None


def _try_source_resolver(source: str, url: str, doi: str, proxy: str, reasons: list):
    """调用某源的专属解析器；成功返回结果，失败把原因追加到 reasons"""
    fn = SOURCE_RESOLVERS.get(source)
    if not fn:
        return None
    try:
        resolved = fn(url, doi, proxy)
        resolved.update({"ok": True, "source": source, "via": source})
        return resolved
    except FulltextUnsupported as e:
        reasons.append(str(e))
    except FulltextNotFound as e:
        reasons.append(str(e))
    except FetchError as e:
        reasons.append(f"[{source}] 回源失败")
    except Exception as e:  # noqa: BLE001  单条解析失败不应中断批量任务
        logger.warning(f"[{source}] PDF 直链解析异常: {e}")
        reasons.append(f"[{source}] 解析失败: {str(e)[:100]}")
    return None


def resolve_pdf_url(source: str, url: str = None, doi: str = None, proxy: str = None) -> dict:
    """
    统一解析入口，永不抛异常。
    顺序：该源专属解析器 → 通用 DOI 兜底（Unpaywall / OpenAlex，仅取合法 OA 版本）。
    返回 {"ok": True, "source", "identifier", "pdf_url", "filename", "via"}
      或 {"ok": False, "source", "reason"}
    """
    info = SOURCE_SUPPORT.get(source)
    if info is None:
        return {"ok": False, "source": source, "reason": f"未知数据源: {source}"}

    reasons: list[str] = []
    resolved = _try_source_resolver(source, url, doi, proxy, reasons)
    if resolved:
        return resolved

    if doi:
        fallback = _resolve_via_doi(doi, proxy)
        if fallback:
            fallback.update({"ok": True, "source": source})
            return fallback
        reasons.append("Unpaywall / OpenAlex 未找到该 DOI 的合法开放获取版本")

    if not reasons:
        reasons.append(info["note"])
    return {"ok": False, "source": source, "reason": "；".join(reasons)}


# ── 下载 ──

def _existing_ok(path: str, min_bytes: int = MIN_BYTES) -> bool:
    """已存在且体积达标的文件 → 视为已下载（断点续传的跳过条件）"""
    try:
        return os.path.exists(path) and os.path.getsize(path) >= min_bytes
    except OSError:
        return False


def is_valid_pdf(data: bytes, min_bytes: int = MIN_BYTES) -> bool:
    """有效性校验：PDF 魔数 + 最小体积（防止把错误页/空壳当 PDF）"""
    return bool(data) and len(data) >= min_bytes and data.startswith(b"%PDF")


def download_pdf(pdf_url: str, dest_path: str, *,
                 min_bytes: int = MIN_BYTES, proxy: str = None,
                 timeout: int = 120, attempts: int = 3,
                 retry_delay: float = 3.0) -> dict:
    """
    下载单个 PDF 到 dest_path（先写 .part 再原子替换，避免半成品）。
    返回 {"status": "downloaded"|"failed", "bytes"?, "reason"?}
    """
    last_reason = "未知错误"
    for attempt in range(1, attempts + 1):
        try:
            resp = fetch(pdf_url, headers={"Accept": "application/pdf,*/*"},
                         timeout=timeout, max_retries=1, retry_delay=retry_delay,
                         user_agent=DOWNLOAD_UA, proxy=proxy, source_name="fulltext")
            data = resp.content
        except FetchError as e:
            last_reason = f"下载失败: {e}"
            if attempt < attempts:
                time.sleep(retry_delay * attempt)
                continue
            return {"status": "failed", "reason": last_reason}

        if not is_valid_pdf(data, min_bytes):
            last_reason = "响应不是有效 PDF（可能被拦截、链接失效或非开放获取）"
            if attempt < attempts:
                time.sleep(retry_delay * attempt)
                continue
            return {"status": "failed", "reason": last_reason}

        try:
            tmp_path = dest_path + ".part"
            with open(tmp_path, "wb") as f:
                f.write(data)
            os.replace(tmp_path, dest_path)
        except OSError as e:
            return {"status": "failed", "reason": f"写入失败: {e}"}
        return {"status": "downloaded", "bytes": len(data)}

    return {"status": "failed", "reason": last_reason}


def _candidate_sources(article: dict) -> list[str]:
    """合并条目可能命中多个源（sources 字段），按顺序去重后作为候选"""
    out = []
    for s in [article.get("source")] + str(article.get("sources") or "").split(";"):
        s = (s or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def download_article(article: dict, pdf_dir: str, *,
                     proxy: str = None, overwrite: bool = False,
                     min_bytes: int = MIN_BYTES, timeout: int = 120,
                     attempts: int = 3) -> dict:
    """
    下载单篇文献的开放全文 PDF。
    返回 {title, source, identifier, status, path, size, pdf_url, via, reason}
    status: downloaded | skipped | failed | unsupported
    """
    if hasattr(article, "to_dict"):
        article = article.to_dict()

    result = {
        "title": article.get("title") or "",
        "source": article.get("source") or "",
        "identifier": None,
        "status": "unsupported",
        "path": None,
        "size": 0,
        "pdf_url": None,
        "via": None,
        "reason": "",
    }

    candidates = _candidate_sources(article)
    if not candidates:
        result["reason"] = "条目缺少来源信息"
        return result

    url = article.get("url")
    doi = article.get("doi")
    reasons: list[str] = []

    # 1) 先试各候选源的专属解析器（直链最稳，优先）
    resolved = None
    for src in candidates:
        resolved = _try_source_resolver(src, url, doi, proxy, reasons)
        if resolved:
            break

    # 2) 再试通用 DOI 兜底（Unpaywall / OpenAlex，只取合法开放获取版本）
    if resolved is None and doi:
        resolved = _resolve_via_doi(doi, proxy)
        if resolved:
            resolved["source"] = candidates[0]
        else:
            reasons.append("Unpaywall / OpenAlex 未找到该 DOI 的合法开放获取版本")

    if resolved is None:
        uniq = list(dict.fromkeys(r for r in reasons if r))
        result["reason"] = "；".join(uniq) or "无法定位 PDF 直链"
        return result

    filename = resolved["filename"]
    if _has_traversal(filename):
        filename = _safe_filename(os.path.basename(filename))
    dest = os.path.join(pdf_dir, filename)

    result["source"] = resolved["source"]
    result["identifier"] = resolved["identifier"]
    result["pdf_url"] = resolved["pdf_url"]
    result["via"] = resolved.get("via")
    result["path"] = dest

    if not overwrite and _existing_ok(dest, min_bytes):
        result["status"] = "skipped"
        result["size"] = os.path.getsize(dest)
        result["reason"] = "本地已存在，跳过"
        return result

    if not overwrite and os.path.exists(dest):
        # 体积不足的残留，重下
        logger.info(f"重下失败残留: {dest}")

    os.makedirs(pdf_dir, exist_ok=True)
    dl = download_pdf(resolved["pdf_url"], dest, min_bytes=min_bytes,
                      proxy=proxy, timeout=timeout, attempts=attempts)
    result["status"] = dl["status"]
    if dl["status"] == "downloaded":
        result["size"] = dl.get("bytes", 0)
        result["reason"] = ""
    else:
        result["path"] = None
        result["reason"] = dl.get("reason", "下载失败")
    return result


def download_articles(articles: list, pdf_dir: str, *,
                      limit: int = None, proxy: str = None,
                      overwrite: bool = False, delay: float = DEFAULT_DELAY,
                      min_bytes: int = MIN_BYTES, timeout: int = 120,
                      attempts: int = 3,
                      on_event: Optional[Callable] = None) -> dict:
    """
    批量下载。articles 为 dict 列表（或含 to_dict 的对象）。
    单次上限 limit（默认不限制，由调用方给），相邻网络请求间 delay 秒礼貌间隔。
    返回 {"total","downloaded","skipped","failed","unsupported","dir","results":[...]}
    """
    os.makedirs(pdf_dir, exist_ok=True)
    todo = list(articles or [])
    if limit and limit > 0:
        todo = todo[:limit]

    summary = {
        "total": len(todo),
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
        "unsupported": 0,
        "dir": os.path.abspath(pdf_dir),
        "results": [],
    }

    for idx, article in enumerate(todo, 1):
        res = download_article(article, pdf_dir, proxy=proxy, overwrite=overwrite,
                               min_bytes=min_bytes, timeout=timeout, attempts=attempts)
        summary[res["status"]] = summary.get(res["status"], 0) + 1
        summary["results"].append(res)
        if on_event:
            try:
                on_event(idx, len(todo), res)
            except Exception:  # noqa: BLE001  回调异常不影响下载
                logger.debug("on_event 回调异常", exc_info=True)
        # 只有真正发起网络请求的条目之间才需要间隔
        if delay and res["status"] in ("downloaded", "failed") and idx < len(todo):
            time.sleep(delay)

    logger.info(
        f"PDF 下载完成: 成功 {summary['downloaded']} / 跳过 {summary['skipped']} / "
        f"失败 {summary['failed']} / 不支持 {summary['unsupported']}"
    )
    return summary


# ── 从 CSV 读取待下载列表（对齐参考脚本的「CSV → 批量续传」用法）──

def load_articles_from_csv(path: str) -> list[dict]:
    """读取 LitScan 导出的 articles.csv（或任何含 source/url/doi 列的 CSV）"""
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not any(row.get(k) for k in ("title", "url", "doi", "source")):
                continue
            rows.append({k: (v if v not in ("", None) else None) for k, v in row.items()})
    return rows
