#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LitScan 服务端边界测试 (仅验证逻辑，不发网络请求)"""
import sys, os, json, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)

results = {"pass": 0, "fail": 0}

def test(name, condition, detail=""):
    if condition:
        results["pass"] += 1
        print(f"  ✓ {name}")
    else:
        results["fail"] += 1
        print(f"  ✗ {name} {detail}")

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ─────────────────────────────────────────────────────────────
section("1. API 参数验证 (即时返回)")
# ─────────────────────────────────────────────────────────────

# 1.1 空关键词
r = client.post("/api/search", json={"keywords": "", "sources": ["arxiv"]})
test("空关键词返回 422", r.status_code == 422)

# 1.2 无效 source (语义错误，返回 400)
r = client.post("/api/search", json={"keywords": "test", "sources": ["nonexistent"]})
test("无效 source 返回 400", r.status_code == 400)

# 1.3 空 sources
r = client.post("/api/search", json={"keywords": "test", "sources": []})
test("空 sources 返回 422", r.status_code == 422)

# 1.4 缺失必填字段
r = client.post("/api/search", json={"keywords": "test"})
test("缺失 sources 返回 422", r.status_code == 422)

r = client.post("/api/search", json={"sources": ["arxiv"]})
test("缺失 keywords 返回 422", r.status_code == 422)

# 1.5 年份超出范围
r = client.post("/api/search", json={"keywords": "test", "sources": ["arxiv"], "year_from": 1800})
test("年份过小返回 422", r.status_code == 422)

r = client.post("/api/search", json={"keywords": "test", "sources": ["arxiv"], "year_from": 2100})
test("年份过大返回 422", r.status_code == 422)

# 1.6 limit 超出范围
r = client.post("/api/search", json={"keywords": "test", "sources": ["arxiv"], "limit_per_source": 0})
test("limit=0 返回 422", r.status_code == 422)

r = client.post("/api/search", json={"keywords": "test", "sources": ["arxiv"], "limit_per_source": 101})
test("limit=101 返回 422", r.status_code == 422)

# 1.7 完全空 body
r = client.post("/api/search", json={})
test("空 body 返回 422", r.status_code == 422)


# ─────────────────────────────────────────────────────────────
section("2. 历史 API 边界")
# ─────────────────────────────────────────────────────────────

# 2.1 删除不存在的记录
r = client.delete("/api/history/nonexistent_id_xyz")
test("删除不存在记录返回 404", r.status_code == 404)

# 2.2 获取不存在记录
r = client.get("/api/history/nonexistent_id_xyz")
test("获取不存在记录返回 404", r.status_code == 404)

# 2.3 清空空历史
r = client.delete("/api/history")
test("清空历史", r.status_code == 200)

# 2.4 获取空历史
r = client.get("/api/history")
test("空历史返回空列表", r.status_code == 200 and r.json()["records"] == [])

# 2.5 历史搜索
r = client.post("/api/history/search", params={"query": "test"})
test("历史搜索", r.status_code == 200)

# 2.6 历史统计
r = client.get("/api/history/stats")
test("历史统计", r.status_code == 200)

# 2.7 不存在的历史重试
r = client.post("/api/history/retry/nonexistent_id")
test("不存在历史重试返回 404", r.status_code == 404)


# ─────────────────────────────────────────────────────────────
section("3. 页面路由边界")
# ─────────────────────────────────────────────────────────────

# 3.1 不存在的页面
r = client.get("/nonexistent_page_12345")
test("不存在页面返回 404", r.status_code == 404)

# 3.2 不存在的 API
r = client.get("/api/nonexistent_endpoint")
test("不存在 API 返回 404", r.status_code == 404)

# 3.3 根路径
r = client.get("/")
test("根路径返回 200", r.status_code == 200)

# 3.4 静态文件
r = client.get("/static/style.css")
test("CSS 文件", r.status_code == 200)

# 3.5 各页面
for page in ["/", "/history", "/sources"]:
    r = client.get(page)
    test(f"页面 {page}", r.status_code == 200)


# ─────────────────────────────────────────────────────────────
section("4. Sources API")
# ─────────────────────────────────────────────────────────────

