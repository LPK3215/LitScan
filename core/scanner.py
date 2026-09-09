"""
LitScan 核心调度器
读配置 → 调各库适配器 → 合并输出 → 记录历史
"""

import logging
from typing import Optional, Callable

import yaml

from .adapters import ADAPTERS, Article
from .output import save_csv, append_log
from .history import SearchHistory, SearchRecord
from .fetcher import RateLimitInfo, FetchError

logger = logging.getLogger("litscan.scanner")


class Scanner:
    """给定配置，执行多库检索，输出结构化结果"""

    def __init__(self, config: dict):
        self.config = config
        self.articles: list[Article] = []
        self.results_per_source: dict[str, int] = {}
        self.history: SearchHistory = self._init_history()
        self._on_rate_limit: Optional[Callable] = None
        self._on_retry: Optional[Callable] = None

    def _init_history(self):
        """初始化搜索历史"""
        hist_cfg = self.config.get("history", {})
        enabled = hist_cfg.get("enabled", True)
        if not enabled:
            return None
        file_path = hist_cfg.get("file", None)
        try:
            return SearchHistory(history_file=file_path)
        except Exception as e:
            logger.error(f"初始化历史失败: {e}")
            return None

    def set_callbacks(self, on_rate_limit=None, on_retry=None):
        """设置回调（CLI/API 用于显示进度）"""
        self._on_rate_limit = on_rate_limit
        self._on_retry = on_retry

    @classmethod
    def from_yaml(cls, path: str) -> "Scanner":
        """从 YAML 配置文件加载"""
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return cls(config)

    def run(self) -> list[Article]:
        """执行完整检索流程"""
        sources = self.config.get("sources", [])
        query_cfg = self.config.get("query", {})
        output_cfg = self.config.get("output", {})
        req_cfg = self.config.get("request", {})

        keywords = query_cfg.get("keywords", "")
        year_from = query_cfg.get("year_from")
        limit = query_cfg.get("limit_per_source", 30)

        logger.info(f"开始检索: keywords={keywords}, year_from={year_from}, limit={limit}")
        print(f"\n{'='*50}")
        print(f"  LitScan · 文献检索")
        print(f"{'='*50}")
        print(f"  关键词: {keywords}")
        print(f"  年份≥: {year_from or '不限'}")
        print(f"  每库: {limit} 篇")
        print(f"{'='*50}\n")

        self.articles = []
        self.results_per_source = {}
        enabled_sources = []

        for src in sources:
            if not src.get("enabled", True):
                continue
            name = src["name"]
            if name not in ADAPTERS:
                logger.warning(f"未知源: {name}，跳过")
                continue

            adapter = ADAPTERS[name]
            enabled_sources.append(name)
            print(f"  [{name}] ...", end="", flush=True)

            try:
                articles = adapter(
                    keywords=keywords,
                    limit=limit,
                    year_from=year_from,
                    timeout=req_cfg.get("timeout", 45),
                    max_retries=req_cfg.get("max_retries", 4),
                    retry_delay=req_cfg.get("retry_delay", 8),
                    user_agent=req_cfg.get("user_agent", "LitScan/1.0"),
                    proxy=req_cfg.get("proxy"),
                    on_rate_limit=self._on_rate_limit,
                    on_retry=self._on_retry,
                    source_name=name,
                )
                self.articles.extend(articles)
                self.results_per_source[name] = len(articles)
                print(f" OK {len(articles)} 篇")

            except FetchError as e:
                self.results_per_source[name] = 0
                print(f" FAIL (重试{e.retries_done}次)")
                logger.error(f"{name} 检索失败: {e}")
            except Exception as e:
                self.results_per_source[name] = 0
                print(f" ERR: {str(e)[:60]}")
                logger.error(f"{name} 检索异常: {e}")

        print(f"\n{'='*50}")
        print(f"  检索完成: 共 {len(self.articles)} 篇")
        print(f"{'='*50}")
        for src, count in self.results_per_source.items():
            status = "OK" if count > 0 else "FAIL"
            print(f"  [{status:4s}] {src}: {count} 篇")
        print(f"{'='*50}")

        # ── 输出文件 ──
        output_dir = output_cfg.get("dir", "./out")
        if output_cfg.get("save_csv", True):
            save_csv(self.articles, output_dir)
            print(f"\n  CSV: {output_dir}/articles.csv")

        if output_cfg.get("save_log", True):
            log_path = f"{output_dir}/log.md"
            append_log(log_path, keywords, enabled_sources, self.results_per_source, len(self.articles))
            print(f"  日志: {log_path}")

        # ── 保存搜索历史 ──
        if self.history:
            record = self.history.add(
                keywords=keywords,
                sources=enabled_sources,
                year_from=year_from,
                limit_per_source=limit,
                total_results=len(self.articles),
                per_source=self.results_per_source,
            )
            print(f"  历史: {record.id}")

        return self.articles

    def search_single(self, source_name: str, keywords: str, limit: int = 30,
                      year_from: Optional[int] = None, **req_kwargs) -> list[Article]:
        """检索单个库（供 API 调用）"""
        if source_name not in ADAPTERS:
            raise ValueError(f"未知源: {source_name}，可用: {list(ADAPTERS.keys())}")
        return ADAPTERS[source_name](keywords=keywords, limit=limit, year_from=year_from, **req_kwargs)

    def get_history(self, limit: int = 20):
        """获取搜索历史"""
        if not self.history:
            return []
        return self.history.list(limit)

    def retry_from_history(self, record_id: str) -> list[Article]:
        """从历史记录重新执行检索"""
        if not self.history:
            raise RuntimeError("历史功能未启用")
        record = self.history.get(record_id)
        if not record:
            raise ValueError(f"未找到记录: {record_id}")
        # 用历史记录的参数执行
        self.config["query"]["keywords"] = record.keywords
        self.config["query"]["year_from"] = record.year_from
        self.config["query"]["limit_per_source"] = record.limit_per_source
        return self.run()
