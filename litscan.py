#!/usr/bin/env python3
"""
LitScan · CLI 入口

用法:
  python litscan.py                          # 用默认 config.yaml 执行检索
  python litscan.py --config myconfig.yaml   # 指定配置文件
  python litscan.py --keywords "my topic"    # 命令行覆盖关键词
  python litscan.py -k "LLM agent" -y 2023 -l 20  # 限定年份与每库条数
  python litscan.py --no-dedup                  # 关闭跨库去重
  python litscan.py --sort-by citations         # 按引用数排序
  python litscan.py --history                    # 查看搜索历史
  python litscan.py --history-search "LLM"   # 搜索历史记录
  python litscan.py --retry 20260909_123456  # 从历史记录重新检索
  python litscan.py --sources                # 列出可用检索源
  python litscan.py --download               # 检索后下载开放全文 PDF (默认 20 篇)
  python litscan.py --download-csv out/articles.csv  # 不检索，从 CSV 批量下载并续传
  python litscan.py --serve                  # 启动 FastAPI 服务
"""

import os
import argparse
import logging
import sys
import io

# Windows GBK 编码修复
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from core.scanner import Scanner
from core.adapters import ADAPTERS
from core.history import SearchHistory


def cmd_search(args, scanner: Scanner):
    """执行检索"""
    # 命令行覆盖配置
    if args.keywords:
        scanner.config["query"]["keywords"] = args.keywords
    if args.limit:
        scanner.config["query"]["limit_per_source"] = args.limit
    if args.year:
        scanner.config["query"]["year_from"] = args.year
    if args.proxy:
        scanner.config["request"]["proxy"] = args.proxy
    elif args.no_proxy:
        scanner.config["request"]["proxy"] = "none"
    if args.no_dedup:
        scanner.config["output"]["dedup"] = False
    if args.sort_by:
        scanner.config["query"]["sort_by"] = args.sort_by

    articles = scanner.run()

    if args.download:
        run_download(articles, args, scanner)

    return articles


# ── 全文 PDF 下载 ──

_DL_SYMBOL = {"downloaded": "✓", "skipped": "⊘", "failed": "✗", "unsupported": "—"}


def _download_settings(args, scanner=None):
    """合并 CLI 参数与 config.yaml 的 download 段"""
    from core.fulltext import MIN_BYTES, DEFAULT_DELAY, DEFAULT_LIMIT

    cfg = (scanner.config.get("download", {}) if scanner else {}) or {}
    out_cfg = (scanner.config.get("output", {}) if scanner else {}) or {}
    req_cfg = (scanner.config.get("request", {}) if scanner else {}) or {}
    proxy = "none" if getattr(args, "no_proxy", False) else (args.proxy or req_cfg.get("proxy"))
    return {
        "pdf_dir": args.pdf_dir or cfg.get("dir") or os.path.join(out_cfg.get("dir", "./out"), "pdf"),
        "limit": args.download_limit or cfg.get("limit") or DEFAULT_LIMIT,
        "delay": cfg.get("delay", DEFAULT_DELAY),
        "min_bytes": cfg.get("min_bytes", MIN_BYTES),
        "proxy": proxy,
    }


def _cli_download_progress(idx, total, res):
    sym = _DL_SYMBOL.get(res["status"], "?")
    name = res.get("identifier") or (res.get("title") or "")[:40]
    if res["status"] == "downloaded":
        extra = f"{res['size'] / 1024:.0f}KB"
        if res.get("via") in ("unpaywall", "openalex"):
            extra += f" (via {res['via']})"
    elif res["status"] in ("failed", "unsupported"):
        extra = res.get("reason", "")[:60]
    else:
        extra = "本地已存在"
    print(f"  [{idx}/{total}] {sym} {res['source']}:{name}  {extra}")