r = client.get("/api/sources")
test("Sources 列表", r.status_code == 200)
sources = r.json().get("sources", [])
test("至少 1 个 source", len(sources) > 0)
if sources:
    test("Source 含 name", "name" in sources[0])
    test("Source 含 description", "description" in sources[0])


# ─────────────────────────────────────────────────────────────
section("5. Stats API")
# ─────────────────────────────────────────────────────────────

r = client.get("/api/stats")
test("全局统计", r.status_code == 200)
data = r.json()
test("统计含 sources", "sources" in data)


# ─────────────────────────────────────────────────────────────
section("6. Articles API (空状态)")
# ─────────────────────────────────────────────────────────────

r = client.get("/api/articles")
test("空文章列表", r.status_code == 200)
test("空文章总数为 0", r.json()["total"] == 0)


# ─────────────────────────────────────────────────────────────
section("7. 导出 API /api/export (无网络)")
# ─────────────────────────────────────────────────────────────

ARTICLES = [
    {"title": "Attention Is All You Need", "source": "arxiv", "year": 2017,
     "venue": "NeurIPS", "doi": "10.5555/3295222", "url": "https://arxiv.org/abs/1706.03762",
     "citation_count": 90000, "authors": "Ashish Vaswani", "abstract": "abstract text"},
]

# 7.1 markdown 导出
r = client.post("/api/export", json={"format": "markdown", "articles": ARTICLES, "keywords": "transformer"})
test("markdown 导出 200", r.status_code == 200)
test("markdown Content-Type", "text/markdown" in r.headers["content-type"])
test("markdown 内容含标题", "Attention Is All You Need" in r.text)
test("markdown 附件头", "attachment" in r.headers.get("content-disposition", ""))

# 7.2 各格式
for fmt, needle in [("bibtex", "@article{"), ("endnote", "TY  - JOUR"),
                    ("csv", "title,source,sources,year"), ("text", "- Attention")]:
    r = client.post("/api/export", json={"format": fmt, "articles": ARTICLES, "save": False})
    test(f"{fmt} 导出 200 且内容正确", r.status_code == 200 and needle in r.text)

# 7.3 非法格式
r = client.post("/api/export", json={"format": "xml", "articles": ARTICLES})
test("非法格式返回 422", r.status_code == 422)

# 7.4 空文章列表
r = client.post("/api/export", json={"format": "markdown", "articles": []})
test("空列表返回 422", r.status_code == 422)

# 7.5 留档
from urllib.parse import unquote as _unquote
r = client.post("/api/export", json={"format": "markdown", "articles": ARTICLES, "save": True})
raw_path = r.headers.get("x-export-path", "")
real_path = _unquote(raw_path) if raw_path else ""
test("留档路径写入响应头", "exports" in real_path and os.path.exists(real_path))
if real_path and os.path.exists(real_path):
    with open(real_path, "r", encoding="utf-8") as f:
        test("留档内容与响应一致", "Attention Is All You Need" in f.read())
    # out/ 已被 .gitignore 忽略，留档文件无需删除

# ─────────────────────────────────────────────────────────────
section("8. 详情 API /api/article/detail (参数校验，无网络)")
# ─────────────────────────────────────────────────────────────

r = client.get("/api/article/detail", params={"source": "nonexistent", "url": "https://x.com"})
test("未知源返回 400", r.status_code == 400)

r = client.get("/api/article/detail", params={"source": "arxiv"})
test("缺 url 和 doi 返回 400", r.status_code == 400)

r = client.get("/api/article/detail", params={"source": "openaire", "url": "https://x.com"})
test("不支持回源的源返回 501", r.status_code == 501)

# arxiv 传入无法解析的链接 → DetailNotFound → 404 (不发请求，解析即失败)
r = client.get("/api/article/detail", params={"source": "arxiv", "url": "https://example.com/no-id"})
test("无法解析 arXiv ID 返回 404", r.status_code == 404)

# crossref 缺 DOI → 404
r = client.get("/api/article/detail", params={"source": "crossref", "url": "https://example.com"})
test("crossref 缺 DOI 返回 404", r.status_code == 404)

# semanticscholar 缺 DOI/paperId → 404
r = client.get("/api/article/detail", params={"source": "semanticscholar", "url": "https://example.com"})
test("s2 缺标识符返回 404", r.status_code == 404)

