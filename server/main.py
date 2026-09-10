"""
LitScan FastAPI 后端

页面路由:
  GET  /                    首页 (检索页面)
  GET  /history             历史记录页面
  GET  /sources             数据源页面
  GET  /logs                操作日志页面

API 接口 (前缀 /api/):
  GET  /api/sources             列出可用检索源
  POST /api/search              多库检索
  GET  /api/search/stream       SSE 实时检索进度 (含限流/重试事件)
  POST /api/search/{source}     单库检索
  GET  /api/articles            最近一次检索结果
  POST /api/export              多选导出 (markdown/bibtex/csv/text)
  GET  /api/download/supported  各源全文 PDF 直下支持情况
  POST /api/download            批量下载开放全文 PDF (断点续传)
  GET  /api/article/detail      文章详情回源 (站内快速预览)
  GET  /api/history             搜索历史
  GET  /api/history/{record_id} 历史记录详情
  POST /api/history/search      搜索历史记录
  POST /api/history/retry/{id}  从历史重新检索
  DELETE /api/history/{id}      删除历史记录
  DELETE /api/history           清空历史
  GET  /api/logs                操作日志列表
  DELETE /api/logs               清空操作日志
  GET  /api/logs/stats           日志统计
"""

import logging
import json
import asyncio
import queue
from typing import Optional, AsyncGenerator
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import Literal

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.scanner import Scanner
from core.adapters import ADAPTERS, Article
from core.history import SearchHistory, SearchRecord
from core.fetcher import FetchError, RateLimitInfo
from core.logger import OperationLogger, LogLevel
from core.exporter import build_export, save_export, FORMAT_META
from core.dedup import deduplicate, sort_articles
from core.article_detail import get_detail, DetailNotSupported, DetailNotFound
from core.fulltext import download_articles, support_table

logger = logging.getLogger("litscan.server")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(
    title="LitScan",
    description="学术文献多库检索工具",
    version="1.1.0",
)

# 静态文件 + 模板
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# ── 全局状态 ──
_last_results: list[dict] = []
scanner = Scanner(config={
    "sources": [],
    "query": {},
    "output": {},
    "request": {},
    "history": {"enabled": True, "file": os.path.join(BASE_DIR, "out", "history.json")},
})

# 操作日志
op_logger = OperationLogger()


# ── 请求/响应模型 ──

class SearchRequest(BaseModel):
    keywords: str = Field(..., min_length=1, examples=["LLM agent evaluation"])
    sources: list[str] = Field(..., min_length=1, description="指定检索源")
    limit_per_source: int = Field(30, ge=1, le=100)
    year_from: Optional[int] = Field(None, ge=1900, le=2030)
    proxy: Optional[str] = Field(None, description="代理地址")
    dedup: bool = Field(True, description="跨库去重（DOI 主键 + 标题兜底）")
    sort_by: Literal["relevance", "citations", "year"] = Field("relevance", description="排序方式")


class SearchResponse(BaseModel):
    total: int
    per_source: dict[str, int]
    articles: list[dict]
    dedup: dict[str, int] = {}


class ErrorResponse(BaseModel):
    error: str
    detail: str = ""
    retries: int = 0


class ExportRequest(BaseModel):
    """多选导出请求"""
    format: Literal["markdown", "bibtex", "endnote", "csv", "text"]
    articles: list[dict] = Field(..., min_length=1, description="选中的文章列表")
    keywords: str = Field("", description="关联关键词（写入文件名与文档头）")
    save: bool = Field(True, description="是否在 out/exports/ 留档")


class DownloadRequest(BaseModel):
    """批量下载开放全文 PDF 请求"""
    articles: list[dict] = Field(..., min_length=1, description="待下载的文章列表")
    limit: int = Field(20, ge=1, le=200, description="单次最多下载篇数")
    proxy: Optional[str] = Field(None, description="代理地址（同检索）")


# ── 前端页面 ──

