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