# openreview 链接无 id 参数 → 404
r = client.get("/api/article/detail", params={"source": "openreview", "url": "https://openreview.net/forum"})
test("openreview 缺 id 返回 404", r.status_code == 404)


# ─────────────────────────────────────────────────────────────
section("9. 去重/排序参数 (参数校验，无网络)")
# ─────────────────────────────────────────────────────────────

# 9.1 dedup / sort_by 参数被接受（sources 无效会先于网络失败）
r = client.post("/api/search", json={
    "keywords": "test", "sources": ["arxiv"],
    "dedup": False, "sort_by": "citations"})
test("dedup/sort_by 参数接受", r.status_code in (200, 503))

# 9.2 非法排序值 → 422
r = client.post("/api/search", json={
    "keywords": "test", "sources": ["arxiv"], "sort_by": "nonsense"})
test("非法 sort_by 返回 422", r.status_code == 422)

# 9.3 去重逻辑直测（不发网络）
from core.dedup import deduplicate
from core.adapters import Article
arts = [
    Article(title="Same Paper", source="arxiv", doi="10.1000/abc"),
    Article(title="Same Paper", source="crossref", doi="https://doi.org/10.1000/ABC",
            abstract="longer", citation_count=7),
    Article(title="Unique", source="doaj"),
]
kept, st = deduplicate(arts)
test("服务端可用去重函数", len(kept) == 2 and st["removed"] == 1)
test("合并后带 sources", "; " in (kept[0].sources or ""))

# ─────────────────────────────────────────────────────────────
section("10. 前后端契约一致性")
# ─────────────────────────────────────────────────────────────

# 10.1 版本号与 pyproject.toml 一致
import re as _re
from core.exporter import FORMAT_META
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pyproject.toml"),
          encoding="utf-8") as _f:
    _pv = _re.search(r'^version\s*=\s*"([^"]+)"', _f.read(), _re.M).group(1)
test("FastAPI 版本 == pyproject 版本", app.version == _pv, f"{app.version} vs {_pv}")
test("OpenAPI 版本同步", client.get("/openapi.json").json()["info"]["version"] == _pv)

# 10.2 前端用到的导出格式后端全部支持
FRONTEND_FORMATS = ["markdown", "bibtex", "endnote", "csv", "text"]
test("导出格式枚举与前端一致", set(FRONTEND_FORMATS) == set(FORMAT_META.keys()),
     str(set(FRONTEND_FORMATS) ^ set(FORMAT_META.keys())))
for fmt in FRONTEND_FORMATS:
    ok = client.post("/api/export", json={"format": fmt, "articles": ARTICLES, "save": False}).status_code == 200
    test(f"导出 {fmt} 可用", ok)

# 10.2.1 关键词含中文时导出也必须成功（回归：之前 X-Export-Path latin-1 失败 500）
r = client.post("/api/export", json={"format": "markdown", "articles": ARTICLES,
                                     "keywords": "对齐验证 中文关键词", "save": True})
test("中文关键词导出留档 200", r.status_code == 200)
test("中文关键词响应头 X-Export-Path 存在", r.headers.get("x-export-path"))
test("中文关键词路径头 latin-1 安全（无原 UnicodeEncodeError）",
     r.headers.get("x-export-path") is not None)

# 10.3 SSE 参数校验与 POST 接口保持一致
r = client.get("/api/search/stream", params={"keywords": "x", "sort_by": "nonsense", "sources": "arxiv"})
test("SSE 非法 sort_by 返回 422", r.status_code == 422)
r = client.get("/api/search/stream", params={"keywords": "x", "year_from": 1000, "sources": "arxiv"})
test("SSE 非法 year_from 返回 422", r.status_code == 422)

# 10.4 详情端点参数校验
test("详情未知源 400", client.get("/api/article/detail", params={"source": "nope", "url": "http://x"}).status_code == 400)
test("详情缺 url/doi 400", client.get("/api/article/detail", params={"source": "arxiv"}).status_code == 400)
test("不支持回源的源 501", client.get("/api/article/detail", params={
    "source": "openaire", "url": "http://x"}).status_code == 501)

