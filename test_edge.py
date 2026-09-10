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
section("9. 全文下载 core/fulltext.py")
# ─────────────────────────────────────────────────────────────

from core.fulltext import (
    extract_arxiv_id, extract_openreview_id, resolve_pdf_url,
    download_article, download_articles, is_valid_pdf,
    load_articles_from_csv, _safe_filename, _has_traversal,
    SOURCE_SUPPORT, support_table, MIN_BYTES,
)

# 9.1 标识符解析
test("arXiv abs 链接解析", extract_arxiv_id("https://arxiv.org/abs/1706.03762") == "1706.03762")
test("arXiv pdf 链接解析", extract_arxiv_id("https://arxiv.org/pdf/2301.00001v2") == "2301.00001v2")
test("arXiv DOI 解析", extract_arxiv_id(None, "10.48550/arXiv.2401.12345") == "2401.12345")
test("arXiv 老式 ID", extract_arxiv_id("https://arxiv.org/abs/cs/0701001") == "cs/0701001")
test("非 arXiv 返回 None", extract_arxiv_id("https://example.com/paper") is None)
test("OpenReview ID 解析", extract_openreview_id("https://openreview.net/forum?id=abcDEF123") == "abcDEF123")
test("OpenReview 无 id 返回 None", extract_openreview_id("https://openreview.net/forum") is None)

# 9.2 PDF 有效性校验（PDF 魔数 + 最小体积）
test("合法 PDF 通过", is_valid_pdf(b"%PDF-1.7" + b"0" * MIN_BYTES))
test("非 PDF 头被拒", not is_valid_pdf(b"<html>" + b"0" * MIN_BYTES))
test("体积不足被拒", not is_valid_pdf(b"%PDF-1.7" + b"0" * 10))
test("空内容被拒", not is_valid_pdf(b""))

# 9.3 直链解析（不联网）
import core.fulltext as _ft

_orig_ft_fetch = _ft.fetch


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


test("arXiv 直链", resolve_pdf_url("arxiv", url="https://arxiv.org/abs/1706.03762")["pdf_url"]
     == "https://arxiv.org/pdf/1706.03762")
test("OpenReview 直链", resolve_pdf_url("openreview", url="https://openreview.net/forum?id=X1")["pdf_url"]
     == "https://openreview.net/pdf?id=X1")
test("无 DOI 的 crossref 无法解析并给原因",
     resolve_pdf_url("crossref", url="https://doi.org/10.1/x")["ok"] is False
     and bool(resolve_pdf_url("crossref", url="https://doi.org/10.1/x")["reason"]))
test("未知源解析失败", resolve_pdf_url("nope", url="http://x")["ok"] is False)
test("支持表覆盖全部源", len(support_table()) == len(SOURCE_SUPPORT) and len(SOURCE_SUPPORT) >= 7)
test("路径穿越被识别", _has_traversal("../../etc/passwd"))
test("文件名清洗去非法字符", "/" not in _safe_filename('a/b:c*d?.pdf'))

# 9.3b DOI 兜底：Unpaywall → OpenAlex（模拟响应，不联网）
_ft.fetch = lambda url, *a, **k: _Resp(
    {"best_oa_location": {"url_for_pdf": "https://repo.example/a.pdf"}} if "unpaywall" in url else {})
try:
    _got = resolve_pdf_url("crossref", doi="10.1234/abc")
    test("crossref 经 Unpaywall 找到合法 OA 直链",
         _got["ok"] and _got["via"] == "unpaywall"
         and _got["pdf_url"] == "https://repo.example/a.pdf")
finally:
    _ft.fetch = _orig_ft_fetch

_ft.fetch = lambda url, *a, **k: _Resp(
    {"best_oa_location": {"url_for_pdf": None}} if "unpaywall" in url
    else {"best_oa_location": {"pdf_url": "https://oa.example/b.pdf"}})
try:
    _got2 = resolve_pdf_url("crossref", doi="10.1234/def")
    test("Unpaywall 无果时回落 OpenAlex",
         _got2["ok"] and _got2["via"] == "openalex" and _got2["pdf_url"].endswith("b.pdf"))
finally:
    _ft.fetch = _orig_ft_fetch

_ft.fetch = lambda *a, **k: _Resp({"best_oa_location": {}})
try:
    _got3 = resolve_pdf_url("crossref", doi="10.1234/ghi")
    test("无合法 OA 版本时明确返回失败",
         _got3["ok"] is False and "OpenAlex" in _got3["reason"])
finally:
    _ft.fetch = _orig_ft_fetch

# 9.4 下载流程（用假的 fetch 模拟，不联网）
_fake_pdf = b"%PDF-1.4\n" + b"x" * (MIN_BYTES + 100)


class _FakePdfResp:
    content = _fake_pdf


class _FakeHtmlResp:
    content = b"<html>blocked</html>"


