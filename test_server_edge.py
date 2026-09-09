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
r = client.post("/api/export", json={"format": "markdown", "articles": ARTICLES, "save": True})
export_path = r.headers.get("x-export-path", "")
test("留档路径写入响应头", "exports" in export_path and os.path.exists(export_path))
if export_path and os.path.exists(export_path):
    with open(export_path, "r", encoding="utf-8") as f:
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