@app.get("/")
async def index(request: Request):
    """首页 - 检索页面"""
    return templates.TemplateResponse(request, "index.html", {
        "active_page": "search",
    })


@app.get("/history")
async def history_page(request: Request):
    """历史记录页面"""
    return templates.TemplateResponse(request, "history.html", {
                "active_page": "history",
    })


@app.get("/sources")
async def sources_page(request: Request):
    """数据源页面"""
    return templates.TemplateResponse(request, "sources.html", {
                "active_page": "sources",
    })


@app.get("/logs")
async def logs_page(request: Request):
    """操作日志页面"""
    return templates.TemplateResponse(request, "logs.html", {
                "active_page": "logs",
    })


# ── 检索源管理 ──

@app.get("/api/sources")
async def list_sources():
    """列出所有可用检索源及说明"""
    descriptions = {
        "arxiv": "arXiv 预印本 (Atom XML, 免费无上限)",
        "semanticscholar": "Semantic Scholar (JSON, 429限流需重试)",
        "crossref": "Crossref (JSON, DOI注册库, 免费)",
        "openreview": "OpenReview (JSON, 顶会评审)",
        "openaire": "OpenAIRE (JSON, 欧盟开放科学聚合)",
        "doaj": "DOAJ (JSON, 开放获取期刊目录)",
        "europepmc": "Europe PMC (JSON, 生物医学文献)",
    }
    return {
        "sources": [
            {"name": k, "description": descriptions.get(k, "")}
            for k in ADAPTERS.keys()
        ]
    }


# ── SSE 实时检索进度 ──

