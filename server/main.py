"""
LitScan FastAPI 后端

页面路由:
  GET  /                    首页 (检索页面)
  GET  /history             历史记录页面
  GET  /sources             数据源页面

API 接口 (前缀 /api/):
  GET  /api/sources             列出可用检索源
  POST /api/search              多库检索
  POST /api/search/{source}     单库检索
  GET  /api/articles            最近一次检索结果
  GET  /api/history             搜索历史
  GET  /api/history/{record_id} 历史记录详情
  POST /api/history/search      搜索历史记录
  POST /api/history/retry/{id}  从历史重新检索
  DELETE /api/history/{id}      删除历史记录
  DELETE /api/history           清空历史
"""

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.scanner import Scanner
from core.adapters import ADAPTERS, Article
from core.history import SearchHistory, SearchRecord
from core.fetcher import FetchError, RateLimitInfo

logger = logging.getLogger("litscan.server")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(
    title="LitScan",
    description="学术文献多库检索工具",
    version="0.1.0",
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


# ── 请求/响应模型 ──

class SearchRequest(BaseModel):
    keywords: str = Field(..., min_length=1, examples=["LLM agent evaluation"])
    sources: list[str] = Field(..., min_length=1, description="指定检索源")
    limit_per_source: int = Field(30, ge=1, le=100)
    year_from: Optional[int] = Field(None, ge=1900, le=2030)
    proxy: Optional[str] = Field(None, description="代理地址")


class SearchResponse(BaseModel):
    total: int
    per_source: dict[str, int]
    articles: list[dict]


class ErrorResponse(BaseModel):
    error: str
    detail: str = ""
    retries: int = 0


# ── 前端页面 ──

@app.get("/")
async def index(request: Request):
    """首页 - 检索页面"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "active_page": "search",
    })


@app.get("/history")
async def history_page(request: Request):
    """历史记录页面"""
    return templates.TemplateResponse("history.html", {
        "request": request,
        "active_page": "history",
    })


@app.get("/sources")
async def sources_page(request: Request):
    """数据源页面"""
    return templates.TemplateResponse("sources.html", {
        "request": request,
        "active_page": "sources",
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


# ── 检索接口 ──

@app.post("/api/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """多库检索"""
    global _last_results
    _last_results = []

    sources_to_use = request.sources
    per_source: dict[str, int] = {}
    all_articles: list[dict] = []
    errors: dict[str, str] = {}

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
                d = a.to_dict()
                all_articles.append(d)
                _last_results.append(d)
        except FetchError as e:
            per_source[src_name] = 0
            errors[src_name] = str(e)
            logger.error(f"{src_name} 检索失败: {e}")
        except Exception as e:
            per_source[src_name] = 0
            errors[src_name] = str(e)[:200]
            logger.error(f"{src_name} 检索异常: {e}")

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

    response = SearchResponse(
        total=len(all_articles),
        per_source=per_source,
        articles=all_articles,
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


# ── 启动入口 ──

def run_server(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
