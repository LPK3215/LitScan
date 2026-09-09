#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LitScan 边界情况测试"""
import sys, os, json, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.scanner import Scanner
from core.history import SearchHistory
from core.output import save_csv, append_log
from core.adapters import ADAPTERS, Article
from core.fetcher import fetch, FetchError

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
section("1. 特殊字符处理")
# ─────────────────────────────────────────────────────────────

# 1.1 关键词含特殊字符
scanner = Scanner(config={"sources": [], "query": {}, "output": {}, "request": {}, "history": {"enabled": False}})
articles = scanner.search_single("arxiv", "GAN (generative adversarial)", limit=2)
test("括号关键词", len(articles) > 0)

articles = scanner.search_single("arxiv", "C++ programming", limit=2)
test("加号关键词", len(articles) > 0)

articles = scanner.search_single("crossref", "COVID-19", limit=2)
test("连字符关键词", len(articles) > 0)

articles = scanner.search_single("crossref", "H2O", limit=2)
test("数字字母混合", len(articles) > 0)

# ─────────────────────────────────────────────────────────────
section("2. 极端参数")
# ─────────────────────────────────────────────────────────────

# 2.1 limit = 1
articles = scanner.search_single("arxiv", "test", limit=1)
test("limit=1", len(articles) == 1)

# 2.2 超长关键词
long_keyword = " ".join([f"word{i}" for i in range(50)])
try:
    articles = scanner.search_single("crossref", long_keyword, limit=1)
    test("超长关键词不崩溃", True)
except Exception as e:
    test("超长关键词不崩溃", False, str(e)[:50])

# ─────────────────────────────────────────────────────────────
section("3. 历史记录边界")
# ─────────────────────────────────────────────────────────────

tmp_dir = tempfile.mkdtemp()
hist_file = os.path.join(tmp_dir, "hist.json")

# 3.1 损坏的 JSON 文件
with open(hist_file, "w") as f:
    f.write("this is not valid json{{{")
h = SearchHistory(history_file=hist_file)
test("损坏 JSON 不崩溃", len(h) == 0)
test("损坏 JSON 后 bool 仍为 True", bool(h))

# 3.2 空文件
with open(hist_file, "w") as f:
    f.write("")
h = SearchHistory(history_file=hist_file)
test("空文件不崩溃", len(h) == 0)

# 3.3 正常写入后删除文件再操作
h.add("test", ["arxiv"], None, 10, 5, {"arxiv": 5})
os.remove(hist_file)
h.add("test2", ["crossref"], None, 10, 3, {"crossref": 3})
test("文件被删后重写", len(h) == 2)

# 3.4 大量记录
for i in range(100):
    h.add(f"query {i}", ["arxiv"], None, 10, i, {"arxiv": i})
test("100 条记录", len(h) == 102)
test("高频词统计", len(h.get_favorite_keywords()) > 0)

shutil.rmtree(tmp_dir)

# ─────────────────────────────────────────────────────────────
section("4. 输出边界")
# ─────────────────────────────────────────────────────────────

tmp_dir = tempfile.mkdtemp()

# 4.1 特殊字符写入 CSV
special_article = Article(title='Title with "quotes" and, comma', source="test", 
                         abstract="Line1\nLine2", authors="A; B")
csv_path = save_csv([special_article], tmp_dir, "special.csv")
test("特殊字符 CSV", os.path.exists(csv_path))
with open(csv_path, "r", encoding="utf-8-sig") as f:
    content = f.read()
    test("CSV 含转abel双引号", '""quotes"""' in content or '"quotes"' in content)

# 4.2 Unicode 写入
unicode_article = Article(title="中文标题 日本語 タイトل", source="test", 
                         abstract="Abstract with émojis 🎉")
csv_path = save_csv([unicode_article], tmp_dir, "unicode.csv")
test("Unicode CSV", os.path.exists(csv_path))
with open(csv_path, "r", encoding="utf-8-sig") as f:
    content = f.read()
    test("CSV 含中文", "中文" in content)

# 4.3 日志写入多行
log_path = os.path.join(tmp_dir, "test.md")
append_log(log_path, 'keywords with "quotes"', ["source with space"], {"source with space": 5}, 5)
test("特殊字符日志", os.path.exists(log_path))

shutil.rmtree(tmp_dir)

# ─────────────────────────────────────────────────────────────
section("5. Article 数据类边界")
# ─────────────────────────────────────────────────────────────

# 5.1 含 None 的 to_dict
a = Article(title="Test", source="test")
d = a.to_dict()
test("None 字段在 dict 中", d["year"] is None and d["doi"] is None)

# 5.2 from_dict 重建
from dataclasses import asdict
a2 = Article(**d)
test("from_dict 重建", a2.title == "Test" and a2.source == "test")

# ─────────────────────────────────────────────────────────────
section("6. 配置边界")
# ─────────────────────────────────────────────────────────────

# 6.1 空配置
s = Scanner(config={})
test("空配置不崩溃", s is not None)

# 6.2 只有部分配置
s = Scanner(config={"query": {"keywords": "test"}})
test("部分配置", s.config["query"]["keywords"] == "test")

# 6.3 无效的 sources 格式
s = Scanner(config={
    "sources": [{"name": "nonexistent_adapter", "enabled": True}],
    "query": {"keywords": "test"},
    "output": {},
    "request": {},
    "history": {"enabled": False}
})
# run() 应该跳过无效源而不是崩溃
articles = s.run()
test("无效源被跳过", len(articles) == 0)


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