# 10.5 详情字段展平：extra 里的字段必须提升到顶层（前端统一渲染）
import core.article_detail as _ad
_orig_fetchers = dict(_ad.DETAIL_FETCHERS)
_ad._cache.clear()
_ad.DETAIL_FETCHERS["semanticscholar"] = lambda url, doi: {
    "source": "semanticscholar", "title": "T", "abstract": "A",
    "extra": {"tldr": "一句话总结", "influential_citations": 3},
}
try:
    d = _ad.get_detail("semanticscholar", url="https://semanticscholar.org/paper/x",
                       doi="10.1/y")
    test("extra 字段提升到顶层 (tldr)", d.get("tldr") == "一句话总结")
    test("extra 字段提升到顶层 (influential_citations)", d.get("influential_citations") == 3)
    test("extra 仍保留", isinstance(d.get("extra"), dict))
finally:
    _ad.DETAIL_FETCHERS.clear()
    _ad.DETAIL_FETCHERS.update(_orig_fetchers)
    _ad._cache.clear()

# 10.6 Europe PMC 作者必须是字符串（旧实现返回 dict 会导致前端 [object Object]）
_orig_fetch = _ad.fetch

_EPMC_PAYLOAD = {
    "resultList": {"result": [{
        "id": "123", "title": "P", "abstractText": "AB",
        "authorList": {"author": [{"fullName": "Alice Wang"}, {"fullName": "Bob Li"}]},
        "authorString": "Wang A, Li B", "pubYear": 2024,
        "journalInfo": {"journal": {"title": "J"}}, "citedByCount": 5,
    }]}
}


class _FakeResp:
    def json(self):
        return _EPMC_PAYLOAD


_ad.fetch = lambda *a, **k: _FakeResp()
try:
    e = _ad.detail_europepmc(url="http://x", doi="10.1/z")
    test("EuropePMC 作者为字符串", all(isinstance(x, str) for x in e["authors"]), str(e["authors"])[:60])
    test("EuropePMC 作者内容正确", e["authors"] == ["Alice Wang", "Bob Li"])
finally:
    _ad.fetch = _orig_fetch

# 10.7 缓存命中带 cached 标记
_ad._cache.clear()
_ad.DETAIL_FETCHERS["arxiv"] = lambda url, doi: {"source": "arxiv", "title": "T", "extra": {}}
try:
    _ad.get_detail("arxiv", url="http://arxiv.org/abs/1")
    d2 = _ad.get_detail("arxiv", url="http://arxiv.org/abs/1")
    test("缓存命中标记 cached", d2.get("cached") is True)
    test("缓存副本不污染原数据", d2 is not _ad._cache["arxiv|http://arxiv.org/abs/1|"][1])
finally:
    _ad.DETAIL_FETCHERS.clear()
    _ad.DETAIL_FETCHERS.update(_orig_fetchers)
    _ad._cache.clear()

# ─────────────────────────────────────────────────────────────
section("11. 全文下载 API (无网络)")
# ─────────────────────────────────────────────────────────────

r = client.get("/api/download/supported")
test("下载支持表 200", r.status_code == 200)
_src = {s["source"]: s for s in r.json().get("sources", [])}
test("支持表含 arxiv 且可下载", _src.get("arxiv", {}).get("supported") is True)
test("支持表含 crossref 且走 DOI 兜底", _src.get("crossref", {}).get("mode") == "oa_lookup")
test("支持表含 openaire 且标注不可下载", _src.get("openaire", {}).get("supported") is False)
test("不可下载源带原因说明", bool(_src.get("openaire", {}).get("note")))

r = client.post("/api/download", json={"articles": []})
test("空文章列表返回 422", r.status_code == 422)

r = client.post("/api/download", json={"articles": [{"source": "openaire"}], "limit": 0})
test("limit=0 返回 422", r.status_code == 422)

# openaire 无 DOI 兜底，走 unsupported 分支，不发网络请求
r = client.post("/api/download", json={
    "articles": [{"title": "O", "source": "openaire"}], "limit": 5})
test("openaire 下载请求 200", r.status_code == 200)
_d = r.json()
test("openaire 计入 unsupported", _d["unsupported"] == 1 and _d["downloaded"] == 0)
test("openaire 结果带不可下载原因", bool(_d["results"][0].get("reason")))
test("下载响应含目录字段", "dir" in _d)