def print_download_summary(summary: dict):
    print(f"\n  {'-'*50}")
    print(f"  下载完成: 成功 {summary['downloaded']} · 跳过 {summary['skipped']} · "
          f"失败 {summary['failed']} · 不支持 {summary['unsupported']}")
    print(f"  目录: {summary['dir']}")

    unsupported = {}
    for r in summary["results"]:
        if r["status"] == "unsupported" and r.get("source"):
            unsupported.setdefault(r["source"], r.get("reason", ""))
    if unsupported:
        print("  不可自动下载的源及原因:")
        for src, reason in unsupported.items():
            print(f"    · {src}: {reason}")
    if summary["failed"]:
        print("  失败项可重跑同一命令自动重试（已下好的会跳过）")
    print(f"  {'-'*50}")


def run_download(articles, args, scanner=None):
    """对文章列表批量下载开放全文 PDF"""
    from core.fulltext import download_articles

    if not articles:
        print("\n  没有可下载的结果（先完成一次检索）")
        return
    settings = _download_settings(args, scanner)
    payload = [a.to_dict() if hasattr(a, "to_dict") else a for a in articles]
    print(f"\n  PDF 下载 → {settings['pdf_dir']}（本次上限 {settings['limit']} 篇）")
    summary = download_articles(
        payload, settings["pdf_dir"], limit=settings["limit"],
        proxy=settings["proxy"], delay=settings["delay"],
        min_bytes=settings["min_bytes"], on_event=_cli_download_progress,
    )
    print_download_summary(summary)


def cmd_download_csv(args):
    """不检索，直接从 CSV 批量下载（断点续传）"""
    from core.fulltext import load_articles_from_csv, download_articles

    path = args.download_csv
    if not os.path.exists(path):
        print(f"  ✗ 文件不存在: {path}")
        sys.exit(1)
    articles = load_articles_from_csv(path)
    if not articles:
        print(f"  ✗ {path} 中没有可下载的条目")
        return
    settings = _download_settings(args)
    print(f"\n  从 CSV 加载 {len(articles)} 条: {path}")
    print(f"  PDF 下载 → {settings['pdf_dir']}（本次上限 {settings['limit']} 篇）")
    summary = download_articles(
        articles, settings["pdf_dir"], limit=settings["limit"],
        proxy=settings["proxy"], delay=settings["delay"],
        min_bytes=settings["min_bytes"], on_event=_cli_download_progress,
    )
    print_download_summary(summary)


def cmd_history(args):
    """查看搜索历史"""
    history = SearchHistory()
    records = history.list(limit=args.limit or 20)

    if not records:
        print("  暂无搜索历史")
        return

    print(f"\n{'='*60}")
    print(f"  搜索历史 (共 {len(history)} 条)")
    print(f"{'='*60}")
    for r in records:
        print(f"\n  [{r.id}] {r.timestamp}")
        print(f"    关键词: {r.keywords}")
        print(f"    来源: {', '.join(r.sources)}")
        print(f"    结果: {r.total_results} 篇 ({', '.join(f'{k}={v}' for k, v in r.per_source.items())})")
    print(f"\n{'='*60}")
    print(f"  提示: --retry <ID> 可重新执行某次检索")


def cmd_history_search(args):
    """搜索历史记录"""
    history = SearchHistory()
    records = history.search_by_keywords(args.query)

    if not records:
        print(f"  未找到包含 '{args.query}' 的历史记录")
        return

    print(f"\n  找到 {len(records)} 条记录:")
    print(f"  {'-'*50}")
    for r in records:
        print(f"  [{r.id}] {r.keywords} ({r.total_results}篇)")
    print(f"  {'-'*50}")
    print(f"  提示: --retry <ID> 可重新执行")


def cmd_retry(args, scanner: Scanner):
    """从历史记录重新执行"""
    try:
        articles = scanner.retry_from_history(args.record_id)
    except ValueError as e:
        print(f"  ✗ {e}")
        sys.exit(1)


