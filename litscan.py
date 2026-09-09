#!/usr/bin/env python3
"""
LitScan · CLI 入口

用法:
  python litscan.py                          # 用默认 config.yaml 执行检索
  python litscan.py --config myconfig.yaml   # 指定配置文件
  python litscan.py --keywords "my topic"    # 命令行覆盖关键词
  python litscan.py --history                # 查看搜索历史
  python litscan.py --history-search "LLM"   # 搜索历史记录
  python litscan.py --retry 20260909_123456  # 从历史记录重新检索
  python litscan.py --sources                # 列出可用检索源
  python litscan.py --serve                  # 启动 FastAPI 服务
"""

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

    articles = scanner.run()
    return articles


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