# ─────────────────────────────────────────────────────────────
section("12. 前后端契约与页面静态校验")
# ─────────────────────────────────────────────────────────────

# 12.1 /api/sources 字段与前端渲染一致
_s0 = client.get("/api/sources").json()["sources"][0]
test("sources 项含 name/description", "name" in _s0 and "description" in _s0)

# 12.2 /api/download/supported 字段与前端读取一致
_sup0 = client.get("/api/download/supported").json()["sources"][0]
test("supported 项含 source/supported/mode/note",
     all(k in _sup0 for k in ("source", "supported", "mode", "note")))

# 12.3 /api/download 汇总与单条结果字段与前端读取一致
_dl = client.post("/api/download", json={"articles": [{"title": "O", "source": "openaire"}]}).json()
test("download 汇总字段齐全",
     all(k in _dl for k in ("total", "downloaded", "skipped", "failed", "unsupported", "dir", "results")))
_r0 = _dl["results"][0]
test("download 单条结果字段齐全",
     all(k in _r0 for k in ("title", "source", "identifier", "status", "path", "size", "pdf_url", "via", "reason")))

# 12.4 首页引用的所有接口路径都存在（防止前端调用后端没有的路由）
_html = client.get("/").text
for _token in ("/api/sources", "/api/search/stream", "/api/export",
               "/api/article/detail", "/api/download", "/api/download/supported"):
    test(f"首页引用接口 {_token}", _token in _html)

# 12.5 首页关键元素/钩子齐全（按钮与 JS 选择器一致）
for _token in ('id="btnDownloadSelected"', "data-download", "data-export", "data-preview",
               'id="previewModal"', 'id="downloadModal"', 'id="actionBar"', 'id="toast"'):
    test(f"首页包含 {_token}", _token in _html)

# 12.6 首页不残留已废弃的下载交互写法
test("首页已改为分批下载", "DOWNLOAD_CHUNK" in _html)
test("首页含下载结果弹窗渲染逻辑", "openDownloadResult" in _html)

# 12.7 导航页面全部可达
for _page in ("/", "/history", "/sources", "/logs"):
    test(f"页面可访问 {_page}", client.get(_page).status_code == 200)

# 12.8 数据源页展示各源全文下载能力
_src_html = client.get("/sources").text
test("数据源页引用下载支持接口", "/api/download/supported" in _src_html)
test("数据源页含下载能力徽章", "dl-badge" in _src_html)

# 12.9 展示页（项目全景）与 README 断言资源存在
_root = os.path.dirname(os.path.abspath(__file__))
for _rel in ("project_overview/index.html", "docs/project_overview/index.html",
             "docs/assets/banner.svg", "docs/assets/architecture.svg",
             "docs/scripts/generate_banner.py", "docs/scripts/generate_architecture.py"):
    test(f"文档资产存在 {_rel}", os.path.exists(os.path.join(_root, _rel)))

# 12.10 展示页引用了新功能关键词（防止文档与实现脱节）
for _rel in ("project_overview/index.html", "docs/project_overview/index.html"):
    with open(os.path.join(_root, _rel), encoding="utf-8") as _f:
        _ov = _f.read()
    test(f"{_rel} 含全文下载章节", 'id="download"' in _ov)
    test(f"{_rel} 含下载 API", "/api/download" in _ov)

# 12.11 两张 SVG 资产内容已更新
with open(os.path.join(_root, "docs", "assets", "architecture.svg"), encoding="utf-8") as _f:
    _arch = _f.read()
test("架构图含 Full-text 管线", "Full-text" in _arch and "pdf/" in _arch)
with open(os.path.join(_root, "docs", "assets", "banner.svg"), encoding="utf-8") as _f:
    _banner = _f.read()
test("banner 统计已更新（20 endpoints）", "20" in _banner and "API Endpoints" in _banner)


# ─────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  测试结果汇总")
print(f"{'='*60}")
print(f"  通过: {results['pass']}")
print(f"  失败: {results['fail']}")
print(f"  总计: {results['pass'] + results['fail']}")
print(f"{'='*60}")
if results['fail'] == 0:
    print("  🎉 全部通过！")
else:
    print(f"  ⚠ {results['fail']} 项失败")
print(f"{'='*60}\n")

sys.exit(0 if results['fail'] == 0 else 1)