def cmd_sources(args):
    """列出可用检索源"""
    print(f"\n  可用检索源 ({len(ADAPTERS)} 个):")
    print(f"  {'-'*50}")
    descriptions = {
        "arxiv": "arXiv 预印本 (免费无上限)",
        "semanticscholar": "Semantic Scholar (429限流)",
        "crossref": "Crossref DOI库 (免费)",
        "openreview": "OpenReview 顶会评审",
        "openaire": "OpenAIRE 欧盟开放科学",
        "doaj": "DOAJ 开放获取期刊",
        "europepmc": "Europe PMC 生物医学",
    }
    for name, desc in descriptions.items():
        print(f"  [{name:18s}] {desc}")
    print(f"  {'-'*50}")
    print(f"  提示: 在 config.yaml 中 enabled: false 可禁用某源")


def main():
    parser = argparse.ArgumentParser(
        description="LitScan · 学术文献多库检索工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python litscan.py -k "LLM agent evaluation"
  python litscan.py -k "deep learning" -y 2023 -l 50
  python litscan.py --history
  python litscan.py --retry 20260909_153022
  python litscan.py --serve
        """
    )

    # 检索参数
    parser.add_argument("--config", "-c", default="config.yaml", help="配置文件路径")
    parser.add_argument("--keywords", "-k", help="检索关键词")
    parser.add_argument("--limit", "-l", type=int, help="每库返回数量")
    parser.add_argument("--year", "-y", type=int, help="起始年份")
    parser.add_argument("--proxy", help="代理地址 (如 http://127.0.0.1:7897)")
    parser.add_argument("--no-proxy", action="store_true", help="不走代理")
    parser.add_argument("--no-dedup", action="store_true", help="关闭跨库去重")
    parser.add_argument("--sort-by", choices=["relevance", "citations", "year"],
                        help="排序方式（默认按配置 relevance）")

    # 全文 PDF 下载
    parser.add_argument("--download", action="store_true", help="检索后批量下载开放全文 PDF")
    parser.add_argument("--download-limit", type=int, help="单次最多下载篇数（默认取配置，兜底 20）")
    parser.add_argument("--pdf-dir", help="PDF 存放目录（默认 out/pdf）")
    parser.add_argument("--download-csv", metavar="CSV",
                        help="不检索，直接从 CSV（如 out/articles.csv）批量下载并断点续传")

    # 历史 & 管理
    parser.add_argument("--history", action="store_true", help="查看搜索历史")
    parser.add_argument("--history-search", metavar="QUERY", help="搜索历史记录")
    parser.add_argument("--history-limit", type=int, default=20, help="历史显示条数")
    parser.add_argument("--retry", metavar="ID", help="从历史记录重新执行检索")
    parser.add_argument("--sources", action="store_true", help="列出可用检索源")

    # 服务模式
    parser.add_argument("--serve", "-s", action="store_true", help="启动 FastAPI 服务")
    parser.add_argument("--host", default="127.0.0.1", help="服务监听地址")
    parser.add_argument("--port", "-p", type=int, default=8000, help="服务端口")

    # 其他
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")

    args = parser.parse_args()

    # 日志级别
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── 子命令路由 ──

    # 列出源
    if args.sources:
        cmd_sources(args)
        return

    # 历史相关（不需要 Scanner）
    if args.history:
        cmd_history(args)
        return

    if args.history_search:
        cmd_history_search(args)
        return

    # 从 CSV 批量下载（不需要 config.yaml，也不发起检索）
    if args.download_csv:
        cmd_download_csv(args)
        return

    # 启动 API 服务
    if args.serve:
        from server.main import run_server
        run_server(host=args.host, port=args.port)
        return

    # 正常检索 / retry
    try:
        scanner = Scanner.from_yaml(args.config)
    except FileNotFoundError:
        print(f"  配置文件不存在: {args.config}")
        print("  当前目录需要 config.yaml，或用 --config 指定路径")
        sys.exit(1)

    if args.retry:
        cmd_retry(args, scanner)
    else:
        cmd_search(args, scanner)


if __name__ == "__main__":
    main()