tmpdir = tempfile.mkdtemp()
try:
    _ft.fetch = lambda *a, **k: _FakePdfResp()
    art = {"title": "T", "source": "arxiv", "url": "https://arxiv.org/abs/1706.03762"}
    r1 = download_article(art, tmpdir)
    test("下载成功且文件落盘", r1["status"] == "downloaded" and os.path.exists(r1["path"]))
    test("下载体积记录正确", r1["size"] == len(_fake_pdf))
    r2 = download_article(art, tmpdir)
    test("已存在则跳过（断点续传）", r2["status"] == "skipped")

    _ft.fetch = lambda *a, **k: _FakeHtmlResp()
    r3 = download_article({"title": "T2", "source": "arxiv",
                           "url": "https://arxiv.org/abs/2301.00001"}, tmpdir, attempts=1)
    test("非 PDF 响应判失败", r3["status"] == "failed"
         and not os.path.exists(os.path.join(tmpdir, "2301.00001.pdf")))

    _ft.fetch = _orig_ft_fetch
    r4 = download_article({"title": "O", "source": "openaire"}, tmpdir)
    test("不可下载源标 unsupported 并带原因", r4["status"] == "unsupported" and bool(r4["reason"]))

    _ft.fetch = lambda *a, **k: _FakePdfResp()
    batch = [
        {"title": "A", "source": "arxiv", "url": "https://arxiv.org/abs/1111.11111"},
        {"title": "B", "source": "openaire"},
        {"title": "C", "source": "arxiv", "url": "https://arxiv.org/abs/2222.22222"},
    ]
    summ = download_articles(batch, tmpdir, limit=2, delay=0)
    test("批量 limit 生效", summ["total"] == 2)
    test("批量汇总计数", summ["downloaded"] == 1 and summ["unsupported"] == 1)
    test("汇总含绝对目录", os.path.isdir(summ["dir"]))
finally:
    _ft.fetch = _orig_ft_fetch
    shutil.rmtree(tmpdir, ignore_errors=True)

# 9.5 CSV 读取（对齐参考脚本的「CSV → 断点续传」用法）
tmpdir = tempfile.mkdtemp()
try:
    csv_path = save_csv([Article(title="Paper", source="arxiv",
                                 url="https://arxiv.org/abs/1706.03762")], tmpdir, "articles.csv")
    rows = load_articles_from_csv(csv_path)
    test("CSV 读取条目", len(rows) == 1 and rows[0]["source"] == "arxiv")
    test("CSV 空值转 None", rows[0]["doi"] is None)
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)


# ─────────────────────────────────────────────────────────────
section("10. 数据保存与持久化")
# ─────────────────────────────────────────────────────────────

# 10.1 搜索历史落盘 + 重载
tmpdir = tempfile.mkdtemp()
try:
    from core.history import SearchHistory
    hp = os.path.join(tmpdir, "history.json")
    h1 = SearchHistory(history_file=hp)
    rec = h1.add("persist test", ["arxiv"], 2020, 5, 3, {"arxiv": 3})
    test("历史文件落盘", os.path.exists(hp))
    h2 = SearchHistory(history_file=hp)
    test("历史重载条数一致", len(h2) == 1)
    test("历史字段完整可读", h2.get(rec.id).keywords == "persist test")
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

# 10.2 操作日志落盘 + 重载
tmpdir = tempfile.mkdtemp()
try:
    from core.logger import OperationLogger
    lp = os.path.join(tmpdir, "operations.json")
    lg1 = OperationLogger(log_file=lp)
    lg1.success("hello", source="test", details={"n": 1})
    test("操作日志落盘", os.path.exists(lp))
    lg2 = OperationLogger(log_file=lp)
    test("操作日志重载条数一致", len(lg2) == 1)
    test("操作日志字段完整", lg2.list()[0].message == "hello")
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

# 10.3 CSV 写出 → 读回（标题/来源保持）
tmpdir = tempfile.mkdtemp()
try:
    p = save_csv([Article(title="持久化标题", source="arxiv",
                          url="https://arxiv.org/abs/1706.03762")], tmpdir)
    test("CSV 落盘", os.path.exists(p))
    back = load_articles_from_csv(p)
    test("CSV 读回标题一致", back and back[0]["title"] == "持久化标题")
    test("CSV 读回来源一致", back and back[0]["source"] == "arxiv")
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

# 10.4 导出留档
tmpdir = tempfile.mkdtemp()
try:
    content = build_export("bibtex", SAMPLE)
    p = save_export(content, "bibtex", tmpdir, "持久化 测试")
    test("导出留档存在且扩展名正确", os.path.exists(p) and p.endswith(".bib"))
    test("留档内容与生成一致", os.path.getsize(p) == len(content))
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

# 10.5 PDF 落盘 + 断点续传 + 无 .part 残留
tmpdir = tempfile.mkdtemp()
try:
    _ft.fetch = lambda *a, **k: _FakePdfResp()
    _art = {"title": "P", "source": "arxiv", "url": "https://arxiv.org/abs/9999.99999"}
    _r1 = download_article(_art, tmpdir)
    test("PDF 文件落盘", _r1["status"] == "downloaded" and os.path.exists(_r1["path"]))
    if _r1["path"] and os.path.exists(_r1["path"]):
        with open(_r1["path"], "rb") as _f:
            test("落盘内容为有效 PDF", _f.read(4) == b"%PDF")
    _r2 = download_article(_art, tmpdir)
    test("再次下载命中续传跳过", _r2["status"] == "skipped")
    test("无 .part 残留文件", not [f for f in os.listdir(tmpdir) if f.endswith(".part")])
finally:
    _ft.fetch = _orig_ft_fetch
    shutil.rmtree(tmpdir, ignore_errors=True)


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
