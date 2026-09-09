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
section("7. 导出模块 core/exporter.py")
# ─────────────────────────────────────────────────────────────

from core.exporter import (
    to_markdown, to_bibtex, to_text, to_csv_bytes,
    build_export, save_export, _safe_filename, _bibtex_key,
)

SAMPLE = [
    {"title": "Attention Is All You Need", "source": "arxiv", "year": 2017,
     "venue": "NeurIPS", "doi": "10.5555/3295222", "url": "https://arxiv.org/abs/1706.03762",
     "citation_count": 90000, "authors": "Ashish Vaswani; Noam Shazeer",
     "abstract": "The dominant sequence transduction models..."},
    {"title": "BERT: Pre-training of Deep Bidirectional Transformers", "source": "crossref",
     "year": 2019, "venue": None, "doi": "10.18653/v1/N19-1423", "url": None,
     "citation_count": None, "authors": "Jacob Devlin; Ming-Wei Chang", "abstract": None},
]

# 7.1 Markdown 导出
md = to_markdown(SAMPLE, keywords="transformer")
test("MD 包含标题", "## 1. Attention Is All You Need" in md)
test("MD 包含关键词头", "transformer" in md)
test("MD 包含原文链接", "[原文](https://arxiv.org/abs/1706.03762)" in md)
test("MD 包含 DOI 链接", "[DOI](https://doi.org/10.5555/3295222)" in md)
test("MD 包含摘要引用", "dominant sequence transduction" in md)
test("MD 空列表不崩溃", to_markdown([]).startswith("# LitScan"))

# 7.2 BibTeX 导出
bib = to_bibtex(SAMPLE)
test("BibTeX 有 venue 用 @article", "@article{vaswani2017attention" in bib)
test("BibTeX 无 venue 用 @misc", "@misc{devlin2019bert" in bib)
test("BibTeX 作者分号转 and", "Ashish Vaswani and Noam Shazeer" in bib)
test("BibTeX 重名 key 去重", len(_bibtex_key(SAMPLE[0], set())) > 0)
used = set()
k1 = _bibtex_key(SAMPLE[0], used)
k2 = _bibtex_key(SAMPLE[0], used)
test("BibTeX key 冲突自动加后缀", k1 != k2 and k2.startswith(k1))

# 7.3 纯文本导出
txt = to_text(SAMPLE)
test("TEXT 每行一条", txt.count("- ") >= 2)
test("TEXT 无 doi 用 url", "https://arxiv.org/abs/1706.03762" in txt)

# 7.4 CSV 导出
csv_bytes = to_csv_bytes(SAMPLE)
csv_header = csv_bytes.decode("utf-8-sig").splitlines()[0]
test("CSV 表头字段完整", csv_header.startswith("title,source,sources,year,venue,doi,url,citation_count,authors,abstract"))

# 7.5 统一入口与非法格式
test("build_export 返回字节", isinstance(build_export("markdown", SAMPLE), bytes))
try:
    build_export("xml", SAMPLE)
    test("非法格式抛 ValueError", False)
except ValueError:
    test("非法格式抛 ValueError", True)

# 7.6 文件名清洗
test("文件名清洗特殊字符", "/" not in _safe_filename('a/b:c*d?"<>|'))
test("空关键词兜底", _safe_filename("") == "export")

# 7.7 保存留档
tmpdir = tempfile.mkdtemp()
try:
    path = save_export(b"content", "markdown", tmpdir, "test keywords")
    test("留档文件存在", os.path.exists(path))
    test("留档扩展名正确", path.endswith(".md"))
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

# 7.8 EndNote (RIS) 导出
from core.exporter import to_ris, FORMAT_META

ris = to_ris(SAMPLE)
test("RIS 以 TY 开头", ris.startswith("TY  - JOUR"))
test("RIS 标题行", "TI  - Attention Is All You Need" in ris)
test("RIS 作者拆分多行", ris.count("AU  - ") == 4)  # 2 + 2 位作者
test("RIS 结束标记", "ER  - " in ris)
test("RIS 无 venue 用 GEN", "TY  - GEN" in to_ris([SAMPLE[1]]))


# ─────────────────────────────────────────────────────────────
section("8. 去重与排序 core/dedup.py")
# ─────────────────────────────────────────────────────────────

from core.dedup import deduplicate, sort_articles, _norm_doi, _norm_title

def A(title, source, **kw):
    return Article(title=title, source=source, **kw)

# 8.1 DOI 主键去重
dup_set = [
    A("Same Paper", "arxiv", doi="10.1000/ABC.", year=2024, abstract="short"),
    A("Same Paper", "crossref", doi="https://doi.org/10.1000/abc", year=2024,
      abstract="a much longer abstract text here", citation_count=5),
    A("Other Paper", "doaj", title2=None) if False else A("Other Paper", "doaj", year=2023),
]
kept, st = deduplicate(dup_set)
test("DOI 去重后剩 2 篇", len(kept) == 2)
test("DOI 统计正确", st["by_doi"] == 1 and st["removed"] == 1)
main = [a for a in kept if a.title == "Same Paper"][0]
test("保留信息更全的条目", main.abstract.startswith("a much longer"))
test("来源合并记录", "arxiv" in main.sources and "crossref" in main.sources)

# 8.2 标题兜底去重（无 DOI 但标题年份相同）
title_dup = [
    A("Diffusion Models Beat GANs", "arxiv", year=2021),
    A("diffusion   models beat gans", "openreview", year=2021),
    A("Diffusion Models Beat GANs", "semanticscholar", year=2020),  # 年份不同 → 不算重复
]
kept2, st2 = deduplicate(title_dup)
test("标题兜底去重", len(kept2) == 2 and st2["by_title"] == 1)
test("不同年份不合并", any(a.year == 2020 for a in kept2))

# 8.3 无重复时保持原样
no_dup = [A("Paper A", "arxiv", year=2024), A("Paper B", "crossref", year=2023)]
kept3, st3 = deduplicate(no_dup)
test("无重复不丢条目", len(kept3) == 2 and st3["removed"] == 0)

# 8.4 归一化函数
test("DOI 去前缀/小写", _norm_doi("https://doi.org/10.1000/ABC.") == "10.1000/abc")
test("DOI 空值", _norm_doi("") is None)
test("标题归一化", _norm_title("The  Attention!! Is-All You Need") == "attention is all you need")

# 8.5 排序
unsorted_set = [
    A("Low", "arxiv", year=2019, citation_count=3),
    A("High", "arxiv", year=2024, citation_count=99),
    A("NoCite", "arxiv", year=2021, citation_count=None),
]
by_cite = sort_articles(unsorted_set, by="citations")
test("按引用数降序", by_cite[0].citation_count == 99 and by_cite[-1].citation_count is None)
by_year = sort_articles(unsorted_set, by="year")
test("按年份降序", by_year[0].year == 2024)
by_rel = sort_articles(unsorted_set, by="relevance")
test("relevance 保持原序", by_rel[0].title == "Low")

# 8.6 导出格式注册表与生成函数一致（防止新增格式漏注册）
test("FORMAT_META 覆盖全部格式",
     set(FORMAT_META.keys()) == {"markdown", "bibtex", "endnote", "csv", "text"})
for fmt in FORMAT_META:
    test(f"build_export 支持 {fmt}", isinstance(build_export(fmt, SAMPLE, "kw"), bytes))
try:
    build_export("nonsense", SAMPLE)
    test("未知格式抛 ValueError", False)
except ValueError:
    test("未知格式抛 ValueError", True)


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