async def search_with_progress(keywords: str, sources: list[str], limit: int,
                               year_from: Optional[int], proxy: Optional[str] = None,
                               dedup: bool = True, sort_by: str = "relevance") -> AsyncGenerator[str, None]:
    """
    执行检索并通过 SSE 推送实时进度
    """
    all_articles: list[Article] = []
    per_source: dict[str, int] = {}
    errors: dict[str, str] = {}

    total_sources = len(sources)

    # 开始检索
    yield f"data: {json.dumps({'type': 'start', 'message': f'开始检索: {keywords}', 'total_sources': total_sources}, ensure_ascii=False)}\n\n"
    op_logger.info(f"开始检索: {keywords}", source="search", details={"keywords": keywords, "sources": sources})

    for idx, src_name in enumerate(sources, 1):
        if src_name not in ADAPTERS:
            yield f"data: {json.dumps({'type': 'skip', 'source': src_name, 'message': f'未知源: {src_name}'}, ensure_ascii=False)}\n\n"
            continue

        # 开始检索某个源
        progress_msg = f"[{idx}/{total_sources}] 正在检索 {src_name}..."
        yield f"data: {json.dumps({'type': 'progress', 'source': src_name, 'current': idx, 'total': total_sources, 'message': progress_msg}, ensure_ascii=False)}\n\n"
        op_logger.progress(progress_msg, source="search", details={"source": src_name, "current": idx, "total": total_sources})

        try:
            # 检索放入线程池执行，主协程轮询事件队列，
            # 把 429 限流等待 / 重试事件实时推给前端（搜索过程可见性）
            events: "queue.Queue[dict]" = queue.Queue()
            loop = asyncio.get_running_loop()

            def _on_rate_limit(info: RateLimitInfo):
                events.put({
                    "type": "rate_limit", "source": src_name,
                    "wait_seconds": info.wait_seconds,
                    "attempt": info.attempt, "max_attempts": info.max_attempts,
                    "message": f"{src_name}: 限流，等待 {info.wait_seconds}s (第{info.attempt}/{info.max_attempts}次)",
                })

            def _on_retry(attempt: int, max_attempts: int, reason: str):
                events.put({
                    "type": "retry", "source": src_name,
                    "message": f"{src_name}: 第{attempt}/{max_attempts}次重试 ({reason})",
                })

            def _run():
                return scanner.search_single(
                    source_name=src_name,
                    keywords=keywords,
                    limit=limit,
                    year_from=year_from,
                    proxy=proxy,
                    on_rate_limit=_on_rate_limit,
                    on_retry=_on_retry,
                )

            fut = loop.run_in_executor(None, _run)
            while not fut.done():
                try:
                    while True:
                        ev = events.get_nowait()
                        yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                        op_logger.progress(ev["message"], source="search", details={"source": src_name})
                except queue.Empty:
                    pass
                await asyncio.sleep(0.3)
            # 收尾：排空剩余事件
            while True:
                try:
                    ev = events.get_nowait()
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                    op_logger.progress(ev["message"], source="search", details={"source": src_name})
                except queue.Empty:
                    break
            articles = fut.result()
            per_source[src_name] = len(articles)
            for a in articles:
                all_articles.append(a)

            # 成功
            success_msg = f"{src_name}: 找到 {len(articles)} 篇"
            yield f"data: {json.dumps({'type': 'success', 'source': src_name, 'count': len(articles), 'message': success_msg}, ensure_ascii=False)}\n\n"
            op_logger.success(success_msg, source="search", details={"source": src_name, "count": len(articles)})

        except FetchError as e:
            per_source[src_name] = 0
            errors[src_name] = str(e)
            error_msg = f"{src_name}: 检索失败 (重试 {e.retries_done} 次)"
            yield f"data: {json.dumps({'type': 'error', 'source': src_name, 'error': str(e), 'retries': e.retries_done, 'message': error_msg}, ensure_ascii=False)}\n\n"
            op_logger.error(error_msg, source="search", details={"source": src_name, "error": str(e), "retries": e.retries_done})

        except Exception as e:
            per_source[src_name] = 0
            errors[src_name] = str(e)[:200]
            error_msg = f"{src_name}: {str(e)[:100]}"
            yield f"data: {json.dumps({'type': 'error', 'source': src_name, 'error': str(e)[:200], 'message': error_msg}, ensure_ascii=False)}\n\n"
            op_logger.error(error_msg, source="search", details={"source": src_name, "error": str(e)[:200]})

        # 小延迟让前端有时间渲染
        await asyncio.sleep(0.1)

    # 保存历史
    if scanner.history:
        try:
            scanner.history.add(
                keywords=keywords,
                sources=sources,
                year_from=year_from,
                limit_per_source=limit,
                total_results=len(all_articles),
                per_source=per_source,
            )
        except Exception as e:
            logger.error(f"保存历史失败: {e}")

    # ── 去重 + 排序 ──
    dedup_stats = {"original": len(all_articles), "removed": 0, "by_doi": 0, "by_title": 0}
    if dedup:
        all_articles, dedup_stats = deduplicate(all_articles)
    if sort_by != "relevance":
        all_articles = sort_articles(all_articles, by=sort_by, desc=True)

    # 最近结果供 /api/articles 复用
    global _last_results
    _last_results = [a.to_dict() for a in all_articles]

    # 完成
    complete_msg = f"检索完成: 共 {len(all_articles)} 篇"
    if dedup_stats["removed"]:
        complete_msg += f"（去重合并 {dedup_stats['removed']} 条重复）"
    yield f"data: {json.dumps({'type': 'complete', 'total': len(all_articles), 'per_source': per_source, 'errors': errors, 'dedup': dedup_stats, 'articles': _last_results, 'message': complete_msg}, ensure_ascii=False)}\n\n"
    op_logger.success(complete_msg, source="search", details={"total": len(all_articles), "per_source": per_source, "dedup": dedup_stats})


@app.get("/api/search/stream")
async def search_stream(keywords: str, sources: str = None, limit_per_source: int = 30,
                        year_from: Optional[int] = Query(None, ge=1900, le=2030),
                        proxy: Optional[str] = None, dedup: bool = True,
                        sort_by: Literal["relevance", "citations", "year"] = "relevance"):
    """
    SSE 实时检索进度
    sources: 逗号分隔的源名称，如 "arxiv,semanticscholar,crossref"
    dedup: 是否跨库去重；sort_by: relevance | citations | year
    """
    if not keywords:
        raise HTTPException(status_code=400, detail="关键词不能为空")

    # 解析源列表
    if sources:
        source_list = [s.strip() for s in sources.split(",") if s.strip()]
    else:
        source_list = list(ADAPTERS.keys())

    # 验证源
    valid_sources = [s for s in source_list if s in ADAPTERS]
    if not valid_sources:
        raise HTTPException(status_code=400, detail="没有有效的检索源")

    return StreamingResponse(
        search_with_progress(keywords, valid_sources, limit_per_source, year_from, proxy,
                             dedup, sort_by),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 检索接口 ──

@app.post("/api/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """多库检索"""
    global _last_results
    _last_results = []

    sources_to_use = request.sources
    per_source: dict[str, int] = {}
    all_articles: list[Article] = []
    errors: dict[str, str] = {}

    op_logger.info(f"开始检索: {request.keywords}", source="api", details={"keywords": request.keywords, "sources": sources_to_use})

    for src_name in sources_to_use:
        if src_name not in ADAPTERS:
            raise HTTPException(status_code=400, detail=f"未知检索源: {src_name}")

        try:
            articles = scanner.search_single(
                source_name=src_name,
                keywords=request.keywords,
                limit=request.limit_per_source,
                year_from=request.year_from,
                proxy=request.proxy,
            )
            per_source[src_name] = len(articles)
            for a in articles:
                all_articles.append(a)
            op_logger.success(f"{src_name}: {len(articles)} 篇", source="api", details={"source": src_name, "count": len(articles)})
        except FetchError as e:
            per_source[src_name] = 0
            errors[src_name] = str(e)
            op_logger.error(f"{src_name}: 检索失败", source="api", details={"source": src_name, "error": str(e)})
        except Exception as e:
            per_source[src_name] = 0
            errors[src_name] = str(e)[:200]
            op_logger.error(f"{src_name}: {str(e)[:100]}", source="api", details={"source": src_name, "error": str(e)[:200]})

    # ── 去重 + 排序 ──
    dedup_stats = {"original": len(all_articles), "removed": 0, "by_doi": 0, "by_title": 0}
    if request.dedup:
        all_articles, dedup_stats = deduplicate(all_articles)
    if request.sort_by != "relevance":
        all_articles = sort_articles(all_articles, by=request.sort_by, desc=True)
    _last_results = [a.to_dict() for a in all_articles]

    # 保存历史
    if scanner.history:
        try:
            scanner.history.add(
                keywords=request.keywords,
                sources=sources_to_use,
                year_from=request.year_from,
                limit_per_source=request.limit_per_source,
                total_results=len(all_articles),
                per_source=per_source,
            )
        except Exception as e:
            logger.error(f"保存历史失败: {e}")

    op_logger.success(f"检索完成: 共 {len(all_articles)} 篇", source="api",
                      details={"total": len(all_articles), "dedup": dedup_stats})

    response = SearchResponse(
        total=len(all_articles),
        per_source=per_source,
        articles=_last_results,
        dedup=dedup_stats,
    )

    # 有错误时附加到响应
    if errors:
        response_dict = response.model_dump()
        response_dict["errors"] = errors
        return response_dict

    return response


@app.post("/api/search/{source}", response_model=SearchResponse)
async def search_single_source(source: str, request: SearchRequest):
    """单库检索"""
    global _last_results

    if source not in ADAPTERS:
        raise HTTPException(status_code=400, detail=f"未知检索源: {source}")

    try:
        articles = scanner.search_single(
            source_name=source,
            keywords=request.keywords,
            limit=request.limit_per_source,
            year_from=request.year_from,
            proxy=request.proxy,
        )
        result_list = [a.to_dict() for a in articles]
        _last_results = result_list

        # 保存历史
        if scanner.history:
            scanner.history.add(
                keywords=request.keywords,
                sources=[source],
                year_from=request.year_from,
                limit_per_source=request.limit_per_source,
                total_results=len(result_list),
                per_source={source: len(result_list)},
            )

        return SearchResponse(
            total=len(result_list),
            per_source={source: len(result_list)},
            articles=result_list,
        )
    except FetchError as e:
        raise HTTPException(
            status_code=503,
            detail=f"检索失败: {str(e)} (已重试 {e.retries_done} 次)"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检索异常: {str(e)}")


@app.get("/api/articles")
async def get_last_articles():
    """获取最近一次检索结果"""
    return {"total": len(_last_results), "articles": _last_results}


# ── 多选导出 ──

@app.post("/api/export")
async def export_articles(request: ExportRequest):
    """
    多选导出：markdown(链接收藏) / bibtex / endnote(RIS) / csv / text(复制用纯文本)
    save=true 时同时在 out/exports/ 留档，路径放响应头 X-Export-Path
    """
    fmt = request.format
    try:
        content = build_export(fmt, request.articles, request.keywords)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    meta = FORMAT_META[fmt]
    op_logger.info(
        f"导出 {len(request.articles)} 篇 ({fmt})",
        source="export",
        details={"format": fmt, "count": len(request.articles), "keywords": request.keywords},
    )

    export_path = None
    if request.save:
        try:
            export_dir = os.path.join(BASE_DIR, "out", "exports")
            export_path = save_export(content, fmt, export_dir, request.keywords)
        except OSError as e:
            logger.error(f"导出留档失败: {e}")

    headers = {}
    if export_path:
        # 路径可能含中文/非 latin-1 字符，HTTP 头必须编码，否则 starlette 会抛 UnicodeEncodeError
        headers["X-Export-Path"] = quote(export_path)

    safe_kw = "".join(c for c in request.keywords if c.isalnum() or c in "-_ ")[:30].strip().replace(" ", "_")
    filename = f"litscan_{fmt}{('_' + safe_kw) if safe_kw else ''}.{meta['ext']}"
    ascii_name = filename.encode("ascii", "ignore").decode() or f"litscan_{fmt}.{meta['ext']}"
    headers["Content-Disposition"] = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"

    return Response(content=content, media_type=meta["mime"], headers=headers)


# ── 全文 PDF 下载 ──

@app.get("/api/download/supported")
async def download_supported():
    """各源全文 PDF 直下支持情况（含不可下载的原因）"""
    return {"sources": support_table()}


@app.post("/api/download")
def download_pdfs(request: DownloadRequest):
    """
    批量下载开放全文 PDF 到 out/pdf/，已存在且体积达标的文件自动跳过（断点续传）。
    支持: arxiv / openreview / semanticscholar / europepmc / doaj；
    不支持: crossref / openaire（原因见返回结果的 reason 与 /api/download/supported）。
    """
    pdf_dir = os.path.join(BASE_DIR, "out", "pdf")
    try:
        summary = download_articles(
            request.articles, pdf_dir, limit=request.limit, proxy=request.proxy,
        )
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"写入 PDF 失败: {e}")

    op_logger.info(
        f"PDF 下载 {summary['total']} 篇: 成功 {summary['downloaded']} / 跳过 {summary['skipped']} / "
        f"失败 {summary['failed']} / 不支持 {summary['unsupported']}",
        source="download",
        details={"dir": summary["dir"], "downloaded": summary["downloaded"],
                 "skipped": summary["skipped"], "failed": summary["failed"],
                 "unsupported": summary["unsupported"]},
    )
    return summary


# ── 文章详情（站内快速预览） ──

@app.get("/api/article/detail")
async def article_detail(source: str, url: str = None, doi: str = None):
    """
    回源拉取文章完整信息（全量摘要、作者、分类、PDF 链接等），带 30 分钟缓存
    支持: arxiv / crossref / semanticscholar / openreview / europepmc / doaj
    """
    if source not in ADAPTERS:
        raise HTTPException(status_code=400, detail=f"未知检索源: {source}")
    if not url and not doi:
        raise HTTPException(status_code=400, detail="需要 url 或 doi 参数")

    try:
        data = get_detail(source, url=url, doi=doi)
        op_logger.info(f"详情预览: {source}", source="detail", details={"source": source, "url": url, "doi": doi})
        return data
    except DetailNotSupported as e:
        raise HTTPException(status_code=501, detail=str(e))
    except DetailNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FetchError as e:
        raise HTTPException(status_code=503, detail=f"回源失败: {str(e)} (已重试 {e.retries_done} 次)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"详情获取异常: {str(e)[:200]}")


@app.get("/api/stats")
async def get_stats():
    """全局统计信息"""
    return {
        "sources": {name: desc for name, desc in [
            (k, v.__doc__ or "") for k, v in ADAPTERS.items()
        ]},
        "total_sources": len(ADAPTERS),
        "history_enabled": scanner.history is not None,
        "history_count": len(scanner.history) if scanner.history else 0,
    }


# ── 搜索历史 ──

@app.get("/api/history")
async def get_history(limit: int = 20):
    """获取搜索历史"""
    if not scanner.history:
        return {"total": 0, "records": []}
    records = scanner.history.list(limit=limit)
    return {
        "total": len(scanner.history),
        "records": [r.to_dict() for r in records],
    }


@app.get("/api/history/stats")
async def get_history_stats():
    """历史统计"""
    if not scanner.history:
        return {"total": 0, "favorite_keywords": [], "source_usage": {}}
    return {
        "total": len(scanner.history),
        "favorite_keywords": scanner.history.get_favorite_keywords(),
        "source_usage": scanner.history.get_source_usage(),
    }


@app.get("/api/history/{record_id}")
async def get_history_record(record_id: str):
    """获取单条历史记录"""
    if not scanner.history:
        raise HTTPException(status_code=404, detail="历史功能未启用")
    record = scanner.history.get(record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"未找到记录: {record_id}")
    return record.to_dict()


@app.post("/api/history/search")
async def search_history(query: str, limit: int = 20):
    """搜索历史记录"""
    if not scanner.history:
        return {"total": 0, "records": []}
    records = scanner.history.search_by_keywords(query)[:limit]
    return {
        "total": len(records),
        "records": [r.to_dict() for r in records],
    }


@app.post("/api/history/retry/{record_id}")
async def retry_from_history(record_id: str):
    """从历史记录重新执行检索"""
    try:
        articles = scanner.retry_from_history(record_id)
        return {"total": len(articles), "articles": [a.to_dict() for a in articles]}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/history/{record_id}")
async def delete_history_record(record_id: str):
    """删除一条历史记录"""
    if not scanner.history:
        raise HTTPException(status_code=404, detail="历史功能未启用")
    if scanner.history.delete(record_id):
        return {"message": f"已删除: {record_id}"}
    raise HTTPException(status_code=404, detail=f"未找到: {record_id}")


@app.delete("/api/history")
async def clear_history():
    """清空历史"""
    if not scanner.history:
        raise HTTPException(status_code=404, detail="历史功能未启用")
    scanner.history.clear()
    return {"message": "历史已清空"}


# ── 操作日志 API ──

@app.get("/api/logs")
async def get_logs(limit: int = 50, level: str = None, source: str = None):
    """获取操作日志"""
    entries = op_logger.list(limit=limit, level=level, source=source)
    return {
        "total": len(op_logger),
        "entries": [e.to_dict() for e in entries],
    }


@app.get("/api/logs/stats")
async def get_log_stats():
    """日志统计"""
    entries = op_logger.list(limit=500)
    level_counts = {}
    source_counts = {}
    for e in entries:
        level_counts[e.level] = level_counts.get(e.level, 0) + 1
        source_counts[e.source] = source_counts.get(e.source, 0) + 1
    return {
        "total": len(op_logger),
        "level_counts": level_counts,
        "source_counts": source_counts,
    }


@app.delete("/api/logs")
async def clear_logs():
    """清空操作日志"""
    op_logger.clear()
    return {"message": "日志已清空"}


# ── 启动入口 ──

def run_server(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
